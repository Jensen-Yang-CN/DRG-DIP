"""Export CHS-DRG 3.0 workbook rules and the matching reference table.

Only this export step needs openpyxl. The HTTP service reads the JSON snapshot.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source" / "按病组（DRG）付费3.0版分组方案配置信息.xlsx"
REFERENCE = ROOT / "data" / "source" / "chs_drg_30_reference.js"
DESTINATION = ROOT / "data" / "drg_rules.json"


def code(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def export() -> dict:
    book = load_workbook(SOURCE, read_only=True, data_only=True)
    sets: dict[str, set[str]] = defaultdict(set)
    diagnoses: dict[str, str] = {}
    operations: dict[str, str] = {}
    for _, (set_id, raw_code, name, kind) in enumerate(
        book["集合"].iter_rows(min_row=2, values_only=True), 2
    ):
        if not set_id or not raw_code:
            continue
        identifier, icd = str(set_id).strip(), code(raw_code)
        sets[identifier].add(icd)
        if identifier.startswith("DI_") and name:
            diagnoses.setdefault(icd, str(name).strip())
        elif identifier.startswith("OP") and name:
            operations.setdefault(icd, str(name).strip())

    mdc = [
        {"code": str(r[0]), "name": str(r[1] or "").strip(),
         "rule": str(r[2] or "").strip(), "order": int(r[3] or 999), "row": index}
        for index, r in enumerate(book["MDC"].iter_rows(min_row=3, values_only=True), 3)
        if r[0] and str(r[0]) != "0000"
    ]
    adrg = [
        {"code": str(r[1]), "name": str(r[2] or "").strip(),
         "rule": str(r[3] or "").strip(), "mdc": str(r[4] or ""),
         "order": int(r[5] or 999), "row": index}
        for index, r in enumerate(book["ADRG"].iter_rows(min_row=2, values_only=True), 2)
        if r[1] and str(r[1]) != "000"
    ]
    drg = [
        {"code": str(r[0]), "name": str(r[1] or "").strip(),
         "rule": str(r[2] or "").strip(), "adrg": str(r[3] or ""),
         "mdc": str(r[4] or ""), "order": int(r[5] or 999), "row": index}
        for index, r in enumerate(book["DRG"].iter_rows(min_row=2, values_only=True), 2)
        if r[0] and str(r[0]) != "0000"
    ]
    cc = {}
    for raw_code, name, exclusion, severity in book["CC"].iter_rows(min_row=2, values_only=True):
        if not raw_code:
            continue
        icd = code(raw_code)
        cc[icd] = {"type": str(severity or ""), "exclusion": str(exclusion or "")}
        if name:
            diagnoses.setdefault(icd, str(name).strip())
    exclusions: dict[str, set[str]] = defaultdict(set)
    for set_id, raw_code, name in book["排除表"].iter_rows(min_row=2, values_only=True):
        if set_id and raw_code:
            icd = code(raw_code)
            exclusions[str(set_id)].add(icd)
            if name:
                diagnoses.setdefault(icd, str(name).strip())
    book.close()

    source = REFERENCE.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\[\s*"([A-Z]{2}\d[A-Z0-9])"\s*,\s*"([^"]*)"\s*,\s*'
        r'"([\d.]*)"\s*,\s*"([\d.]*)"\s*,\s*"([^"]*)"\s*,?\s*\]'
    )
    reference = {
        drg_code: {"name": name, "weight": weight or None, "fee": fee or None,
                   "label": label or None}
        for drg_code, name, weight, fee, label in pattern.findall(source)
    }
    if len(reference) != 825:
        raise ValueError(f"CHS-DRG 3.0 reference table has {len(reference)} rows, expected 825")
    result = {
        "scheme": "chs_drg_30",
        "mdc": sorted(mdc, key=lambda r: r["order"]),
        "adrg": sorted(adrg, key=lambda r: (r["mdc"], r["order"])),
        "drg": sorted(drg, key=lambda r: (r["adrg"], r["order"])),
        "sets": {key: sorted(values) for key, values in sorted(sets.items())},
        "cc": cc,
        "exclusions": {key: sorted(values) for key, values in sorted(exclusions.items())},
        "diagnosisNames": diagnoses,
        "operationNames": operations,
        "reference": reference,
    }
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return result


if __name__ == "__main__":
    data = export()
    print(f"DRG: {len(data['mdc'])} MDC, {len(data['adrg'])} ADRG, "
          f"{len(data['drg'])} DRG, {len(data['reference'])} reference rows")
