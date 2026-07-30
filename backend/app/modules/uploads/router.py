"""附件上传（图片/文档）：白名单校验 + 本地磁盘存储（DATA_DIR/uploads/）。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.core.auth import get_current_user_id
from app.core.config import DATA_DIR
from app.modules.uploads.extractor import DOC_EXTENSIONS
from app.schemas import UploadOut

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = DATA_DIR / "uploads"

MAX_SIZE = 10 * 1024 * 1024  # 10MB

# content-type -> 允许的扩展名集合（双重校验）
ALLOWED_TYPES: dict[str, set[str]] = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}


@router.post("", status_code=201)
async def upload_image(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
) -> UploadOut:
    """上传单个附件（图片或文档），返回可访问的 /uploads/ 相对 URL。

    图片按 MIME + 扩展名双重校验；文档（.pdf/文本/代码）浏览器给出的 MIME
    不可靠（text/* 或空），按原始文件名扩展名判断。

    user_id 为预留参数：多用户模式下要求登录才能上传，暂不按用户分目录。
    """
    content_type = (file.content_type or "").lower()
    ext = Path(file.filename or "").suffix.lower()
    allowed_exts = ALLOWED_TYPES.get(content_type)
    is_image = allowed_exts is not None and ext in allowed_exts
    if not is_image and ext not in DOC_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                "不支持的文件类型，支持图片（png/jpg/jpeg/webp/gif）"
                "与文档（" + "/".join(sorted(e.lstrip(".") for e in DOC_EXTENSIONS)) + "）"
            ),
        )

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10MB")
    if not data:
        raise HTTPException(status_code=422, detail="文件为空")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex
    (UPLOAD_DIR / f"{file_id}{ext}").write_bytes(data)

    return UploadOut(
        id=file_id,
        url=f"/uploads/{file_id}{ext}",
        file_name=file.filename or f"{file_id}{ext}",
        mime_type=content_type,
        size=len(data),
    )
