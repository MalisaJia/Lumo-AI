"""Lumo Coding Agent CLI — 终端交互式编码助手。

直接实例化 ChatPipeline + stream_with_tools()，不走 HTTP，零网络开销。

用法:
    python cli.py -w /path/to/project
    python cli.py -w . --provider openai --model gpt-4o
    python cli.py -w . --message "读取 README.md"
    python cli.py --resume CONVERSATION_ID
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


async def _start_mcp_servers(config_path: str) -> None:
    """启动并注册配置的 MCP 服务器；失败不影响 CLI 启动。"""
    if not config_path:
        return

    try:
        from app.modules.mcp.bridge import register_mcp_tools
        from app.modules.mcp.client import get_mcp_manager
        from app.modules.mcp.config import load_mcp_config

        servers_config = load_mcp_config(config_path)
        manager = get_mcp_manager()
        started_servers = 0
        registered_tools = 0
        for name, cfg in servers_config.items():
            try:
                await manager.start_server(
                    name=name,
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )
                tools = await manager.list_tools(name)
                registered = register_mcp_tools(name, tools)
                started_servers += 1
                registered_tools += registered
                logger.info("MCP server '%s': %d tools registered", name, registered)
            except Exception as exc:
                logger.warning("Failed to start MCP server '%s': %s", name, exc)
        logger.info(
            "MCP initialization complete: %d servers and %d tools loaded",
            started_servers,
            registered_tools,
        )
    except Exception as exc:
        logger.warning("MCP initialization failed: %s", exc)


async def _stop_mcp_servers() -> None:
    """停止 CLI 启动的所有 MCP 服务器；清理失败不影响退出。"""
    try:
        from app.modules.mcp.client import get_mcp_manager

        await get_mcp_manager().stop_all()
    except Exception as exc:
        logger.warning("MCP shutdown failed: %s", exc)


async def _resolve_provider_id(
    session,
    provider_name_or_id: str | None,
    user_id: str,
) -> str | None:
    """将当前用户的 Provider 名称或 ID 解析为数据库 ID。"""
    if not provider_name_or_id:
        return None

    from sqlalchemy import func, select

    from app.models import Provider

    provider = (
        await session.execute(
            select(Provider).where(
                Provider.id == provider_name_or_id,
                Provider.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        provider = (
            await session.execute(
                select(Provider)
                .where(
                    func.lower(Provider.name) == provider_name_or_id.lower(),
                    Provider.user_id == user_id,
                )
                .order_by(Provider.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()
    if provider is None:
        raise ValueError(f"找不到供应商：{provider_name_or_id}")
    return provider.id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Lumo Coding Master CLI")
    parser.add_argument("-w", "--workspace", default=".", help="工作目录（默认当前目录）")
    parser.add_argument(
        "-a", "--agent", default="coding", help="Agent 类型 (coding, ppt, ...)"
    )
    parser.add_argument(
        "--list-agents", action="store_true", help="列出所有可用的 Agent 类型"
    )
    parser.add_argument("-p", "--provider", default=None, help="供应商名称或 ID")
    parser.add_argument("-m", "--model", default=None, help="模型名称")
    parser.add_argument("--message", default=None, help="非交互式单次执行")
    parser.add_argument("--resume", default=None, help="恢复会话 ID")
    parser.add_argument("--user-id", default="local", help="用户 ID（默认 local）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.list_agents:
        from app.modules.tools.agent_profiles import get_all_profiles

        for profile in get_all_profiles():
            icon = f"{profile.icon} " if profile.icon else ""
            print(
                f"{icon}{profile.agent_type}: {profile.display_name}"
                f" — {profile.description}"
            )
        return

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"错误：工作目录不存在：{workspace}", file=sys.stderr)
        sys.exit(1)

    from app.core.config import settings

    settings.workspace_dir = str(workspace)
    settings.sandbox_allowed_dirs = str(workspace)

    # 导入工具包会通过装饰器副作用注册全部 Coding Agent 工具。
    import app.modules.tools  # noqa: F401

    from app.core.db import async_session_factory, engine
    from app.main import _bootstrap_schema

    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)

    await _start_mcp_servers(settings.mcp_config_path)
    try:
        from app.cli.session import create_coding_session, resume_session

        async with async_session_factory() as session:
            try:
                provider_id = await _resolve_provider_id(
                    session, args.provider, args.user_id
                )
            except ValueError as exc:
                print(f"错误：{exc}", file=sys.stderr)
                sys.exit(1)

            if args.resume:
                conversation = await resume_session(session, args.resume, args.user_id)
                if conversation is None:
                    print(f"错误：找不到会话 {args.resume}", file=sys.stderr)
                    sys.exit(1)
                print(f"已恢复会话：{conversation.title} ({conversation.id})")
            else:
                conversation = await create_coding_session(
                    session,
                    args.user_id,
                    str(workspace),
                    provider_id=provider_id,
                    model_name=args.model,
                    agent_type=args.agent,
                )
                print(f"已创建新会话：{conversation.id}")

            conversation_id = conversation.id

        if args.message:
            await _run_once(
                conversation_id,
                args.user_id,
                args.message,
                provider_id,
                args.model,
            )
        else:
            await _run_repl(
                conversation_id,
                args.user_id,
                provider_id,
                args.model,
                workspace,
            )
    finally:
        await _stop_mcp_servers()


async def _run_once(
    conversation_id: str,
    user_id: str,
    message: str,
    provider_id: str | None,
    model_name: str | None,
) -> None:
    """非交互式：执行单次消息并退出。"""
    await _process_message(
        conversation_id, user_id, message, provider_id, model_name
    )


async def _run_repl(
    conversation_id: str,
    user_id: str,
    provider_id: str | None,
    model_name: str | None,
    workspace: Path,
) -> None:
    """交互式 REPL 循环。"""
    print("\nLumo Coding Master")
    print(f"工作目录：{workspace}")
    print("输入消息开始对话，Ctrl+C 退出。输入行尾加 \\ 可多行续行。\n")

    while True:
        try:
            lines: list[str] = []
            prompt = ">>> "
            while True:
                try:
                    line = input(prompt)
                except EOFError:
                    if lines:
                        break
                    print("\n再见！")
                    return
                if line.endswith("\\"):
                    lines.append(line[:-1])
                    prompt = "... "
                else:
                    lines.append(line)
                    break

            user_message = "\n".join(lines).strip()
            if not user_message:
                continue

            if user_message.lower() in ("/exit", "/quit", "exit", "quit"):
                print("再见！")
                return
            if user_message.lower() == "/id":
                print(f"会话 ID: {conversation_id}")
                continue

            print()
            await _process_message(
                conversation_id,
                user_id,
                user_message,
                provider_id,
                model_name,
            )
            print()
        except KeyboardInterrupt:
            print("\n再见！")
            return


async def _process_message(
    conversation_id: str,
    user_id: str,
    user_message: str,
    provider_id: str | None,
    model_name: str | None,
) -> None:
    """将一条用户消息交给完整聊天管线处理。"""
    from app.core.db import async_session_factory
    from app.models import Message
    from app.modules.conversations import service as conversation_service
    from app.modules.tools import get_registry
    from app.modules.tools.executor import stream_with_tools
    from app.pipeline.chat_pipeline import ChatContext, ChatPipeline, PipelineError

    async with async_session_factory() as session:
        conversation = await conversation_service.get_conversation(
            session, conversation_id, user_id
        )
        if conversation is None:
            raise PipelineError("会话不存在")

        session.add(
            Message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
            )
        )
        conversation.updated_at = conversation_service._now()
        await session.commit()

        pipeline = ChatPipeline(session)
        context = ChatContext(
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=user_message,
            provider_id=provider_id,
            model_name=model_name,
        )

        try:
            await pipeline.load_history(context)
            await pipeline.select_model(context)

            tools_payload = get_registry().build_openai_tools()
            if tools_payload:
                async for event in stream_with_tools(
                    pipeline,
                    context,
                    tools_payload,
                    is_disconnected=None,
                ):
                    if event.get("type") == "chunk":
                        print(event.get("content", ""), end="", flush=True)
                    # CLI 无断开检测，keepalive 与 modelSwitch 事件无需渲染。
            else:
                async for chunk in pipeline.call_provider(context):
                    print(chunk, end="", flush=True)
        except Exception:
            await pipeline.persist(context)
            raise

        await pipeline.persist(context)
        if not context.response_text:
            print("（无回复）")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
