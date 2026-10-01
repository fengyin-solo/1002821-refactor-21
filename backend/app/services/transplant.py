"""苗木移植业务规则：状态流转、字段校验与筛选口径都收在这里。

成活率不在本文件里另算：登记/安排/上报的估值、列表读口径、看板汇总全部走
``app.services.transplant_survival`` 里的唯一实现。
"""
from __future__ import annotations

from typing import Any

from app.services import transplant_survival as survival
from app.store import store

MODULE = "transplant"
# 移植数量允许暂时不填：登记时按统一口径补成「待补录」，后续上报成活再核实。
REQUIRED_FIELDS = ["移植编号", "移植树种"]
ALL_FIELDS = ["移植编号", "移植树种", "移植数量", "移出位置", "移入位置", "移植日期"]
STATUS_ORDER = ["待移植", "已移植", "已成活", "已死亡"]
# 记录成活携带实测成活数量，状态落到「已成活」，是正常闭环，不计异常。
ACTION_RULES = {"安排移植": "已移植", "登记移植": "已成活", "记录成活": "已成活"}
NEGATIVE_ACTIONS: list[str] = []


class TransplantService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("移植编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        # 读口径之一：列表、明细、导出都经过同一份成活率算法。
        return [survival.present_entry(row, rows) for row in page_rows], total

    def all_entries(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        return [survival.present_entry(row, rows) for row in rows]

    def survival_overview(self) -> dict[str, Any]:
        return survival.build_survival_overview(store.rows(MODULE))

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        rows = store.rows(MODULE)
        for row in rows:
            if int(row.get("id", 0)) == entry_id:
                return survival.present_entry(row, rows)
        return None

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], bool]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        rows = store.rows(MODULE)
        code = str(values.get("移植编号") or "").strip()
        # 同一批苗重复登记只记一次：按移植编号去重，已存在直接返回原记录。
        for row in rows:
            if str(row.get("移植编号") or "").strip() == code:
                return survival.present_entry(row, rows), [], True
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            raw = values.get(field)
            if field == "移植数量":
                entry[field] = survival.normalize_quantity(raw)
            elif field == "移入位置":
                entry[field] = survival.normalize_location(raw)
            else:
                entry[field] = raw
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        # 读口径之二：安排移植时的预估成活率也取共用算法，与列表里显示的一致。
        return survival.present_entry(entry, rows), [], False

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"移植记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于苗木移植可执行范围"
        rows = store.rows(MODULE)
        if action == "记录成活":
            if survival.parse_survived(entry.get("成活数量")) is not None:
                return None, "该批苗木已上报过成活情况，不能重复上报"
            survived_count = survival.parse_survived((values or {}).get("成活数量"))
            if survived_count is None:
                return None, "成活数量必须是不小于 0 的整数，请核实后重新上报"
            quantity = survival.normalize_quantity(entry.get("移植数量"))
            if not isinstance(quantity, int):
                return None, "移植数量仍是「待补录」，请先补录移植数量再上报成活"
            if survived_count > quantity:
                return None, f"成活数量 {survived_count} 不能超过移植数量 {quantity}"
            entry["成活数量"] = survived_count
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        # 读口径之三：成活上报后回算成活率，仍走共用算法。
        return survival.present_entry(entry, rows), f"移植记录已{action}"
