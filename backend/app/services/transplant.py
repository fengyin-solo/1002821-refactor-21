"""苗木移植业务规则：状态流转、字段校验、去重登记与成活情况都收在这里。

成活率的算法本身不在这里，而是统一走 ``app.services.transplant_metrics``：
安排移植时的估算、成活上报、移入位置处理三处都调同一份实现。
"""
from __future__ import annotations

from typing import Any

from app.services import transplant_metrics as metrics
from app.store import store

MODULE = "transplant"
REQUIRED_FIELDS = ["移植编号", "移植树种"]
OPTIONAL_FIELDS = [
    metrics.QUANTITY_FIELD,
    metrics.MOVE_OUT_FIELD,
    metrics.MOVE_IN_FIELD,
    metrics.DATE_FIELD,
]
STATUS_ORDER = ["待移植", "已移植", "已成活", "已死亡"]
# 成活上报是正式名称；记录成活、登记移植为历史按钮的兼容别名。
ACTION_RULES = {
    "安排移植": "已移植",
    "成活上报": "已成活",
    "记录成活": "已成活",
    "登记移植": "已成活",
    "标记死亡": "已死亡",
}
NEGATIVE_ACTIONS = ["标记死亡"]


class TransplantService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        location: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("移植编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if location:
            target = metrics.normalize_location(location)
            rows = [
                row for row in rows
                if metrics.normalize_location(row.get(metrics.MOVE_IN_FIELD)) == target
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记移植记录。

        返回（记录, 缺失字段, 是否命中重复）。同一批苗（移植编号相同，忽略空白差异）
        重复登记时只保留第一次的记录，不新建第二条。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, False
        code = str(values.get("移植编号") or "").strip()
        rows = store.rows(MODULE)
        for row in rows:
            if str(row.get("移植编号") or "").strip() == code:
                return row, [], True
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["移植编号"] = code
        entry["移植树种"] = str(values.get("移植树种") or "").strip()
        for field in OPTIONAL_FIELDS:
            entry[field] = values.get(field)
        entry[metrics.SURVIVED_FIELD] = values.get(metrics.SURVIVED_FIELD)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        # 统一之后新建记录也按同一口径归一、估算成活率。
        metrics.refresh_rates(rows)
        return entry, [], False

    def update_location(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """移入位置处理：位置与数量都先归一，再用共用实现重算相关记录的成活率。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"移植记录 {entry_id} 不存在或已归档"
        if metrics.MOVE_IN_FIELD in values:
            entry[metrics.MOVE_IN_FIELD] = metrics.normalize_location(values.get(metrics.MOVE_IN_FIELD))
        if metrics.MOVE_OUT_FIELD in values:
            entry[metrics.MOVE_OUT_FIELD] = metrics.normalize_location(values.get(metrics.MOVE_OUT_FIELD))
        # 移植数量在位置处理时补录也按同一办法归一，并重新夹成活数量。
        if metrics.QUANTITY_FIELD in values:
            entry[metrics.QUANTITY_FIELD] = metrics.normalize_quantity(values.get(metrics.QUANTITY_FIELD))
            entry[metrics.SURVIVED_FIELD] = metrics.normalize_survived(
                entry.get(metrics.SURVIVED_FIELD), entry[metrics.QUANTITY_FIELD]
            )
        metrics.refresh_rates(store.rows(MODULE))
        return entry, "移入位置已处理，成活率已按统一算法重算"

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"移植记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于苗木移植可执行范围"
        values = values or {}

        # 安排移植：估一次成活率，估算口径就是共用算法（同位置已有上报就取同一值）。
        if action == "安排移植":
            if entry["status"] != STATUS_ORDER[0]:
                return None, "仅待移植的记录可以安排移植"
            if metrics.MOVE_IN_FIELD in values:
                entry[metrics.MOVE_IN_FIELD] = metrics.normalize_location(values.get(metrics.MOVE_IN_FIELD))
        # 成活上报：成活数量在此录入，随后同位置记录一起重算。
        elif action in ("成活上报", "记录成活", "登记移植"):
            if entry["status"] not in ("待移植", "已移植"):
                return None, "当前状态不允许上报成活情况"
            quantity = metrics.normalize_quantity(entry.get(metrics.QUANTITY_FIELD))
            entry[metrics.QUANTITY_FIELD] = quantity
            if quantity == metrics.PENDING:
                return None, "移植数量待补录，请先在移入位置处理中补全数量后再上报成活"
            if metrics.SURVIVED_FIELD not in values:
                return None, "成活上报需要成活数量"
            entry[metrics.SURVIVED_FIELD] = metrics.normalize_survived(
                values.get(metrics.SURVIVED_FIELD), quantity
            )
            if metrics.MOVE_IN_FIELD in values:
                entry[metrics.MOVE_IN_FIELD] = metrics.normalize_location(values.get(metrics.MOVE_IN_FIELD))
        # 标记死亡：整批未成活，按零纳入统一口径。
        elif action == "标记死亡":
            if entry["status"] == STATUS_ORDER[-1]:
                return None, "该记录已标记死亡"
            entry[metrics.SURVIVED_FIELD] = 0

        target = ACTION_RULES[action]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        metrics.refresh_rates(store.rows(MODULE))
        return entry, f"移植记录已{action}"

    # ---- 看板与其他页面共用的统计口径 ----

    def stats(self) -> dict[str, Any]:
        rows = store.rows(MODULE)
        by_status = {status: 0 for status in STATUS_ORDER}
        for row in rows:
            by_status[str(row.get("status"))] = by_status.get(str(row.get("status")), 0) + 1
        return {
            "total": len(rows),
            "by_status": by_status,
            "survival_rate": metrics.format_rate(metrics.overall_survival(rows)),
            "locations": metrics.location_breakdown(rows),
        }
