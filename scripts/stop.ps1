# ============================================================
#  Lumo AI 一键停止脚本（由根目录 stop.bat 调用）
#  行为：查找监听 8000 / 5173 端口的进程并结束（taskkill），
#        只处理监听这两个端口的进程及其对应的 Lumo 日志窗口，
#        不会影响其他程序。
# ============================================================
$ErrorActionPreference = 'Continue'

Write-Host '==============================================='
Write-Host '            Lumo AI 一键停止'
Write-Host '==============================================='

# 沿父进程链向上查找由 start 脚本创建的 Lumo 日志窗口（标题为 Lumo Backend / Lumo Frontend）
function Get-LumoWindowAncestor {
    param([int]$ProcessId)
    $current = $ProcessId
    for ($i = 0; $i -lt 6; $i++) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$current" -ErrorAction SilentlyContinue
        if (-not $proc -or -not $proc.ParentProcessId) { return $null }
        $parent = Get-Process -Id $proc.ParentProcessId -ErrorAction SilentlyContinue
        if (-not $parent) { return $null }
        if ($parent.MainWindowTitle -like 'Lumo *') { return $parent.Id }
        $current = $parent.Id
    }
    return $null
}

$targets = @(
    @{ Port = 8000; Name = '后端 (uvicorn)' },
    @{ Port = 5173; Name = '前端 (vite)' }
)

$stoppedAny = $false
foreach ($t in $targets) {
    $port = $t.Port
    $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    $ownerPids = @($conns | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 })
    if ($ownerPids.Count -eq 0) {
        Write-Host "[跳过] 端口 $port（$($t.Name)）当前没有监听进程，无需停止" -ForegroundColor Yellow
        continue
    }
    foreach ($procId in $ownerPids) {
        $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
        # 先在进程结束前找到对应的 Lumo 日志窗口
        $windowPid = Get-LumoWindowAncestor -ProcessId $procId
        taskkill /PID $procId /T /F 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[停止] 已结束端口 $port 的进程：$procName (PID $procId)（$($t.Name)）" -ForegroundColor Green
            $stoppedAny = $true
        } else {
            Write-Host "[失败] 无法结束端口 $port 的进程 PID $procId，请尝试以管理员身份运行" -ForegroundColor Red
        }
        # 顺带关闭 start 脚本留下的日志窗口（仅限标题为 Lumo * 的窗口）
        if ($windowPid) {
            taskkill /PID $windowPid /F 2>&1 | Out-Null
        }
    }
}

if ($stoppedAny) {
    Write-Host '[完成] Lumo AI 服务已停止。' -ForegroundColor Green
} else {
    Write-Host '[完成] 没有需要停止的服务。' -ForegroundColor Green
}
exit 0
