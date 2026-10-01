"""苗木移植成活率的唯一口径。

以前成活率分别在「安排移植时预估」「成活上报」「移入位置处理」三个地方各算各的，
同一批苗给出的数对不上。现在把算法收拢到本模块，所有读数据的地方（移植明细列表、
苗木基地页面的移入位置成活情况、运营概览看板）都从这里取值，保证：

* 移入位置先做归一化，同一个位置只对应一个成活率；
* 移植数量缺失或无法识别时统一补成「待补录」，不参与率值计算；
* 算法本身以后调整时，所有读口径自动重算，不需要重做历史记录；
* 同一批苗（同一移植编号）重复登记只计一次。

读口径统一返回百分比文本（保留 1 位小数，如 ``83.3%``），数量待补录时返回
``待补录``。看板用的明细重算汇总走 :func:`build_survival_overview`。
"""
from __future__ import annotations

from typing import Any

# 没有任何已上报数据可参考时，安排移植阶段的默认预估成活率。
DEFAULT_ESTIMATE_RATE = 95.0
# 移植数量没填或填了无法识别的内容时，按这一处统一补录。
PENDING_QUANTITY_TEXT = "待补录"
# 移入位置为空时归一化后的占位名称。
UNSPECIFIED_LOCATION = "未指定移入位置"


def normalize_location(value: Any) -> str:
    """归一化移入位置：去首尾空白、全角转半角、剔除位置内全部空格，空值归到同一占位名。

    例如 ``" 中心绿地　A区 "`` 与 ``"中心绿地A区"`` 视为同一个位置，读到同一个成活率。
    """
    text = str(value or "").replace("　", " ").strip()
    if not text:
        return UNSPECIFIED_LOCATION
    return "".join(text.split())


def normalize_quantity(value: Any) -> Any:
    """归一化移植数量：识别不出正整数时统一补成「待补录」，能识别就返回整数。"""
    if isinstance(value, bool):
        return PENDING_QUANTITY_TEXT
    if isinstance(value, int):
        return value if value > 0 else PENDING_QUANTITY_TEXT
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    text = str(value or "").strip()
    if text.isdigit() and int(text) > 0:
        return int(text)
    return PENDING_QUANTITY_TEXT


def parse_survived(value: Any) -> int | None:
    """解析成活上报里的成活数量，非法或非正数返回 None 由上层报错。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return None


def format_rate(rate: float) -> str:
    """把 0~100 的率值格式化成统一的百分比文本。"""
    return f"{round(rate, 1):.1f}%"


def location_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
    """按归一后的移入位置，用已上报成活的明细重算每个位置的成活率。

    同一移植编号重复登记时只取第一条，避免同一批苗被重复计数；数量为「待补录」
    的记录不进入分母。任何位置只要存在可算的明细，就一定有对应率值。
    """
    seen_codes: set[str] = set()
    totals: dict[str, int] = {}
    survived: dict[str, int] = {}
    for row in rows:
        code = str(row.get("移植编号") or "").strip()
        if code:
            if code in seen_codes:
                continue
            seen_codes.add(code)
        if parse_survived(row.get("成活数量")) is None:
            continue
        quantity = normalize_quantity(row.get("移植数量"))
        if not isinstance(quantity, int):
            continue
        survived_count = parse_survived(row.get("成活数量")) or 0
        location = normalize_location(row.get("移入位置"))
        totals[location] = totals.get(location, 0) + quantity
        survived[location] = survived.get(location, 0) + survived_count
    return {
        location: min(survived[location] / totals[location] * 100, 100.0)
        for location in totals
        if totals[location] > 0
    }


def estimate_rate(rows: list[dict[str, Any]], location: Any) -> float:
    """安排移植时的预估成活率：优先取同位置实测，其次全局实测，都没有用默认值。"""
    rates = location_rates(rows)
    key = normalize_location(location)
    if key in rates:
        return rates[key]
    if rates:
        return round(sum(rates.values()) / len(rates), 1)
    return DEFAULT_ESTIMATE_RATE


def present_entry(row: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """统一读口径：复制一条移植记录，补上归一位置与所有页面一致的成活率。

    * 数量待补录：成活率显示「待补录」；
    * 已上报成活数量：用本批实测（存活/移植），上限 100%；
    * 尚未上报：同位置取同一个预估数（同位置实测 → 全局实测 → 默认值）。
    """
    view = dict(row)
    view["移入位置"] = normalize_location(row.get("移入位置"))
    quantity = normalize_quantity(row.get("移植数量"))
    view["移植数量"] = quantity
    if not isinstance(quantity, int):
        view["成活率"] = PENDING_QUANTITY_TEXT
        return view
    survived_count = parse_survived(row.get("成活数量"))
    if survived_count is not None:
        rate = min(survived_count / quantity * 100, 100.0)
    else:
        rate = estimate_rate(rows, row.get("移入位置"))
    view["成活率"] = format_rate(rate)
    return view


def build_survival_overview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """看板与苗木基地页面共用的成活情况汇总，全部跟着明细重算。

    返回整体指标、按归一位置分组的成活率、以及各状态的批次数。重复登记的同批苗
    在整体率值里只计一次；没有可算明细时整体率值回落到默认预估。
    """
    presented = [present_entry(row, rows) for row in rows]
    rates = location_rates(rows)

    seen_codes: set[str] = set()
    total_quantity = 0
    reported_quantity = 0
    reported_batches = 0
    total_survived = 0
    for row in rows:
        code = str(row.get("移植编号") or "").strip()
        if code:
            if code in seen_codes:
                continue
            seen_codes.add(code)
        quantity = normalize_quantity(row.get("移植数量"))
        if isinstance(quantity, int):
            total_quantity += quantity
        survived_count = parse_survived(row.get("成活数量"))
        if survived_count is None or not isinstance(quantity, int):
            continue
        reported_quantity += quantity
        reported_batches += 1
        total_survived += survived_count

    if reported_quantity > 0:
        overall_rate = min(total_survived / reported_quantity * 100, 100.0)
    elif rates:
        overall_rate = round(sum(rates.values()) / len(rates), 1)
    else:
        overall_rate = DEFAULT_ESTIMATE_RATE

    locations = [
        {
            "移入位置": location,
            "成活率": format_rate(rates[location]),
        }
        for location in sorted(rates)
    ]
    codes = [str(row.get("移植编号") or "").strip() for row in rows]
    codes = [code for code in codes if code]
    duplicate_batches = len(codes) - len(set(codes))
    status_counts = {
        status: sum(1 for row in rows if row.get("status") == status)
        for status in ["待移植", "已移植", "已成活", "已死亡"]
    }
    return {
        "overallRate": format_rate(overall_rate),
        "totalQuantity": total_quantity,
        "reportedBatches": reported_batches,
        "pendingQuantityBatches": sum(
            1 for row in presented if row["移植数量"] == PENDING_QUANTITY_TEXT
        ),
        "duplicateBatches": duplicate_batches,
        "statusCounts": status_counts,
        "locations": locations,
    }
