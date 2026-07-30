# Lumo AI 桌面安装包构建脚本
# 用法: powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Write-Host "== Lumo AI 桌面构建 ==" -ForegroundColor Cyan
Write-Host "项目根目录: $Root"

# ① 构建前端
Write-Host "`n[1/4] 构建前端 (vite build) ..." -ForegroundColor Cyan
npm run build --prefix (Join-Path $Root "frontend")
if ($LASTEXITCODE -ne 0) {
    Write-Host "前端构建失败 (exit $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}

# ② 拷贝 frontend/dist -> backend/frontend_dist
Write-Host "`n[2/4] 拷贝前端产物到 backend/frontend_dist ..." -ForegroundColor Cyan
$FrontendDist = Join-Path $Root "frontend\dist"
$BackendFrontend = Join-Path $Root "backend\frontend_dist"
if (-not (Test-Path $FrontendDist)) {
    Write-Host "未找到 $FrontendDist，前端构建产物缺失" -ForegroundColor Red
    exit 1
}
if (Test-Path $BackendFrontend) {
    Remove-Item -Recurse -Force $BackendFrontend
}
Copy-Item -Recurse -Force $FrontendDist $BackendFrontend
Write-Host "已拷贝到 $BackendFrontend"

# ③ PyInstaller 打包后端
Write-Host "`n[3/4] PyInstaller 打包后端 ..." -ForegroundColor Cyan
$BackendDir = Join-Path $Root "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "未找到 $VenvPython，请先创建后端虚拟环境" -ForegroundColor Red
    exit 1
}
& $VenvPython -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "venv 中未安装 PyInstaller，正在安装 ..." -ForegroundColor Yellow
    & $VenvPython -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller 安装失败 (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}
Push-Location $BackendDir
& $VenvPython -m PyInstaller lumo_backend.spec --noconfirm
$PyiExit = $LASTEXITCODE
Pop-Location
if ($PyiExit -ne 0) {
    Write-Host "PyInstaller 打包失败 (exit $PyiExit)" -ForegroundColor Red
    exit 1
}

# ④ electron-builder 打包安装包
Write-Host "`n[4/4] electron-builder 打包 Windows 安装包 ..." -ForegroundColor Cyan
# 国内网络直连 GitHub 下载 Electron/NSIS 二进制易超时，固定走 npmmirror 镜像
if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}
if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
    $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
}
$DesktopDir = Join-Path $Root "desktop"
Push-Location $DesktopDir
if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Write-Host "desktop/node_modules 缺失，执行 npm install ..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "desktop npm install 失败 (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}
npx electron-builder --win
$EbExit = $LASTEXITCODE
Pop-Location
if ($EbExit -ne 0) {
    Write-Host "electron-builder 打包失败 (exit $EbExit)" -ForegroundColor Red
    exit 1
}

# ⑤ 产物提示
Write-Host "`n== 构建完成 ==" -ForegroundColor Green
Write-Host "安装包输出目录: $(Join-Path $Root 'desktop\release')" -ForegroundColor Green
Get-ChildItem (Join-Path $Root "desktop\release") -Filter *.exe -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("  -> " + $_.FullName) -ForegroundColor Green
}
exit 0
