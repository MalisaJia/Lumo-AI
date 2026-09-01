"""会话导出 API：POST /api/conversations/{id}/export?format=pdf|pptx。"""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.conversations import service as conv_service
from app.modules.uploads.router import UPLOAD_DIR

from .service import generate_pdf, generate_pptx

router = APIRouter(prefix="/api/conversations", tags=["export"])

MAX_EXPORT_MESSAGES = 2000


@router.post("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: Literal["pdf", "pptx"] = Query(...),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    conv = await conv_service.get_conversation(session, conversation_id, user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = await conv_service.list_messages(session, conversation_id)
    if not messages:
        raise HTTPException(status_code=400, detail="会话为空，无法导出")
    if len(messages) > MAX_EXPORT_MESSAGES:
        raise HTTPException(
            status_code=400, detail=f"消息过多({len(messages)}条)，请缩短后重试"
        )

    # 文件生成是纯 CPU 同步逻辑，放线程池避免阻塞事件循环
    if format == "pdf":
        buf = await run_in_threadpool(generate_pdf, conv, messages, UPLOAD_DIR)
        media_type = "application/pdf"
        ext = "pdf"
    else:
        buf = await run_in_threadpool(generate_pptx, conv, messages, UPLOAD_DIR)
        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        ext = "pptx"

    filename = f"{conv.title[:50]}.{ext}"
    return Response(
        content=buf.getvalue(),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
