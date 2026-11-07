"""工作区文件浏览 API。"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.modules.tools.sandbox import validate_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])

# Directories and files to hide from tree listing
_HIDDEN_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    ".env",
    ".DS_Store",
    "Thumbs.db",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".nuxt",
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB


class FileEntry(BaseModel):
    name: str
    type: str  # "file" or "dir"
    size: int | None = None


class FileContent(BaseModel):
    content: str
    lineCount: int
    language: str


class FileSaveRequest(BaseModel):
    path: str
    content: str


def _detect_language(filename: str) -> str:
    """Detect language from file extension for syntax highlighting."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".jsx": "javascriptreact",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
        ".ps1": "powershell",
        ".bat": "bat",
        ".xml": "xml",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".dart": "dart",
        ".vue": "vue",
        ".svelte": "svelte",
        ".ini": "ini",
        ".cfg": "ini",
        ".txt": "plaintext",
        ".log": "plaintext",
    }
    suffix = Path(filename).suffix.lower()
    return ext_map.get(suffix, "plaintext")


def _validate_workspace_path(path_str: str) -> Path:
    """Validate a path is within the workspace. Raises HTTPException on failure."""
    error = validate_path(path_str)
    if error:
        raise HTTPException(status_code=403, detail=error)
    return Path(path_str).resolve()


@router.get("/tree", response_model=list[FileEntry])
async def list_directory(
    path: str = Query(..., description="Directory path to list"),
):
    """列出目录内容（1 层深度），自动过滤隐藏目录。"""
    resolved = _validate_workspace_path(path)

    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录：{path}")

    entries: list[FileEntry] = []
    try:
        for item in sorted(
            resolved.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())
        ):
            if item.name in _HIDDEN_NAMES or item.name.startswith("."):
                continue
            if item.is_dir():
                entries.append(FileEntry(name=item.name, type="dir"))
            elif item.is_file():
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
                entries.append(FileEntry(name=item.name, type="file", size=size))
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"无权限访问目录：{path}")

    return entries


@router.get("/file", response_model=FileContent)
async def read_file(
    path: str = Query(..., description="File path to read"),
):
    """读取文件内容（纯文本），512KB 上限。"""
    resolved = _validate_workspace_path(path)

    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"路径不是文件：{path}")

    if resolved.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大（超过 512KB），不支持在 IDE 中查看")

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取文件失败：{exc}")

    line_count = content.count("\n") + (1 if content else 0)
    language = _detect_language(resolved.name)

    return FileContent(content=content, lineCount=line_count, language=language)


@router.put("/file")
async def save_file(body: FileSaveRequest):
    """保存文件内容。"""
    resolved = _validate_workspace_path(body.path)

    # Ensure parent directory exists
    resolved.parent.mkdir(parents=True, exist_ok=True)

    try:
        resolved.write_text(body.content, encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存文件失败：{exc}")

    return {"status": "ok", "path": str(resolved)}


@router.get("/pick-folder")
async def pick_folder():
    """Open a native folder selection dialog for local development."""
    import asyncio

    def _show_dialog():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title="选择工作区目录")
        root.destroy()
        return folder or None

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _show_dialog)
    return {"path": result}
