"""PyInstaller 桌面版入口：以内嵌 uvicorn 启动 FastAPI 后端。

冻结（frozen）环境注意事项：
- 必须直接导入 app 对象传给 uvicorn.run，不能用 "app.main:app" 字符串
  （字符串形式走动态导入，PyInstaller 可能收集不到）。
- Windows 冻结环境惯例：加 multiprocessing.freeze_support()，
  防止子进程 spawn 时重复执行入口逻辑。

环境变量：
- LUMO_PORT：监听端口，默认 8000。
- LUMO_DATA_DIR：可写数据目录（由 Electron 主进程注入，见 app/core/config.py）。
"""

import multiprocessing
import os
import sys

# PyInstaller --noconsole 模式下 stdout/stderr 为 None，
# uvicorn 日志配置会调用 isatty() 导致 AttributeError，需提前修补
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import uvicorn

from app.main import app


def main() -> None:
    port = int(os.environ.get("LUMO_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
