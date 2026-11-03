from __future__ import annotations

import json
import re
from pathlib import Path

# ── 数据来源与规则层名称 ────────────────────────────────────────────────
# Excel 由 scripts/export_rules.py 预先导出为 rules.json；请求分组时读取该快照。
ROOT = Path(__file__).resolve().parent
RULES_PATH = ROOT / "data" / "rules.json"
SECTION_LABEL = {
    "xq": "先期分组",
    "fz_burn": "诊断辅助细分 · 烧伤",
    "fz_tumor": "诊断辅助细分 · 肿瘤",
    "fz_tb": "诊断辅助细分 · 结核",
    "bx": "并项规则",
    "jc": "基础规则",
}


# ── 读取规则快照 ────────────────────────────────────────────────────
# 读取十张工作表导出的数据、原表名和原行号；此处不直接打开 xlsx。
def load_rules():
    with RULES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)



# ── 编码与规则表达式的基础匹配 ────────────────────────────────────────
# 去掉空白并转大写，统一用户输入和表内文字；点号及 x 等编码字符保留。
def norm(value):
    return re.sub(r"\s+", "", str(value or "").strip().upper())



# 判断单个诊断条件：支持‘所有诊断’、C00-C75 等范围、短编码前缀及完整编码。
# 短编码按当前 Demo 的前缀规则处理，例如 Z51.101 可匹配 Z51.1。
def diagnosis_atom_matches(code, atom):
    value, pattern = norm(code), norm(atom)
    if not value or not pattern:
        return False
    if pattern == "所有诊断":
        return True
    # 范围只比较 ICD 前三位类别，如 C34 属于 C00-C75。
    match = re.fullmatch(r"([A-Z][0-9]{2})-([A-Z][0-9]{2})", pattern)
    if match:
        category = re.match(r"^[A-Z][0-9]{2}", value)
        return bool(category and match[1] <= category[0] <= match[2])
    # 长度不超过 5 的规则编码允许前缀匹配；更长的编码要求完整相等。(这里说的是包括了小数点前面的位数)
    if len(pattern) <= 5:
        return value == pattern or value.startswith(pattern + ".") or ("." in pattern and value.startswith(pattern))
    return value == pattern



# 把诊断表达式拆开：'|' 是任选一个分支，'+' 是同一分支内全部满足。
# 这里始终用传入的同一个诊断编码检查一个分支中的各个原子条件。
def diagnosis_matches(code, expression):
    pattern = norm(expression)
    return bool(pattern and any(
        all(diagnosis_atom_matches(code, atom) for atom in group.split("+"))
        for group in pattern.split("|")
    ))



# 旧 score 使用的诊断具体程度：‘所有诊断’为 0，范围为 1，其他按文字长度计、最多 10。
# 这只是同一层候选规则的排序辅助值，不代表医学严重程度。
def diagnosis_specificity(expression):
    value = norm(expression)
    if value == "所有诊断":
        return 0
    if "-" in value:
        return 1
    return min(10, max(map(len, value.split("|")), default=0))



# 检查操作列表是否满足表达式：'|' 表示任一组合，'+' 表示组合内都存在。
# 不要求哪个操作是主操作，主要用于 XQ 和额外相关操作条件。
def operation_matches(expression, codes):
    value = norm(expression)
    code_set = set(map(norm, codes))
    return bool(value and any(
        all(part in code_set for part in group.split("+"))
        for group in value.split("|")
    ))



# 检查某规则要求的主操作组合：'+' 左边第一个编码必须是主操作，
# 同一组合的其余编码也必须出现在操作列表；'|' 表示可选组合。
# 注意：它匹配的是 FZ/BX/JC 等规则行，不负责查‘五、排除表’。
def main_operation_matches(expression, main, all_codes):
    value, main = norm(expression), norm(main)
    if not value or not main:
        return False
    code_set = set(all_codes)
    # 与上面的中文说明对应：先核对主操作，再核对该组合的全部操作。
    # In a combination, the first code is the principal operation; later codes
    # are required related operations. Alternatives are separated with '|'.
    return any((parts := group.split("+"))[0] == main and all(part in code_set for part in parts)
               for group in value.split("|"))



