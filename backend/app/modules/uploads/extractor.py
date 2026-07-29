"""附件文档文本抽取：PDF 用 pypdf 逐页抽取，文本/代码文件按编码回退解码。"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 文档类附件扩展名白名单（与前端共享契约，须保持一致）
DOC_EXTENSIONS: set[str] = {
    ".pdf", ".txt", ".md", ".markdown",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css",
    ".json", ".yaml", ".yml", ".xml", ".sql", ".sh", ".csv", ".log",
}

# 单文件注入上限（字符）；超出截断并追加提示
MAX_CHARS_PER_FILE = 20000
# 单条消息内多文件合计注入上限（字符）；超出后停止注入后续文件
MAX_CHARS_PER_MESSAGE = 50000
TRUNCATED_SUFFIX = "\n……(文件内容过长，已截断)"


def extract_text(file_path: Path, file_name: str) -> str | None:
    """抽取文档文本；超长按 MAX_CHARS_PER_FILE 截断；解析失败返回 None。"""
    try:
        if not file_path.is_file():
            logger.warning("文档附件文件不存在：%s", file_name)
            return None
        ext = Path(file_name).suffix.lower() or file_path.suffix.lower()
        if ext == ".pdf":
            text = _extract_pdf(file_path)
        else:
            text = _decode_bytes(file_path.read_bytes())
        if text is None:
            return None
        if len(text) > MAX_CHARS_PER_FILE:
            text = text[:MAX_CHARS_PER_FILE] + TRUNCATED_SUFFIX
        return text
    except Exception:
        logger.warning("文档附件文本抽取失败：%s", file_name, exc_info=True)
        return None


def _extract_pdf(file_path: Path) -> str | None:
    """pypdf 逐页抽取拼接；解析异常返回 None。"""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(file_path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        return "\n".join(pages)
    except Exception:
        logger.warning("PDF 解析失败：%s", file_path.name, exc_info=True)
        return None


def _decode_bytes(raw: bytes) -> str:
    """文本解码：utf-8 优先，失败退 gbk，再失败 utf-8 + errors=replace。"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")
