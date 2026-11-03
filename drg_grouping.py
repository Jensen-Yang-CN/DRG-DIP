"""CHS-DRG 3.0 rule evaluation against the exported workbook snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "drg_rules.json"
DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
SETS = {key: set(values) for key, values in DATA["sets"].items()}
SETS["OP_ALL"] = set().union(*(values for key, values in SETS.items() if key.startswith("OP")))
CC_TYPE = {code: row["type"] for code, row in DATA["cc"].items()}
CC_EXCL = {code: row["exclusion"] for code, row in DATA["cc"].items()}
EXCL = {key: set(values) for key, values in DATA["exclusions"].items()}
MDC_RULES = DATA["mdc"]
ADRG_ROWS = DATA["adrg"]
DRG_ROWS = DATA["drg"]
ADRG_BY_MDC = defaultdict(list)
DRG_BY_ADRG = defaultdict(list)
for row in ADRG_ROWS:
    ADRG_BY_MDC[row["mdc"]].append(row)
for row in DRG_ROWS:
    DRG_BY_ADRG[row["adrg"]].append(row)
LEN_REG = {}

# ------------------------------------------------------------------ DSL engine
TOKEN_RE = re.compile(
    r"\s*(?:(>=|<=|<>|!=|=|>|<|\{|\}|\(|\)|,)|"
    r"(not\s+in|in|and|or|not)\b|"
    r"([A-Za-z_][A-Za-z0-9_]*)|(\d+(?:\.\d+)?))", re.I)


def preprocess(rule):
    """Rewrite length(SET ∩ {A,B})>=2 style fragments into synthetic variables."""
    rule = rule.replace("_x000D_", " ").replace("_x000A_", " ")
    def rep(m):
        setname, vars_ = m.group(1), m.group(2)
        vnames = [v.strip() for v in vars_.split(",") if v.strip()]
        key = setname + ":" + ",".join(vnames)
        name = "__LEN_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        LEN_REG.setdefault(name, (setname, vnames))
        return name
    return re.sub(r"length\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*[\u2229&]\s*\{([^}]*)\}\s*\)", rep, rule)


@lru_cache(maxsize=2048)
def tokenize(s):
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\bOR\b", "or", s)
    s = re.sub(r"\bAND\b", "and", s)
    s = re.sub(r"\bNOT\b", "not", s)
    bal = s.count("(") - s.count(")")
    if bal > 0:
        s = s + ")" * bal
    elif bal < 0:
        out, depth = [], 0
        for ch in s:
            if ch == "(":
                depth += 1; out.append(ch)
            elif ch == ")":
                if depth == 0:
                    continue
                depth -= 1; out.append(ch)
            else:
                out.append(ch)
        s = "".join(out)
    toks, i = [], 0
    while i < len(s):
        m = TOKEN_RE.match(s, i)
        if not m:
            if s[i].isspace():
                i += 1; continue
            raise ValueError("bad char %r" % s[i])
        i = m.end()
        op, kw, ident, num = m.groups()
        if op:
            toks.append(("op", op))
        elif kw:
            toks.append(("kw", re.sub(r"\s+", " ", kw.lower())))
        elif ident:
            toks.append(("id", ident))
        elif num:
            toks.append(("num", float(num)))
    return toks


class Parser:
    def __init__(self, toks, ctx):
        self.t, self.i, self.ctx = toks, 0, ctx

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, want=None):
        k, v = self.peek()
        self.i += 1
        if want is not None and v != want:
            raise ValueError("expected %s got %s" % (want, v))
        return v

    def parse(self):
        v = self.orx()
        if self.i != len(self.t):
            raise ValueError("trailing %s" % (self.t[self.i:],))
        return v

    def orx(self):
        v = bool(self.andx())
        while self.peek() == ("kw", "or"):
            self.eat(); r = self.andx(); v = v or bool(r)
        return v

    def andx(self):
        v = bool(self.notx())
        while self.peek() == ("kw", "and"):
            self.eat(); r = self.notx(); v = v and bool(r)
        return v

    def notx(self):
        if self.peek() == ("kw", "not"):
            self.eat(); return not bool(self.notx())
        return self.atom()

    def atom(self):
        if self.peek() == ("op", "("):
            self.eat("("); v = self.orx(); self.eat(")"); return v
        return self.cmp()

    # ---- operands: always a 3-tuple (kind, name, value) ----
    def operand(self):
        k, v = self.peek()
        if k == "op" and v == "{":
            self.eat("{")
            names = []
            while True:
                kk, vv = self.peek()
                if kk in ("id", "num"):
                    self.eat(); names.append(vv)
                else:
                    raise ValueError("bad set member %s" % ((kk, vv),))
                if self.peek() == ("op", ","):
                    self.eat(","); continue
                break
            self.eat("}")
            return ("list", None, names)
        if k == "id":
            self.eat(); return ("name", v, None)
        if k == "num":
            self.eat(); return ("num", None, v)
        raise ValueError("bad operand %s" % ((k, v),))

    def resolve(self, name):
        if name in self.ctx:
            return self.ctx[name]
        if name in LEN_REG:
            setname, vnames = LEN_REG[name]
            target = SETS.get(setname, set())
            n = 0
            for vn in vnames:
                for code in self.asList(self.ctx.get(vn, "")):
                    if str(code) in target:
                        n += 1
            return n
        if name in SETS:
            return SETS[name]
        if name in ("MCC", "CC"):
            return name
        raise KeyError(name)

    @staticmethod
    def asList(v):
        if isinstance(v, (list, tuple, set)):
            return [str(x) for x in v]
        if v in ("", None):
            return []
        return [str(v)]

    def leftCodes(self, o):
        if o[0] == "name":
            return self.asList(self.resolve(o[1]))
        if o[0] == "list":
            out = []
            for nm in o[2]:
                out.extend(self.asList(self.resolve(nm)))
            return out
        return [str(o[2])]

    def ccLevel(self, code):
        lvl = CC_TYPE.get(str(code))
        if not lvl:
            return None
        ex = CC_EXCL.get(str(code))
        zyzd = str(self.ctx.get("ZYZD", ""))
        if ex and zyzd and zyzd in EXCL.get(ex, ()):
            return None
        return lvl

    def targets(self, right):
        if right[0] == "list":
            return [str(x) for x in right[2]]
        if right[0] == "name":
            return [right[1]]
        return [str(right[2])]

    def isMember(self, code, target):
        code = str(code)
        if target in ("MCC", "CC"):
            return self.ccLevel(code) == target
        return code in SETS.get(target, ())

    def inSet(self, left, right):
        tg = self.targets(right)
        codes = self.leftCodes(left)
        if not codes:
            return False
        return any(self.isMember(c, t) for c in codes for t in tg)

    def cmp(self):
        left = self.operand()
        k, v = self.peek()
        if k == "kw" and v in ("in", "not in"):
            self.eat()
            right = self.operand()
            res = self.inSet(left, right)
            return (not res) if v == "not in" else res
        OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
               ">": lambda a, b: a > b, "<": lambda a, b: a < b,
               "=": lambda a, b: a == b, "!=": lambda a, b: a != b,
               "<>": lambda a, b: a != b}
        if k == "op" and v in OPS:
            self.eat()
            right = self.operand()
            return OPS[v](self.scalar(left), self.scalar(right))
        if left[0] == "num":
            return bool(left[2])
        return len(self.leftCodes(left)) > 0

    def scalar(self, o):
        if o[0] == "num":
            return o[2]
        if o[0] == "name":
            return self.resolve(o[1])
        raise ValueError("cannot compare a list")


def ev(rule, ctx, tag=""):
    rule = str(rule or "").strip()
    if rule in ("", "0"):
        return False
    if rule == "1":
        return True
    try:
        return bool(Parser(tokenize(preprocess(rule)), ctx).parse())
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError(f"{tag} 规则无法解析：{rule[:120]}（{exc}）") from exc


def norm(value):
    return re.sub(r"\s+", "", str(value or "").upper())


def _first_adrg(mdc_code, ctx):
    for row in ADRG_BY_MDC[mdc_code]:
        if ev(row["rule"], ctx, "ADRG " + row["code"]):
            return row
    return None


def diagnose(zyzd, qtzd=(), zyss="", qtss=(), nl=0, xb=1, xsrlt=0, xsrtz=0):
    """Evaluate workbook rows in their priority order, including MDCA pre-grouping."""
    ctx = dict(ZYZD=zyzd, QTZD=list(qtzd), ZYSS=zyss, QTSS=list(qtss),
               NL=nl, XB=xb, XSRTL=xsrlt, XSRTZ=xsrtz)
    trace = []
    mdc = adrg = None
    for row in MDC_RULES:
        if row["code"] == "MDCA":
            candidate = _first_adrg("MDCA", ctx)
            if candidate:
                mdc, adrg = row, candidate
                trace.append({"state": "passed", "title": "先期分组 · MDCA",
                              "detail": f"ADRG {adrg['code']}：{adrg['rule']}（ADRG 表第 {adrg['row']} 行）"})
                break
            continue
        if ev(row["rule"], ctx, "MDC " + row["code"]):
            mdc = row
            trace.append({"state": "passed", "title": f"MDC · {row['code']} {row['name']}",
                          "detail": f"{row['rule']}（MDC 表第 {row['row']} 行）"})
            break
    if not mdc:
        trace.append({"state": "blocked", "title": "MDC 未命中",
                      "detail": "病例未满足配置工作簿中的 MDC 规则。"})
        return {"mdc": None, "adrg": None, "drg": None, "trace": trace}
    if not adrg:
        adrg = _first_adrg(mdc["code"], ctx)
        if adrg:
            trace.append({"state": "passed", "title": f"ADRG · {adrg['code']} {adrg['name']}",
                          "detail": f"{adrg['rule']}（ADRG 表第 {adrg['row']} 行）"})
    if not adrg:
        trace.append({"state": "blocked", "title": "ADRG 未命中",
                      "detail": f"已进入 {mdc['code']}，但该 MDC 下无满足条件的 ADRG。"})
        return {"mdc": mdc, "adrg": None, "drg": None, "trace": trace}
    for row in DRG_BY_ADRG[adrg["code"]]:
        if not row["rule"] or ev(row["rule"], ctx, "DRG " + row["code"]):
            trace.append({"state": "passed", "title": f"DRG · {row['code']} {row['name']}",
                          "detail": f"{row['rule'] or '本 ADRG 的默认末档'}（DRG 表第 {row['row']} 行）"})
            return {"mdc": mdc, "adrg": adrg, "drg": row, "trace": trace}
    trace.append({"state": "blocked", "title": "DRG 未命中",
                  "detail": f"已进入 {adrg['code']}，但无满足条件的 DRG。"})
    return {"mdc": mdc, "adrg": adrg, "drg": None, "trace": trace}


def _integer(value, label, *, required=False):
    if value in (None, ""):
        if required:
            raise ValueError(f"请填写{label}")
        return 0
    text = str(value).strip()
    if not re.fullmatch(r"\d+", text):
        raise ValueError(f"{label}只能填写非负整数，不要附加单位")
    return int(text)


def group_case(payload):
    diagnoses = payload.get("diagnoses") or []
    operations = payload.get("operations") or []
    if not isinstance(diagnoses, list) or not diagnoses:
        raise ValueError("请先添加主要诊断")
    if not isinstance(operations, list):
        raise ValueError("手术操作必须是编码列表")
    diagnoses, operations = [norm(x) for x in diagnoses], [norm(x) for x in operations]
    if any(not re.fullmatch(r"[A-Z0-9.]+", x) for x in diagnoses + operations):
        raise ValueError("诊断或操作编码格式不正确")
    sex = {"男": 1, "女": 2}.get(payload.get("sex"))
    if sex is None:
        raise ValueError("请选择性别")
    age = _integer(payload.get("age"), "年龄", required=True)
    if age > 130:
        raise ValueError("年龄不能超过 130 岁")
    age_days = _integer(payload.get("ageDays"), "天龄", required=age == 0)
    weight = _integer(payload.get("admissionWeight", payload.get("birthWeight")), "入院体重")
    _integer(payload.get("lengthOfStay"), "住院天数")
    if age == 0 and weight == 0:
        raise ValueError("新生儿病例请填写入院体重（g）")
    result = diagnose(diagnoses[0], diagnoses[1:], operations[0] if operations else "",
                      operations[1:], age, sex, age_days, weight)
    secondary_trace = []
    for secondary in diagnoses[1:]:
        severity = CC_TYPE.get(secondary)
        if severity:
            exclusion = CC_EXCL.get(secondary)
            excluded = diagnoses[0] in EXCL.get(exclusion, ())
            secondary_trace.append({
                "state": "info", "title": f"其他诊断 · {secondary}",
                "detail": f"{severity}，排除表 {exclusion or '无'}；"
                          + ("主诊断在排除集合中，本条不触发 CC/MCC。" if excluded
                             else "主诊断不在排除集合中，可参与相应 DRG 条件。"),
            })
    result["trace"] = secondary_trace + result["trace"]
    drg = result["drg"]
    if not drg:
        return {"scheme": "drg", "status": "unmatched", "hit": None,
                "message": "未能按配置工作簿得到完整的 MDC → ADRG → DRG 分组。",
                "path": {key: result[key] for key in ("mdc", "adrg", "drg")},
                "trace": result["trace"]}
    reference = DATA["reference"].get(drg["code"], {})
    return {
        "scheme": "drg", "status": "matched",
        "hit": {"code": drg["code"], "name": drg["name"],
                "weight": reference.get("weight"), "fee": reference.get("fee"),
                "label": reference.get("label")},
        "path": {key: result[key] for key in ("mdc", "adrg", "drg")},
        "trace": result["trace"],
    }


def catalog():
    return {"scheme": "drg", "mdcCount": len(MDC_RULES),
            "adrgCount": len(ADRG_ROWS), "drgCount": len(DRG_ROWS),
            "referenceCount": len(DATA["reference"])}


def search_catalog(kind, query, limit=10):
    names = DATA["diagnosisNames"] if kind == "dx" else DATA["operationNames"]
    query = str(query or "").strip()
    if len(query) < 2:
        return []
    code_query = norm(query)
    exact, starts, contains = [], [], []
    for code, name in names.items():
        item = {"code": code, "name": name}
        if kind == "dx" and code in DATA["cc"]:
            item["ccType"] = DATA["cc"][code]["type"]
        if code == code_query:
            exact.append(item)
        elif code.startswith(code_query):
            if len(starts) < limit:
                starts.append(item)
        elif code_query in code or query in name:
            if len(contains) < limit:
                contains.append(item)
    return (exact + starts + contains)[:limit]
