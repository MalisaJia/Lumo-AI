"""AI 制作 PPT API：POST /api/ppt/generate -> pptx 二进制。"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.pipeline.chat_pipeline import PipelineError
from app.schemas import CamelModel

from .service import PptGenerationError, generate_ppt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ppt", tags=["ppt"])

MAX_TOPIC_CHARS = 200
MAX_REFERENCE_CHARS = 50_000


class PptGenerateRequest(CamelModel):
    topic: str
    reference_text: str | None = None
    template: str | None = None


@router.post("/generate")
async def generate(
    body: PptGenerateRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
) -> Response:
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic 不能为空")
    if len(topic) > MAX_TOPIC_CHARS:
        raise HTTPException(status_code=422, detail="主题过长，请精简后重试")
    if body.reference_text and len(body.reference_text) > MAX_REFERENCE_CHARS:
        raise HTTPException(status_code=422, detail="参考资料过长，请精简后重试")

    # 管线内部：LLM 调用为 async，PPT Master 子进程已在线程池执行，不阻塞事件循环
    try:
        pptx_bytes = await generate_ppt(
            session, user_id, topic, body.reference_text, body.template
        )
    except PipelineError as exc:
        # 未配置服务商/模型、Key 解密失败、上游报错等：用户可自行处理，归 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PptGenerationError as exc:
        logger.warning("PPT 生成失败：%s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = f"{topic[:50]}.pptx"
    return Response(
        content=pptx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )
