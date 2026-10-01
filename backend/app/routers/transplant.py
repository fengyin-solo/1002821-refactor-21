"""苗木移植接口：维护移植记录，覆盖安排移植、登记移植、记录成活等动作。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.transplant import TransplantService

router = APIRouter(prefix="/api/transplant", tags=["苗木移植"])

service = TransplantService()

LIST_FIELDS = ["移植编号", "移植树种", "移植数量", "移出位置", "移入位置", "移植日期", "成活率", "移植状态"]
STATUSES = ["待移植", "已移植", "已成活", "已死亡"]


@router.get("/survival-overview")
def survival_overview() -> dict:
    """苗木基地页面与统计看板共用的成活情况：整体率值、分位置率值都跟着明细重算。"""
    return {"module": "transplant", **service.survival_overview()}


@router.get("/export")
def export_entries() -> dict:
    """导出苗木移植清单：成活率与移入位置走统一读口径，和页面上看到的完全一致。"""
    items = service.all_entries()
    return {"module": "transplant", "total": len(items), "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按移植编号检索"),
    status: str | None = Query(default=None, description="待移植、已移植、已成活、已死亡"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按移植编号与状态过滤苗木移植列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条移植记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"移植记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条移植记录，缺字段时说明原因；同一移植编号重复登记只保留第一批。"""
    entry, missing, duplicated = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if duplicated:
        return ActionResult(ok=True, message="该批苗木已登记过，沿用原有记录，不重复登记", entry=entry)
    return ActionResult(ok=True, message="移植记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条移植记录执行安排移植、登记移植、记录成活；不允许的动作会被拦下并说明原因。

    「记录成活」需要在 values 里带成活数量，成活率由共用算法回算。
    """
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
