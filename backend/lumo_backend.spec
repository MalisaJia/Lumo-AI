# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：Lumo AI 后端打包（onedir 模式）。

产物：backend/dist/lumo_backend/（主 exe 为 lumo_backend.exe）。
构建方式（由构建脚本执行，勿手动）：pyinstaller lumo_backend.spec

datas 说明：
- alembic.ini / alembic/：_alembic_head() 运行时读取迁移脚本目录。
- frontend_dist/：前端构建产物（构建脚本先把 frontend/dist 拷贝到
  backend/frontend_dist 再打包；目录不存在时容错跳过，避免干跑失败）。
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BACKEND_DIR = os.path.dirname(os.path.abspath(SPEC))

# 项目代码全部作为源码收集，规避 FastAPI/SQLAlchemy 模型注册等间接导入遗漏
hiddenimports = [
    *collect_submodules("app"),
    # sqlite 异步驱动与方言（SQLAlchemy 运行时按字符串动态加载）
    "aiosqlite",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.aiosqlite",
    # uvicorn 内部按字符串动态导入的实现模块
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # alembic 迁移脚本运行时由 ScriptDirectory 动态加载
    *collect_submodules("alembic"),
    # pydantic v2 依赖的编译核心
    "pydantic_core",
    # 会话导出（PPTX/PDF 生成库）
    *collect_submodules("pptx"),
    *collect_submodules("fpdf"),
]

datas = [
    (os.path.join(BACKEND_DIR, "alembic.ini"), "."),
    (os.path.join(BACKEND_DIR, "alembic"), "alembic"),
    # pydantic/alembic 附带的数据文件（版本元数据、mako 模板等）
    *collect_data_files("alembic"),
    # fpdf2 附带的字体/数据文件
    *collect_data_files("fpdf"),
]

# 前端构建产物仅在构建脚本拷贝后存在；首次干跑（无前端）时容错跳过
_frontend_dist = os.path.join(BACKEND_DIR, "frontend_dist")
if os.path.exists(_frontend_dist):
    datas.append((_frontend_dist, "frontend_dist"))

a = Analysis(
    ["run_desktop.py"],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="lumo_backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="lumo_backend",
)