# ── 候选规则的条件数与平分时的 score ───────────────────────────────────
# score 使用规则表达式中要求操作最多的可选分支，不看本次实际命中哪一支。
def count_requirements(expression):
    return max((len(group.split("+")) for group in norm(expression).split("|") if group), default=0)



# conditionCount 使用本病例实际满足的分支；若传了 main，还要求分支首项是主操作。
def matched_operation_count(expression, codes, main=None):
    """Count requirements in the alternative actually satisfied by this case."""
    code_set = set(map(norm, codes))
    main = norm(main) if main is not None else None
    counts = []
    for group in norm(expression).split("|"):
        parts = group.split("+") if group else []
        if parts and all(part in code_set for part in parts) and (main is None or parts[0] == main):
            counts.append(len(parts))
    return max(counts, default=0)



# 统计一条已命中规则满足的要求：每个具体诊断条件计 1，
# 加上实际命中组合中的操作个数；extra 给新生儿年龄/体重、结核耐药等额外判断。
# 它不是用户输入编码的总数，无关的其他诊断或操作不会加分。
def condition_count(*diagnosis_rules, operations=(), extra=0):
    """Count independent rule requirements met by a candidate row."""
    diagnosis_count = sum(bool(norm(rule) and norm(rule) != "所有诊断") for rule in diagnosis_rules)
    return diagnosis_count + sum(matched_operation_count(expr, codes, main) for expr, codes, main in operations) + extra



# 沿用旧排序分数：基础 100 + 诊断具体程度 + 各层指定的操作权重/加分。
# 只有 conditionCount 相同才比较 score；这些权重不是国家 DIP 分值。
def tie_score(diagnosis="", main_operation="", related_operation="", *,
              main_weight=0, related_weight=0, main_bonus=0, related_bonus=0):
    """Preserve the demo's former ordering wh en candidates satisfy equally many conditions."""
    return (100 + diagnosis_specificity(diagnosis)
            + count_requirements(main_operation) * main_weight
            + count_requirements(related_operation) * related_weight
            + (main_bonus if norm(main_operation) else 0)
            + (related_bonus if norm(related_operation) else 0))



# ── 从 JSON 行构造可展示的候选结果 ────────────────────────────────────
# 安全读取第 index 列；短行缺少该列时返回空字符串。
def rv(row, index):
    return row["v"][index] if index < len(row["v"]) else ""



# 统一包装命中行：规则编号、原 Excel 行号、展示名称及排序指标。
# 如 FZ-1771 是表内规则标识，不等于地方医保结算病种编码。
def make_hit(section, row, name, diagnosis_rule, operation_rule, auxiliary_rule="", score=0, conditions=0):
    return {
        "key": f"{rv(row, 0)}-{rv(row, 1)}",
        "category": rv(row, 0), "number": rv(row, 1),
        "section": section, "sectionLabel": SECTION_LABEL[section],
        "row": row["row"], "name": name,
        "diagnosisRule": diagnosis_rule, "operationRule": operation_rule,
        "auxiliaryRule": auxiliary_rule, "score": score, "conditionCount": conditions,
    }



# ── 第一层：先期分组 XQ ──────────────────────────────────────────────
# 逐行找满足条件的 XQ 规则，返回所有候选；本函数不决定最终选哪条。
def xq_candidates(rows, case):
    results = []
    for row in rows:
        v = row["v"]
        # XQ 16 号起走新生儿分支：年龄须小于 29 天，并满足出生体重及诊断范围。
        if int(v[1]) >= 16:
            weight_range = re.search(r"(\d+)-(\d+)", v[6])
            if not weight_range or case["ageDays"] is None or case["ageDays"] >= 29 or case["birthWeight"] is None:
                continue
            if not any(diagnosis_matches(code, v[3]) for code in case["diagnoses"]):
                continue
            if not int(weight_range[1]) <= case["birthWeight"] <= int(weight_range[2]):
                continue
            results.append(make_hit("xq", row, v[2], v[3], "", f"{v[5]}；{v[6]}",
                                    tie_score(v[3]),
                                    condition_count(v[3], extra=2)))
            continue
        # 其他 XQ 规则：主诊断满足要求，所需操作可出现在任一操作位置。
        if v[3] != "所有诊断" and not diagnosis_matches(case["principalDx"], v[3]):
            continue
        if not operation_matches(v[5], case["operations"]):
            continue
        results.append(make_hit("xq", row, v[2], v[3], v[5], v[7],
                                tie_score(v[3], v[5], main_weight=10),
                                condition_count(v[3], operations=((v[5], case["operations"], None),))))
    return results



