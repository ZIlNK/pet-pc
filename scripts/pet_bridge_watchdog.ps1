<#
.SYNOPSIS
  桌宠桥接器 watchdog —— 持续运行，死了就重启

.DESCRIPTION
  每 5 秒检查 pet_to_openclaw_bridge.ps1 是否在跑，死了就重启。
  适合作为常驻任务用 Start-Process 或 Windows 任务计划启动。
#>

$targetScript = "D:\code\pet-pc\scripts\pet_to_openclaw_bridge.ps1"
$logFile = "$env:TEMP\pet_bridge_watchdog.log"
$checkIntervalSec = 5

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Is-BridgeRunning {
    $procs = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
        $_.Id -ne $PID -and $_.CommandLine -like "*pet_to_openclaw_bridge*"
    }
    return ($procs.Count -gt 0)
}

Write-Log "==== Watchdog 启动 ===="
Write-Log "  目标脚本: $targetScript"
Write-Log "  检查间隔: ${checkIntervalSec}s"

try {
    while ($true) {
        if (-not (Is-BridgeRunning)) {
            Write-Log "桥接器不在跑，重新启动..."
            try {
                $proc = Start-Process powershell -ArgumentList @(
                    "-ExecutionPolicy", "Bypass",
                    "-File", $targetScript
                ) -PassThru -WindowStyle Normal
                Write-Log "已启动新桥接器 (PID $($proc.Id))"
            } catch {
                Write-Log "启动失败: $_"
            }
        }
        Start-Sleep -Seconds $checkIntervalSec
    }
} catch {
    Write-Log "Watchdog 异常退出: $_"
}
