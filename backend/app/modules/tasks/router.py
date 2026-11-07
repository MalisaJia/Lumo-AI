"""任务管理 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.tasks.manager import TaskManager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    id: str
    conversation_id: str
    parent_task_id: str | None
    description: str
    status: str
    result: str | None
    agent_run_id: str | None
    priority: int

    class Config:
        from_attributes = True


class CreateTaskRequest(BaseModel):
    conversation_id: str
    description: str
    parent_task_id: str | None = None
    blocked_by: list[str] | None = None
    priority: int = 0


class UpdateTaskRequest(BaseModel):
    status: str | None = None
    result: str | None = None


@router.post("", response_model=TaskResponse)
async def create_task(
    body: CreateTaskRequest, db: AsyncSession = Depends(get_session)
):
    mgr = TaskManager(db)
    task = await mgr.create_task(
        conversation_id=body.conversation_id,
        description=body.description,
        parent_task_id=body.parent_task_id,
        blocked_by=body.blocked_by,
        priority=body.priority,
    )
    await db.commit()
    return task


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    conversation_id: str = Query(...),
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    mgr = TaskManager(db)
    return await mgr.list_tasks(conversation_id, status)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session)):
    mgr = TaskManager(db)
    task = await mgr.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    body: UpdateTaskRequest,
    db: AsyncSession = Depends(get_session),
):
    mgr = TaskManager(db)
    task = await mgr.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if body.status is not None or body.result is not None:
        task = await mgr.update_task_status(
            task_id,
            body.status if body.status is not None else task.status,
            body.result,
        )
    await db.commit()
    return task


@router.delete("/{task_id}")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_session)):
    mgr = TaskManager(db)
    task = await mgr.cancel_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await db.commit()
    return {"status": "cancelled", "task_id": task_id}
