"""将 DIP 3.0 工作簿导出为保留原表名与行号的 JSON 规则快照。

用法：python scripts/export_rules.py [工作簿路径]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "data" / "source" / "按病种分值（DIP）付费3.0版分组方案.xlsx"
OUTPUT = ROOT / "data" / "rules.json"


def cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def rows(sheet, start, category=None, operation_code_column=False):
    result = []
    for row_number, raw_values in enumerate(sheet.iter_rows(min_row=start, values_only=True), start):
        values = list(raw_values)
        # 操作排除表的编码列有数值单元格 33.24；按该列的六位操作编码粒度补齐为 33.2400。
        if operation_code_column and isinstance(values[0], (int, float)):
            values[0] = f"{values[0]:.4f}"
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
    # 用工作表名称定位，避免用户调整表顺序后将肿瘤与烧伤规则导反。
    sheets = {sheet.title: sheet for sheet in book.worksheets}
    payload = {
        "edition": "国家 DIP 3.0 正式版",
        "source": source.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sheets": {
            "xq": {"name": sheets["一、先期分组"].title, "rows": rows(sheets["一、先期分组"], 4, "XQ")},
            "bx": {"name": sheets["二、并项规则下的核心病种"].title, "rows": rows(sheets["二、并项规则下的核心病种"], 3, "BX")},
            "fz_burn": {"name": sheets["三、诊断辅助细分-烧伤类病种"].title, "rows": rows(sheets["三、诊断辅助细分-烧伤类病种"], 4, "FZ")},
            "fz_tumor": {"name": sheets["三、诊断辅助细分-肿瘤类病种"].title, "rows": rows(sheets["三、诊断辅助细分-肿瘤类病种"], 3, "FZ")},
            "fz_tb": {"name": sheets["三、诊断辅助细分-结核类病种"].title, "rows": rows(sheets["三、诊断辅助细分-结核类病种"], 3, "FZ")},
            "tb_resistant": {"name": sheets["附表—结核耐药诊断"].title, "rows": rows(sheets["附表—结核耐药诊断"], 3)},
            "jc": {"name": sheets["四、基础规则下的核心病种"].title, "rows": rows(sheets["四、基础规则下的核心病种"], 3, "JC")},
            "excluded_dx": {"name": sheets["五、不纳入分组的主要诊断"].title, "rows": rows(sheets["五、不纳入分组的主要诊断"], 4)},
            "excluded_op": {"name": sheets["五、不纳入分组的主要手术操作"].title, "rows": rows(sheets["五、不纳入分组的主要手术操作"], 3, operation_code_column=True)},
            "grassroots": {"name": sheets["六、基层病种"].title, "rows": rows(sheets["六、基层病种"], 3)},
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    for key, section in payload["sheets"].items():
        print(f"  {key}: {len(section['rows'])}")


if __name__ == "__main__":
    main()