# ── 第二层：诊断辅助细分 FZ（肿瘤、烧伤、结核）─────────────────────────
# 三个子表的命中行合并为同一层候选，再按条件数、score、序号排序。
def fz_candidates(sheets, case, resistant_set):
    principal, other = case["principalDx"], case["otherDx"]
    main, operations = case["effectiveMainOperation"], case["effectiveOperations"]
    results = []
    # 肿瘤：主诊断、至少一个其他诊断以及指定主操作组合都要匹配。
    for row in sheets["fz_tumor"]["rows"]:
        v = row["v"]
        if not diagnosis_matches(principal, v[2]) or not any(diagnosis_matches(dx, v[4]) for dx in other):
            continue
        if not main_operation_matches(v[6], main, operations):
            continue
        results.append(make_hit("fz_tumor", row, f"{v[3]} · {v[5]} · {v[7]}", v[2], v[6],
                                f"其他诊断 {v[4]}", tie_score(v[4], v[6], main_weight=10),
                                condition_count(v[2], v[4], operations=((v[6], operations, main),))))
    # 烧伤：除主/其他诊断外，分别核对可选的主操作和相关操作列。
    for row in sheets["fz_burn"]["rows"]:
        v = row["v"]
        if not diagnosis_matches(principal, v[2]) or not any(diagnosis_matches(dx, v[4]) for dx in other):
            continue
        if v[6] and not main_operation_matches(v[6], main, operations):
            continue
        if v[8] and not operation_matches(v[8], operations):
            continue
        if not v[6] and main:
            continue
        name = f"{v[3]} · {v[5]}" + (f" · {v[7]}" if v[7] else "")
        aux = f"其他诊断 {v[4]}" + (f"；相关操作 {v[8]}" if v[8] else "")
        results.append(make_hit("fz_burn", row, name, v[2], v[6], aux,
                                tie_score(main_operation=v[6], related_operation=v[8],
                                          main_weight=10, related_weight=5),
                                condition_count(v[2], v[4], operations=((v[6], operations, main),
                                                                          (v[8], operations, None)))))
    # 结核：主诊断在耐药目录中，或其他诊断含 U84.300，就按耐药情况选规则。
    drug_resistant = principal in resistant_set or any(diagnosis_matches(dx, "U84.300") for dx in other)
    # 无主操作要求的结核行只接受无有效主操作的病例。
    for row in sheets["fz_tb"]["rows"]:
        v = row["v"]
        if not diagnosis_matches(principal, v[2]):
            continue
        if v[4] and not main_operation_matches(v[4], main, operations):
            continue
        if not v[4] and main:
            continue
        if (v[6] == "是") != drug_resistant:
            continue
        name = f"{v[3]} · {v[5] or '保守治疗'} · {'耐药' if drug_resistant else '非耐药'}"
        results.append(make_hit("fz_tb", row, name, v[2], v[4], v[7],
                                tie_score(v[2], v[4], main_weight=10),
                                condition_count(v[2], operations=((v[4], operations, main),), extra=1)))
    return results



