"""图片上传：多类型白名单校验 + 本地磁盘存储（backend/uploads/）。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.core.config import BACKEND_DIR
from app.schemas import UploadOut

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = BACKEND_DIR / "uploads"

MAX_SIZE = 10 * 1024 * 1024  # 10MB

# content-type -> 允许的扩展名集合（双重校验）
ALLOWED_TYPES: dict[str, set[str]] = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}


@router.post("", status_code=201)
async def upload_image(file: UploadFile) -> UploadOut:
    """上传单张图片，返回可访问的 /uploads/ 相对 URL。"""
    content_type = (file.content_type or "").lower()
    ext = Path(file.filename or "").suffix.lower()
    allowed_exts = ALLOWED_TYPES.get(content_type)
    if allowed_exts is None or ext not in allowed_exts:
        raise HTTPException(
            status_code=422,
            detail="不支持的图片类型，仅支持 png/jpg/jpeg/webp/gif",
        )

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="图片大小不能超过 10MB")
    if not data:
        raise HTTPException(status_code=422, detail="图片文件为空")

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
