"""AI 制作 PPT 管线：LLM 生成 SVG -> PPT Master 校验/修复 -> 转换为原生 PPTX。

复用现有 provider 基础设施：模型选择与 Key 解密走 ChatPipeline.select_model，
LLM 调用走 ChatPipeline.call_provider（流式聚合，SVG 输出较长，流式可避免
非流式长响应的读超时）。PPT Master 以子进程方式调用其独立 venv 的 python。
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR
from app.modules.ppt_master import prompts
from app.pipeline.chat_pipeline import ChatContext, ChatPipeline

logger = logging.getLogger(__name__)

# PPT Master 安装位置：环境变量 PPT_MASTER_HOME 可覆盖，
# 默认为项目根目录（仓库根 = backend/ 的上一级）下的 ppt-master/
PPT_MASTER_HOME = Path(
    os.environ.get("PPT_MASTER_HOME") or str(BACKEND_DIR.parent / "ppt-master")
)
PPT_MASTER_PYTHON = PPT_MASTER_HOME / ".venv" / "Scripts" / "python.exe"
PPT_MASTER_SCRIPTS = PPT_MASTER_HOME / "skills" / "ppt-master" / "scripts"

# 每个 PPT Master 子进程步骤的超时（秒）
SUBPROCESS_TIMEOUT = 120

MIN_PAGES = 2
MAX_PAGES = 12


class PptGenerationError(Exception):
    """携带用户可读中文错误说明的 PPT 生成异常。"""


# ---------------------------------------------------------------------------
# LLM：生成与修复 SVG（复用 ChatPipeline 的模型选择/Key 解密/流式调用）
# ---------------------------------------------------------------------------


async def _resolve_llm(session: AsyncSession, user_id: str) -> tuple[ChatPipeline, ChatContext]:
    """复用 ChatPipeline.select_model 解析默认 Provider/Model 并解密 Key。"""
    pipeline = ChatPipeline(session)
    ctx = ChatContext(conversation_id="", user_id=user_id)
    await pipeline.select_model(ctx)  # 未配置时抛 PipelineError（中文提示）
    return pipeline, ctx


async def _call_llm(
    pipeline: ChatPipeline, ctx: ChatContext, messages: list[dict[str, str]]
) -> str:
    """以流式方式调用上游并聚合完整文本（复用 call_provider 及其错误处理）。"""
    ctx.history = messages
    ctx.response_text = ""
    async for _ in pipeline.call_provider(ctx):
        pass
    return ctx.response_text


# 完整 <svg>...</svg> 块（非贪婪）；LLM 约定每页前输出 <!-- PAGE n --> 分隔，
# 解析端直接按 svg 块切分，对围栏/注释缺失均免疫
_SVG_BLOCK_RE = re.compile(r"<svg\b[\s\S]*?</svg>", re.IGNORECASE)


def _split_svg_pages(raw: str) -> list[str]:
    """从 LLM 输出中解析出每页完整 SVG；尾部截断的不完整块自然被丢弃。"""
    return [m.group(0).strip() for m in _SVG_BLOCK_RE.finditer(raw or "")]


def _page_file_name(index: int, total: int) -> str:
    """svg_output 命名：两位序号 + 角色 slug（01_cover / 02_content / NN_end）。"""
    if index == 0:
        slug = "cover"
    elif index == total - 1:
        slug = "end"
    else:
        slug = "content"
    return f"{index + 1:02d}_{slug}.svg"


# ---------------------------------------------------------------------------
# PPT Master 子进程封装
# ---------------------------------------------------------------------------


def _run_ppt_master(
    script: str, args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess:
    """在 PPT Master 独立 venv 中运行脚本；仅超时/无法启动时抛错，
    非零退出码交由调用方按步骤语义处理。"""
    cmd = [str(PPT_MASTER_PYTHON), str(PPT_MASTER_SCRIPTS / script), *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise PptGenerationError(f"PPT 转换步骤超时（{script}）") from exc
    except OSError as exc:
        raise PptGenerationError(
            "PPT Master 环境不可用，请检查 PPT_MASTER_HOME 配置"
        ) from exc
    logger.info(
        "ppt-master %s exit=%d stdout_tail=%s stderr_tail=%s",
        script, proc.returncode, proc.stdout[-400:], proc.stderr[-400:],
    )
    return proc


def _init_project(work_dir: Path) -> Path:
    """project_manager.py init：项目建在 work_dir/projects/ 下，从输出解析实际路径。"""
    proc = _run_ppt_master(
        "project_manager.py",
        ["init", "lumo_ppt", "--format", "ppt169", "--quick-generate"],
        cwd=work_dir,
    )
    if proc.returncode != 0:
        raise PptGenerationError("初始化 PPT 项目失败")
    match = re.search(r"Project initialized:\s*(.+)", proc.stdout)
    if match:
        project = Path(match.group(1).strip())
        if project.is_dir():
            return project
    # 兜底：init 固定建在 <cwd>/projects/ 下
    candidates = sorted((work_dir / "projects").glob("lumo_ppt_*"))
    if candidates:
        return candidates[0]
    raise PptGenerationError("初始化 PPT 项目失败：未找到项目目录")


def _run_checker(project: Path) -> dict:
    """svg_quality_checker.py --json：返回 {文件名: [错误消息]}，全过则为空 dict。

    有错误时 checker 以非零码退出，属预期，不视为致命。
    """
    _run_ppt_master(
        "svg_quality_checker.py",
        [str(project), "--quick-generate", "--stage", "final", "--json"],
    )
    report_path = project / "validation" / "svg_quality_report.json"
    if not report_path.is_file():
        raise PptGenerationError("SVG 质量检查失败：未生成检查报告")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures: dict[str, list[str]] = {}
    for item in report.get("files") or []:
        errors = item.get("errors") or []
        if errors:
            failures[str(item.get("file"))] = [
                e.get("message") if isinstance(e, dict) else str(e) for e in errors
            ]
    return failures


def _export_pptx(project: Path) -> bytes:
    """svg_to_pptx.py --quick-generate：导出并读回 pptx 字节。"""
    out_path = project / "exports" / "lumo_ppt.pptx"
    proc = _run_ppt_master(
        "svg_to_pptx.py",
        [str(project), "--quick-generate", "-o", str(out_path), "-t", "fade"],
    )
    if proc.returncode != 0 or not out_path.is_file():
        raise PptGenerationError("SVG 转换 PPTX 失败，请稍后重试")
    return out_path.read_bytes()


# ---------------------------------------------------------------------------
# 主管线
# ---------------------------------------------------------------------------

# 修复回调：(文件名, 原 SVG, 错误列表) -> 修复后 SVG 或 None
RepairFn = Callable[[str, str, list[str]], Awaitable[str | None]]


async def _convert_pages_to_pptx(
    pages: list[str], repair_fn: RepairFn | None = None
) -> bytes:
    """步骤 b-d：临时目录建项目 -> 写 SVG -> 校验(+1 轮修复) -> 导出 pptx。

    修复后仍不合格的页面直接剔除继续（导出器要求检查报告全过），
    全部页面均不合格才失败。
    """
    work_dir = Path(tempfile.mkdtemp(prefix="lumo_ppt_"))
    try:
        project = await run_in_threadpool(_init_project, work_dir)
        svg_dir = project / "svg_output"
        svg_dir.mkdir(parents=True, exist_ok=True)
        total = len(pages)
        for i, svg in enumerate(pages):
            (svg_dir / _page_file_name(i, total)).write_text(svg, encoding="utf-8")

        failures = await run_in_threadpool(_run_checker, project)
        if failures and repair_fn is not None:
            logger.info("SVG 质量检查未通过页面：%s，尝试 1 轮 LLM 修复", list(failures))
            for file_name, errors in failures.items():
                svg_path = svg_dir / file_name
                try:
                    fixed = await repair_fn(
                        file_name, svg_path.read_text(encoding="utf-8"), errors
                    )
                except Exception:
                    logger.warning("LLM 修复页面 %s 失败，保留原文件", file_name, exc_info=True)
                    continue
                if fixed:
                    svg_path.write_text(fixed, encoding="utf-8")
            failures = await run_in_threadpool(_run_checker, project)

        if failures:
            # 容忍策略：剔除仍不合格页面后重跑检查（导出器要求报告与源指纹一致）
            logger.warning("修复后仍不合格，剔除页面：%s", list(failures))
            for file_name in failures:
                (svg_dir / file_name).unlink(missing_ok=True)
            if not any(svg_dir.glob("*.svg")):
                raise PptGenerationError("生成的所有页面均未通过质量检查，请重试")
            failures = await run_in_threadpool(_run_checker, project)
            if failures:
                raise PptGenerationError("SVG 质量检查未通过，请重试")

        return await run_in_threadpool(_export_pptx, project)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def generate_ppt(
    session: AsyncSession,
    user_id: str,
    topic: str,
    reference_text: str | None = None,
    template: str | None = None,
) -> bytes:
    """完整管线：LLM 生成全部页面 SVG -> PPT Master 校验/转换 -> pptx bytes。

    template 参数暂未使用（预留给前端模板选择），品牌风格由 prompt 固定。
    """
    if not PPT_MASTER_PYTHON.is_file():
        raise PptGenerationError(
            "未找到 PPT Master 环境，请检查 PPT_MASTER_HOME 配置"
        )

    pipeline, ctx = await _resolve_llm(session, user_id)
    logger.info(
        "PPT 生成开始：topic=%r model=%s referenceText=%d 字",
        topic, ctx.model_name, len(reference_text or ""),
    )
    raw = await _call_llm(
        pipeline,
        ctx,
        [
            {"role": "system", "content": prompts.SVG_SYSTEM_PROMPT},
            {"role": "user", "content": prompts.build_user_prompt(topic, reference_text)},
        ],
    )
    pages = _split_svg_pages(raw)[:MAX_PAGES]
    if len(pages) < MIN_PAGES:
        logger.warning("LLM 输出无法解析出足够页面：%d 页，原文长度 %d", len(pages), len(raw))
        raise PptGenerationError("模型未能生成有效的 PPT 页面，请重试或更换模型")
    logger.info("LLM 生成完成：%d 页 SVG", len(pages))

    async def repair(file_name: str, svg: str, errors: list[str]) -> str | None:
        raw_fixed = await _call_llm(
            pipeline,
            ctx,
            [
                {"role": "system", "content": prompts.REPAIR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": prompts.build_repair_prompt(file_name, svg, errors),
                },
            ],
        )
        fixed_pages = _split_svg_pages(raw_fixed)
        return fixed_pages[0] if fixed_pages else None

    pptx_bytes = await _convert_pages_to_pptx(pages, repair_fn=repair)
    logger.info("PPT 生成完成：%d 字节", len(pptx_bytes))
    return pptx_bytes