# ── 第三层：并项规则 BX ───────────────────────────────────────────────
# 主诊断及主操作组合必须符合；相关操作列有值时，还须由非主操作满足。
def bx_candidates(rows, case):
    principal, main, operations = case["principalDx"], case["effectiveMainOperation"], case["effectiveOperations"]
    results = []
    for row in rows:
        v = row["v"]
        if not diagnosis_matches(principal, v[2]) or not main_operation_matches(v[4], main, operations):
            continue
        if v[6] and not operation_matches(v[6], [op for op in operations if op != main]):
            continue
        name = f"{v[3]} · {v[5]}" + (f" · {v[7]}" if v[7] and v[6] else "")
        results.append(make_hit("bx", row, name, v[2], v[4], f"相关操作 {v[6]}" if v[6] else "",
                                tie_score(v[2], v[4], v[6], main_weight=5,
                                          related_weight=1, related_bonus=30),
                                condition_count(v[2], operations=((v[4], operations, main),
                                                                  (v[6], [op for op in operations if op != main], None)))))
    return results



# ── 第四层：基础规则 JC ───────────────────────────────────────────────
# 有操作要求的行匹配有效主操作；无操作要求的行只走保守治疗路径。
def jc_candidates(rows, case):
    principal, main, operations = case["principalDx"], case["effectiveMainOperation"], case["effectiveOperations"]
    results = []
    for row in rows:
        v = row["v"]
        if not diagnosis_matches(principal, v[2]):
            continue
        if v[4] and not main_operation_matches(v[4], main, operations):
            continue
        if not v[4] and main:
            continue
        results.append(make_hit("jc", row, f"{v[3]} · {v[5] or '保守治疗'}", v[2],
                                v[4] or "无有效主操作（保守治疗）", "",
                                tie_score(v[2], v[4], main_weight=1, main_bonus=20),
                                condition_count(v[2], operations=((v[4], operations, main),))))
    return results



# ── 命中核心规则后附加基层病种标识 ──────────────────────────────────
# 这是附加标签，不重新选择 XQ/FZ/BX/JC；当前 Demo 不给 XQ 附此标签。
def grassroots_matches(rows, case, hit):
    if hit["section"] == "xq":
        return []
    result = []
    for row in rows:
        v = row["v"]
        if not diagnosis_matches(case["principalDx"], v[1]):
            continue
        if v[3]:
            if not main_operation_matches(v[3], case["effectiveMainOperation"], case["effectiveOperations"]):
                continue
        elif hit["section"] != "jc" or case["effectiveMainOperation"]:
            continue
        result.append({"number": v[0], "name": v[2], "row": row["row"]})
    return result



# ── 同一层候选规则的选取顺序 ──────────────────────────────────────────
# min 配合负号：conditionCount 大的优先，再看旧 score，最后取较小序号。
def candidate_rank(hit):
    # Most satisfied requirements win; preserve the former heuristic for ties.
    return (-hit["conditionCount"], -hit["score"], int(hit["number"]))



# 从当前层完整命中的候选中选一条；其他命中行会作为备选展示。
def best(candidates):
    return min(candidates, key=candidate_rank) if candidates else None



# 可选数字字段转浮点数；空值或无效文字返回 None，特殊规则据此判定是否可用。
def _optional_number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None



