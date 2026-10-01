"""苗木移植接口：维护移植记录，覆盖安排移植、成活上报、移入位置处理等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.transplant import TransplantService

router = APIRouter(prefix="/api/transplant", tags=["苗木移植"])

service = TransplantService()

LIST_FIELDS = ["移植编号", "移植树种", "移植数量", "移出位置", "移入位置", "移植日期", "成活数量", "成活率", "移植状态"]
STATUSES = ["待移植", "已移植", "已成活", "已死亡"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按移植编号检索"),
    status: str | None = Query(default=None, description="待移植、已移植、已成活、已死亡"),
    location: str | None = Query(default=None, description="按归一后的移入位置筛选"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按移植编号、状态与移入位置过滤苗木移植列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, location=location, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出苗木移植清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "transplant", "total": total, "items": items}


@router.get("/stats")
def transplant_stats() -> dict[str, Any]:
    """移植成活统计：成活率与按移入位置的明细都来自共用算法，跟着明细实时重算。"""
    return service.stats()


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条移植记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"移植记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条移植记录，缺字段时说明原因；同一批苗重复登记只记一次。"""
    entry, missing, duplicate = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if duplicate:
        return ActionResult(ok=True, message="同一批苗已登记过，未重复创建", entry=entry)
    return ActionResult(ok=True, message="移植记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条移植记录执行安排移植、成活上报；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}/location", response_model=ActionResult)
def update_location(entry_id: int, payload: EntryPayload) -> ActionResult:
    """移入位置处理：归一移入位置（可同时补录移植数量），成活率随之统一重算。"""
    entry, message = service.update_location(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
