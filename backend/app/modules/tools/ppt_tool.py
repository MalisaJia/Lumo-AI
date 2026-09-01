"""create_ppt 工具：复用 ppt_master 服务生成 PPT 并提供 /uploads/ 下载链接。

分钟级耗时：分级超时 300s；自建 DB session，不与管线共享。
"""

import logging
import uuid
from typing import Any

from app.core.db import async_session_factory
from app.modules.ppt_master import service as ppt_service
from app.modules.tools.registry import tool
from app.pipeline.chat_pipeline import UPLOAD_DIR

logger = logging.getLogger(__name__)


@tool(
    name="create_ppt",
    description=(
        "制作 PPT 演示文稿文件。仅当用户明确要求制作 PPT/幻灯片/演示文稿时调用；"
        "普通问答或仅需列出大纲时不要调用。生成耗时较长（分钟级）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "PPT 主题，例如 \"人工智能的发展趋势\"",
            },
            "reference_text": {
                "type": "string",
                "description": "可选：用户提供的参考资料或要点说明原文",
            },
        },
        "required": ["topic"],
    },
    timeout=300.0,
)
async def create_ppt(ctx: Any, arguments: dict[str, Any]) -> str:
    topic = str(arguments.get("topic") or "").strip()
    if not topic:
        return "PPT 制作失败：主题为空。"
    reference_text = str(arguments.get("reference_text") or "").strip() or None

    try:
        async with async_session_factory() as session:
            data = await ppt_service.generate_ppt(
                session, ctx.user_id, topic, reference_text
            )
    except Exception as exc:
        logger.warning("create_ppt 工具执行失败 (topic=%r)：%s", topic, exc, exc_info=True)
        return f"PPT 制作失败：{exc}。请告知用户失败原因。"

    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_id = uuid.uuid4().hex
        (UPLOAD_DIR / f"{file_id}.pptx").write_bytes(data)
    except Exception as exc:
        logger.warning("PPT 产物写盘失败 (topic=%r)：%s", topic, exc, exc_info=True)
        return f"PPT 制作失败：文件保存出错（{exc.__class__.__name__}）。"

    return (
        f"PPT《{topic}》制作完成。\n"
        f"下载链接：/uploads/{file_id}.pptx\n"
        "请在回答中告知用户 PPT 已生成，并给出上面的下载链接。"
    )