# ── 一次点击‘执行分组’的总流程 ────────────────────────────────────────
# 输入 → 主诊断排除 → 主操作资格/保守治疗处理 → XQ/FZ/BX/JC → 基层标识。
def group_case(data, raw_case):
    sheets = data["sheets"]
    raw_dx = raw_case.get("diagnoses") or []
    raw_op = raw_case.get("operations") or []
    # 前端录入顺序决定角色：第一项诊断/操作为主项，后续为其他项。
    principal = norm(raw_dx[0]) if raw_dx else ""
    other = [norm(dx) for dx in raw_dx[1:] if norm(dx)]
    main = norm(raw_op[0]) if raw_op else ""
    operations = [norm(op) for op in raw_op if norm(op)]
    diagnoses = [principal, *other] if principal else other
    trace = []
    empty = {"hit": None, "alternatives": [], "trace": trace}
    if not principal:
        return {**empty, "status": "invalid", "message": "请先录入主诊断编码。"}

    # ‘五、不纳入分组的主要诊断’按完整编码相等检查；命中即停止。
    excluded_dx = next((row for row in sheets["excluded_dx"]["rows"] if norm(rv(row, 0)) == principal), None)
    if excluded_dx:
        trace.append({"state": "blocked", "title": "主诊断排除检查",
                      "detail": f"{principal} 命中排除表第 {excluded_dx['row']} 行：{excluded_dx['v'][1]}"})
        return {**empty, "status": "excluded", "message": "主诊断属于不纳入分组的编码", "excluded": excluded_dx}
    trace.append({"state": "passed", "title": "主诊断排除检查", "detail": f"{principal} 未命中排除表"})

    # ‘五、不纳入分组的主要手术操作’也是完整编码相等；
    # 它不调用 main_operation_matches，命中后要进一步读该行说明。
    excluded_op = next((row for row in sheets["excluded_op"]["rows"] if norm(rv(row, 0)) == main), None)
    effective_main = main
    if excluded_op:
        note = rv(excluded_op, 2)
        # 保守治疗：清空‘有效主操作’，但不立即返回，后面仍逐层试规则。
        if note == "按保守治疗入组":
            effective_main = ""
            trace.append({"state": "info", "title": "主操作处理",
                          "detail": f"{main}：{note}（排除表第 {excluded_op['row']} 行）。忽略其作为主操作的分组作用，继续依次尝试先期分组、诊断辅助细分、并项规则和基础规则；不保证最终命中基础规则。"})
        # 不能作为主操作：立即返回，提示调整输入。
        elif note == "不可作为主要手术操作":
            trace.append({"state": "blocked", "title": "主操作处理",
                          "detail": f"{main}：{note}（排除表第 {excluded_op['row']} 行）"})
            return {**empty, "status": "invalid_operation", "message": f"{main} 不可作为主要手术操作"}
        else:
            # 有诊断例外的说明：提取允许的主诊断范围，无法理解时交人工核对。
            conditional = re.fullmatch(r"(.+)作为主要诊断，可作为主要手术操作", str(note), flags=re.S)
            if not conditional:
                trace.append({"state": "blocked", "title": "主操作处理",
                              "detail": f"{main} 的排除表说明为「{note}」；暂无法自动判定。"})
                return {**empty, "status": "invalid_operation", "message": f"{main} 的主操作资格需人工核对"}
            # 诊断符合例外时没有 return，代码自然往下执行；不符合才停止。
            allowed = diagnosis_matches(principal, conditional[1])
            trace.append({"state": "passed" if allowed else "blocked", "title": "主操作条件检查",
                          "detail": f"{main}：主诊断 {principal}{'满足' if allowed else '不满足'}例外范围 {norm(conditional[1])}（排除表第 {excluded_op['row']} 行）"})
            if not allowed:
                return {**empty, "status": "invalid_operation", "message": f"{main} 在当前主诊断下不可作为主要手术操作"}
    else:
        trace.append({"state": "passed", "title": "主操作处理",
                      "detail": f"{main} 未命中排除表" if main else "未填写手术操作，按保守治疗路径查找"})

    # 保留原始主操作与有效主操作：保守治疗时两者不同，排除的主操作不再参与后续匹配。
    case = {
        "principalDx": principal, "otherDx": other, "diagnoses": diagnoses,
        "mainOperation": main, "operations": operations,
        "effectiveMainOperation": effective_main,
        "effectiveOperations": operations if effective_main else [op for op in operations if op != main],
        "ageDays": _optional_number(raw_case.get("ageDays")),
        "birthWeight": _optional_number(raw_case.get("birthWeight")),
    }
    # 耐药结核编码目录供 FZ 结核分支使用。
    resistant_set = {norm(rv(row, 0)) for row in sheets["tb_resistant"]["rows"]}
    # 分层按此顺序尝试；一层有候选就停止，不再检查后面的层。
    stages = [
        ("xq", lambda: xq_candidates(sheets["xq"]["rows"], case)),
        ("fz", lambda: fz_candidates(sheets, case, resistant_set)),
        ("bx", lambda: bx_candidates(sheets["bx"]["rows"], case)),
        ("jc", lambda: jc_candidates(sheets["jc"]["rows"], case)),
    ]
    for stage, find in stages:
        candidates = find()
        title = "诊断辅助细分" if stage == "fz" else SECTION_LABEL[stage]
        if candidates:
            # 先排序选中一条，同时保留同层其余候选供界面展示。
            hit = best(candidates)
            trace.append({"state": "passed", "title": title,
                          "detail": f"命中 {len(candidates)} 条候选规则，按满足条件数选用 {hit['key']}（{hit['conditionCount']} 项条件；{sheets[hit['section']]['name']}，第 {hit['row']} 行）"})
            alternatives = sorted((item for item in candidates if item is not hit),
                                  key=candidate_rank)
            return {"status": "matched", "message": "已匹配国家 3.0 核心病种规则",
                    "hit": hit, "alternatives": alternatives, "trace": trace,
                    "grassroots": grassroots_matches(sheets["grassroots"]["rows"], case, hit),
                    "processed": case, "sourceSheetName": sheets[hit["section"]]["name"]}
        trace.append({"state": "neutral", "title": title, "detail": "未匹配到符合全部条件的规则"})
    # 四层均无完整匹配时只报告未命中，不推造未提供的综合病种。
    return {"status": "unmatched", "message": "未命中本表公布的核心病种规则",
            "hit": None, "alternatives": [], "trace": trace, "grassroots": [], "processed": case}



