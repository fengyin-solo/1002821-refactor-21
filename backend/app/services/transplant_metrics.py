"""苗木移植成活率的唯一共用实现。

安排移植时的估算、成活上报、移入位置处理三处，以及苗木基地页面、统计看板，
都必须从这里取数，禁止各自再写一份算法，保证同一批苗、同一移入位置读到的
成活率永远是同一个值。

口径约定：
- 移入位置先归一（去首尾空白、删中间空白），再按归一结果分组；
- 移植数量缺失或无法识别时，统一补成 ``PENDING``（待补录），不允许各处自创写法；
- 成活率 = 组内已上报记录的成活数量之和 / 移植数量之和，保留一位小数百分比；
- 组内还没有任何成活上报时，成活率为待补录（安排移植时的估算也取这一份值）。
"""
from __future__ import annotations

import re
from typing import Any

# 算法版本：换算法时抬一次版本号，启动迁移会把旧版本记录重算一遍，
# 已经是当前版本的记录不重做，保证迁移只发生一次。
ALGORITHM_VERSION = "v2-2026-10-01"

PENDING = "待补录"

ID_FIELD = "移植编号"
SPECIES_FIELD = "移植树种"
QUANTITY_FIELD = "移植数量"
MOVE_OUT_FIELD = "移出位置"
MOVE_IN_FIELD = "移入位置"
DATE_FIELD = "移植日期"
SURVIVED_FIELD = "成活数量"
RATE_FIELD = "成活率"
STATUS_TEXT_FIELD = "移植状态"
VERSION_FIELD = "成活率算法版本"

_WHITESPACE = re.compile(r"\s+")


def normalize_location(value: Any) -> str:
    """移入位置归一：去首尾空白并删掉中间全部空白。

    中文地名里的空格基本都是录入噪音（“东湖 绿地”与“东湖绿地”应是同一处），
    统一去掉后再分组，保证同位置记录取到同一个成活率。
    """
    return _WHITESPACE.sub("", str(value or "").strip())


def parse_int(value: Any) -> int | None:
    """把录入值解析成非负整数；空值、小数、非数字一律视为无法识别。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value or "").strip()
    if not text or not text.isdigit():
        return None
    return int(text)


def normalize_quantity(value: Any) -> int | str:
    """移植数量归一：识别不出就按同一办法补成待补录。"""
    amount = parse_int(value)
    return amount if amount is not None else PENDING


def normalize_survived(value: Any, quantity: int | str) -> int | str:
    """成活数量归一：数量本身待补录或成活数无法识别时为待补录，并夹到 [0, 移植数量]。"""
    if not isinstance(quantity, int):
        return PENDING
    survived = parse_int(value)
    if survived is None:
        return PENDING
    return max(0, min(survived, quantity))


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """就地归一一条记录的位置、数量、成活数量与移植状态文案。"""
    row[MOVE_IN_FIELD] = normalize_location(row.get(MOVE_IN_FIELD))
    row[MOVE_OUT_FIELD] = normalize_location(row.get(MOVE_OUT_FIELD))
    row[QUANTITY_FIELD] = normalize_quantity(row.get(QUANTITY_FIELD))
    quantity = row[QUANTITY_FIELD]
    row[SURVIVED_FIELD] = normalize_survived(row.get(SURVIVED_FIELD), quantity)
    status = row.get("status")
    if status:
        row[STATUS_TEXT_FIELD] = status
    return row


def _calc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """生成只用于计算的归一副本，绝不在聚合过程中改写原始记录。"""
    return [normalize_row(dict(row)) for row in rows]


def _group_ratio(members: list[dict[str, Any]]) -> float | None:
    """组内成活率：仅统计移植数量与成活数量都已落实的记录。"""
    total = 0
    survived = 0
    for row in members:
        quantity = row.get(QUANTITY_FIELD)
        alive = row.get(SURVIVED_FIELD)
        if isinstance(quantity, int) and isinstance(alive, int):
            total += quantity
            survived += alive
    if total <= 0:
        return None
    return survived / total


def group_survival(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """按归一后的移入位置给出成活率；没有上报的位置为 None（待补录）。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in _calc_rows(rows):
        groups.setdefault(row.get(MOVE_IN_FIELD, ""), []).append(row)
    return {location: _group_ratio(members) for location, members in groups.items()}


def overall_survival(rows: list[dict[str, Any]]) -> float | None:
    """全部已上报记录的综合成活率，看板与各页面都从这里取。"""
    return _group_ratio(_calc_rows(rows))


def format_rate(ratio: float | None) -> str:
    """统一成活率展示格式；拿不到口径时显示待补录。"""
    if ratio is None:
        return PENDING
    return f"{round(ratio * 100, 1):g}%"


def refresh_rates(rows: list[dict[str, Any]]) -> None:
    """数据发生变化后重算：归一全部记录，并把同位置的同一个成活率写回每条记录。"""
    for row in rows:
        normalize_row(row)
    rates = {
        location: format_rate(ratio)
        for location, ratio in group_survival(rows).items()
    }
    for row in rows:
        row[RATE_FIELD] = rates.get(row.get(MOVE_IN_FIELD, ""), PENDING)
        row[VERSION_FIELD] = ALGORITHM_VERSION


def backfill_legacy_rows(rows: list[dict[str, Any]]) -> int:
    """一次性迁移：只重算算法版本过期的成活记录，当前版本的旧记录不重做。

    分组前先对所有记录做归一口径计算（不改版本），保证同一移入位置即使写法不一
    也汇到同一组；但只有版本过期的记录会被真正改写并打上当前版本，
    因此迁移幂等：第二次启动时没有过期记录，直接返回 0。
    """
    stale = [row for row in rows if row.get(VERSION_FIELD) != ALGORITHM_VERSION]
    if not stale:
        return 0
    for row in stale:
        normalize_row(row)
    rates = {
        location: format_rate(ratio)
        for location, ratio in group_survival(rows).items()
    }
    for row in stale:
        row[RATE_FIELD] = rates.get(row.get(MOVE_IN_FIELD, ""), PENDING)
        row[VERSION_FIELD] = ALGORITHM_VERSION
    return len(stale)


def location_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按移入位置列出成活情况，移植页与苗木基地页共用这一份结果。"""
    normalized = _calc_rows(rows)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        groups.setdefault(row.get(MOVE_IN_FIELD, ""), []).append(row)
    breakdown: list[dict[str, Any]] = []
    for location, members in groups.items():
        ratio = _group_ratio(members)
        breakdown.append({
            MOVE_IN_FIELD: location,
            "记录数": len(members),
            QUANTITY_FIELD: sum(
                m[QUANTITY_FIELD] for m in members if isinstance(m[QUANTITY_FIELD], int)
            ),
            SURVIVED_FIELD: sum(
                m[SURVIVED_FIELD]
                for m in members
                if isinstance(m[SURVIVED_FIELD], int)
            ),
            "待补录数量": sum(1 for m in members if m[QUANTITY_FIELD] == PENDING),
            RATE_FIELD: format_rate(ratio),
        })
    return breakdown
