@echo off
REM ============================================================
REM  Lumo AI 一键启动（双击即可）
REM  用法：start.bat          正常启动前后端
REM        start.bat dev      开发模式（后端带 --reload 热重载）
REM  实际逻辑位于 scripts\start.ps1
REM ============================================================
chcp 65001 >nul
set "PSARGS="
if /i "%~1"=="dev" set "PSARGS=-Dev"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %PSARGS%
echo.
pause