# ── 前端编码搜索与概况信息 ────────────────────────────────────────────
# 从 JSON 的规则行提取可单独输入的编码/名称，供输入框搜索建议使用。
def build_suggestions(data, kind):
    entries = {}

    # 复合表达式、范围和‘所有诊断’不是可直接输入的单个编码；按编码去重。
    def add(code, name):
        key = norm(code)
        if not key or any(char in key for char in "|+-") or key == "所有诊断":
            return
        if key not in entries and name:
            entries[key] = {"code": key, "name": str(name).strip()}

    sheets = data["sheets"]
    # 诊断建议来自排除表、主要规则表、基层表和耐药结核目录。
    if kind == "dx":
        for row in sheets["excluded_dx"]["rows"]:
            add(rv(row, 0), rv(row, 1))
        for section in ("bx", "jc", "fz_tumor", "fz_tb"):
            for row in sheets[section]["rows"]:
                add(rv(row, 2), rv(row, 3))
        for row in sheets["grassroots"]["rows"]:
            add(rv(row, 1), rv(row, 2))
        for row in sheets["tb_resistant"]["rows"]:
            add(rv(row, 0), rv(row, 1))
    # 操作建议来自排除表和各主要规则表；'|' 分支与名称逐个配对。
    else:
        for row in sheets["excluded_op"]["rows"]:
            add(rv(row, 0), rv(row, 1))
        for section in ("xq", "bx", "jc", "fz_tumor", "fz_tb"):
            for row in sheets[section]["rows"]:
                v = row["v"]
                code_idx = 5 if section == "xq" else 6 if section == "fz_tumor" else 4
                name_idx = 6 if section == "xq" else 7 if section == "fz_tumor" else 5
                codes = norm(rv(row, code_idx)).split("|")
                names = str(rv(row, name_idx)).split("|")
                if len(codes) == len(names):
                    for code, name in zip(codes, names):
                        add(code, name)
                else:
                    add(rv(row, code_idx), rv(row, name_idx))
    return list(entries.values())



# 汇总规则条数与编码建议，供前端初始化目录和统计信息。
def catalog(data):
    sheets = data["sheets"]
    core = sum(len(sheets[key]["rows"]) for key in ("xq", "bx", "fz_burn", "fz_tumor", "fz_tb", "jc"))
    return {"edition": data["edition"], "coreCount": core,
            "grassrootsCount": len(sheets["grassroots"]["rows"]),
            "suggestions": {"dx": build_suggestions(data, "dx"), "op": build_suggestions(data, "op")}}
