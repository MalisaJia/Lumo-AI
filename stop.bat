@echo off
REM ============================================================
REM  Lumo AI 一键停止（双击即可）
REM  按端口 8000 / 5173 查找并结束对应服务进程，不影响其他程序
REM  实际逻辑位于 scripts\stop.ps1
REM ============================================================
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
echo.
pause
