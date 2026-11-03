"""Read the official DIP 3.0 workbook into a compact, auditable JSON snapshot.

Usage: python scripts/export_rules.py [path-to-workbook]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT.parent / "DRG_DIP" / "按病种分值（DIP）付费3.0版分组方案.xlsx"
OUTPUT = ROOT / "data" / "rules.json"


def cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def rows(sheet, start, category=None):
    result = []
    for row_number, values in enumerate(sheet.iter_rows(min_row=start, values_only=True), start):
        values = [cell(value) for value in values]
        if category and values[0] != category:
            continue
        if not values[0]:
            continue
        result.append({"row": row_number, "v": values})
    return result


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKBOOK
    if not source.is_file():
        raise SystemExit(f"Workbook not found: {source}")
    book = openpyxl.load_workbook(source, read_only=True, data_only=True)
    sheets = book.worksheets
    payload = {
        "edition": "国家 DIP 3.0 正式版",
        "source": source.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sheets": {
            "xq": {"name": sheets[0].title, "rows": rows(sheets[0], 4, "XQ")},
            "bx": {"name": sheets[1].title, "rows": rows(sheets[1], 3, "BX")},
            "fz_burn": {"name": sheets[2].title, "rows": rows(sheets[2], 4, "FZ")},
            "fz_tumor": {"name": sheets[3].title, "rows": rows(sheets[3], 3, "FZ")},
            "fz_tb": {"name": sheets[4].title, "rows": rows(sheets[4], 3, "FZ")},
            "tb_resistant": {"name": sheets[5].title, "rows": rows(sheets[5], 3)},
            "jc": {"name": sheets[6].title, "rows": rows(sheets[6], 3, "JC")},
            "excluded_dx": {"name": sheets[7].title, "rows": rows(sheets[7], 4)},
            "excluded_op": {"name": sheets[8].title, "rows": rows(sheets[8], 3)},
            "grassroots": {"name": sheets[9].title, "rows": rows(sheets[9], 3)},
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    for key, section in payload["sheets"].items():
        print(f"  {key}: {len(section['rows'])}")


if __name__ == "__main__":
    main()
