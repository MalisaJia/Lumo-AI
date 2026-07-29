# ============================================================
#  Lumo AI 一键启动脚本（由根目录 start.bat 调用）
#  用法：start.bat            正常启动
#        start.bat dev       开发模式（后端带 --reload 热重载）
#  行为：检查依赖 -> 检测端口占用 -> 启动缺失的服务 -> 等待就绪 -> 打开浏览器
# ============================================================
param([switch]$Dev)

$ErrorActionPreference = 'Stop'

$root        = Split-Path -Parent $PSScriptRoot
$backendDir  = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$python      = Join-Path $backendDir '.venv\Scripts\python.exe'
$nodeModules = Join-Path $frontendDir 'node_modules'

$backendPort  = 8000
$frontendPort = 5173

# 依次尝试多个地址（兼容 IPv4 / IPv6，vite 默认监听 ::1）
function Test-PortOpen {
    param([string[]]$Addresses, [int]$Port)
    foreach ($addr in $Addresses) {
        try {
            $ip = [System.Net.IPAddress]::Parse($addr)
            $client = New-Object System.Net.Sockets.TcpClient($ip.AddressFamily)
            $ok = $client.ConnectAsync($ip, $Port).Wait(1000)
            $connected = $ok -and $client.Connected
            $client.Close()
            if ($connected) { return $true }
        } catch { }
    }
    return $false
}

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

Write-Host '==============================================='
Write-Host '            Lumo AI 一键启动'
Write-Host '==============================================='

# ---------- 1. 依赖检查 ----------
$envOk = $true
if (-not (Test-Path $python)) {
    Write-Host '[错误] 未找到后端虚拟环境 backend\.venv' -ForegroundColor Red
    Write-Host '       请先在 backend 目录执行以下命令安装：' -ForegroundColor Yellow
    Write-Host '         python -m venv .venv'
    Write-Host '         .venv\Scripts\pip install -r requirements.txt'
    $envOk = $false
}
if (-not (Test-Path $nodeModules)) {
    Write-Host '[错误] 未找到前端依赖 frontend\node_modules' -ForegroundColor Red
    Write-Host '       请先在 frontend 目录执行以下命令安装：' -ForegroundColor Yellow
    Write-Host '         npm install'
    $envOk = $false
}
if (-not $envOk) { exit 1 }

# ---------- 2. 端口检测 + 启动 ----------
$startedBackend  = $false
$startedFrontend = $false

if (Test-PortListening -Port $backendPort) {
    Write-Host "[跳过] 端口 $backendPort 已被占用，后端服务疑似已在运行，跳过启动" -ForegroundColor Yellow
} else {
    $reload = ''
    if ($Dev) { $reload = ' --reload'; Write-Host '[信息] 开发模式：后端将以 --reload 启动' }
    $backendCmd = "`$Host.UI.RawUI.WindowTitle = 'Lumo Backend'; Set-Location -LiteralPath '$backendDir'; & '$python' -m uvicorn app.main:app --port $backendPort$reload"
    Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', $backendCmd) -WorkingDirectory $backendDir -WindowStyle Minimized
    Write-Host "[启动] 后端已在独立窗口（Lumo Backend，已最小化）中启动..." -ForegroundColor Cyan
    $startedBackend = $true
}

if (Test-PortListening -Port $frontendPort) {
    Write-Host "[跳过] 端口 $frontendPort 已被占用，前端服务疑似已在运行，跳过启动" -ForegroundColor Yellow
} else {
    $frontendCmd = "`$Host.UI.RawUI.WindowTitle = 'Lumo Frontend'; Set-Location -LiteralPath '$frontendDir'; npm run dev"
    Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', $frontendCmd) -WorkingDirectory $frontendDir -WindowStyle Minimized
    Write-Host "[启动] 前端已在独立窗口（Lumo Frontend，已最小化）中启动..." -ForegroundColor Cyan
    $startedFrontend = $true
}

# ---------- 3. 等待端口就绪（最多约 30 秒） ----------
$backendReady  = $false
$frontendReady = $false
Write-Host '[等待] 正在等待服务就绪（最多 30 秒）...'
for ($i = 0; $i -lt 30; $i++) {
    if (-not $backendReady)  { $backendReady  = Test-PortOpen -Addresses @('127.0.0.1', '::1') -Port $backendPort }
    if (-not $frontendReady) { $frontendReady = Test-PortOpen -Addresses @('::1', '127.0.0.1') -Port $frontendPort }
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Seconds 1
}

# ---------- 4. 结果汇总 ----------
$failed = $false
if ($backendReady) {
    Write-Host "[就绪] 后端服务：http://127.0.0.1:$backendPort" -ForegroundColor Green
} else {
    Write-Host "[失败] 后端服务在 30 秒内未就绪！" -ForegroundColor Red
    Write-Host "       请打开任务栏中标题为 'Lumo Backend' 的窗口查看错误日志。" -ForegroundColor Yellow
    $failed = $true
}
if ($frontendReady) {
    Write-Host "[就绪] 前端服务：http://localhost:$frontendPort" -ForegroundColor Green
} else {
    Write-Host "[失败] 前端服务在 30 秒内未就绪！" -ForegroundColor Red
    Write-Host "       请打开任务栏中标题为 'Lumo Frontend' 的窗口查看错误日志。" -ForegroundColor Yellow
    $failed = $true
}
if ($failed) { exit 1 }

if ($startedBackend -or $startedFrontend) {
    Write-Host '[完成] 服务已全部就绪，正在打开浏览器...' -ForegroundColor Green
    Start-Process "http://localhost:$frontendPort"
} else {
    Write-Host '[完成] 前后端均已在运行，无需重复启动。' -ForegroundColor Green
    Write-Host "       前端地址：http://localhost:$frontendPort"
}
exit 0
