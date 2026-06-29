<#
.SYNOPSIS
  Desktop Pet → OpenClaw 实时桥接监听器（方案 C）

.DESCRIPTION
  监听桌宠写入的 jsonl 钩子文件（$env:TEMP\pet_user_messages.jsonl），
  每当用户通过桌宠气泡发送消息，桥接器把消息作为系统事件注入
  OpenClaw 主 session，让 AI 实时收到并可调用 get_user_messages
  工具拉取并回复。

  用法：
    powershell -ExecutionPolicy Bypass -File scripts\pet_to_openclaw_bridge.ps1
    # 或后台运行
    Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-File","$PWD\scripts\pet_to_openclaw_bridge.ps1" -WindowStyle Hidden

.NOTES
  Author : Ling (老板的桌面宠物小助手 ☀️)
  Created: 2026-06-17
  Requires: PowerShell 5.1+, OpenClaw CLI in PATH
#>

param(
    [string]$HookFile = "$env:TEMP\pet_user_messages.jsonl",
    [string]$LogFile  = "$env:TEMP\pet_to_openclaw_bridge.log",
    [int]   $PollMs   = 500,  # 备用轮询（ms），用于兜底 FileSystemWatcher 漏报
    [switch]$DryRun          # 仅打印注入内容，不实际调用 openclaw system event
)

# ── 日志函数 ──────────────────────────────────────────────
function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

# ── 初始化：记录启动时文件大小（只处理新内容） ────────────
$script:lastSize = 0
# 去重保护：FileSystemWatcher 在 Windows 上对同一次写入会触发多次 Changed 事件
$script:lastMessageText = ""
$script:lastMessageTime = [datetime]::MinValue
# OpenClaw dashboard session 缓存（动态获取，发送失败时刷新）
$script:OpenClawSessionKey = ""
$script:OpenClawSessionKeyFetchedAt = [datetime]::MinValue
if (Test-Path $HookFile) {
    $script:lastSize = (Get-Item $HookFile).Length
    Write-Log "发现已有钩子文件，当前偏移: $script:lastSize bytes"
} else {
    Write-Log "钩子文件尚不存在，等待桌宠创建: $HookFile"
}

# ── 动态获取老板当前活跃的 dashboard session key ─────────
function Get-OpenClawSessionKey {
    try {
        # 用 active 60 拿到近期 1 小时内活跃的 session（active 10 在老板场景下返回 0）
        $json = openclaw sessions list --active 60 --json 2>&1 | Out-String
        $obj = $json | ConvertFrom-Json -ErrorAction Stop
        # JSON 结构是 { sessions: [...] }，需取 .sessions
        $sessions = if ($obj.sessions) { $obj.sessions } else { @($obj) }
        $dash = $sessions | Where-Object { $_.key -like "agent:main:dashboard:*" } | Select-Object -First 1
        if ($dash) {
            return $dash.key
        }
        # fallback：拿任意最近活跃的 direct session
        $any = $sessions | Where-Object { $_.kind -eq "direct" } | Select-Object -First 1
        if ($any) { return $any.key }
    } catch {
        Write-Log "获取 session key 失败: $_"
    }
    return $null
}

# 启动时主动获取一次
$script:OpenClawSessionKey = Get-OpenClawSessionKey
$script:OpenClawSessionKeyFetchedAt = Get-Date
if ($script:OpenClawSessionKey) {
    Write-Log "老板当前 session: $script:OpenClawSessionKey"
} else {
    Write-Log "警告：启动时未获取到 session key，发送时会重试"
}

# ── 解析单行并注入 OpenClaw ──────────────────────────────
function Send-ToOpenClaw([string]$jsonLine) {
    try {
        $msg = $jsonLine | ConvertFrom-Json -ErrorAction Stop
        $text = [string]$msg.text
        if ([string]::IsNullOrWhiteSpace($text)) {
            Write-Log "跳过空消息"
            return
        }

        # 转义双引号避免 PowerShell 解析问题
        $safeText = $text -replace '"', '\"'
        $eventText = @"
桌宠气泡收到用户消息: "$safeText"

处理步骤：
1. （可选）调 desktop-pet__get_user_messages 兑底拉取
2. 理解用户意图并生成简短回复（控制 60 字以内）
3. 调 desktop-pet__show_message(text="<你的回复>") 在桌宠气泡上显示回复

这是桌宠用户通过 ChatBubble 发送的实时对话。
"@

        Write-Log "收到: $text"

        # 去重：500ms 内同文本不重复触发（FileSystemWatcher 会重复触发）
        $now = Get-Date
        if ($text -eq $script:lastMessageText -and ($now - $script:lastMessageTime).TotalMilliseconds -lt 500) {
            Write-Log "跳过重复触发 (${text} 出现于 500ms 内)"
            return
        }
        $script:lastMessageText = $text
        $script:lastMessageTime = $now

        Write-Log "注入 OpenClaw 主 session..."

        if ($DryRun) {
            Write-Log "[DRY-RUN] 将注入 OpenClaw 主 session: $eventText"
            return
        }

        # 注入老板当前 dashboard session（--mode now 立即唤醒）
        # 每次发送前检查 session key 缓存（超过 2 分钟重新获取）
        if (-not $script:OpenClawSessionKey -or ((Get-Date) - $script:OpenClawSessionKeyFetchedAt).TotalMinutes -gt 2) {
            Write-Log "刷新 session key 缓存..."
            $script:OpenClawSessionKey = Get-OpenClawSessionKey
            $script:OpenClawSessionKeyFetchedAt = Get-Date
            if ($script:OpenClawSessionKey) {
                Write-Log "当前 session: $script:OpenClawSessionKey"
            }
        }
        if (-not $script:OpenClawSessionKey) {
            Write-Log "✗ 无法获取 session key，跳过本次注入"
            return
        }

        $output = openclaw system event --session-key $script:OpenClawSessionKey --mode now --text $eventText 2>&1
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            Write-Log "✓ 注入成功"
        } else {
            Write-Log "✗ 注入失败 (exit=$exitCode): $output"
            # 失败时清空缓存，下次重新获取
            $script:OpenClawSessionKey = ""
        }
    } catch {
        Write-Log "解析失败: $_ (raw: $jsonLine)"
    }
}

# ── FileSystemWatcher 监听 ───────────────────────────────
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = Split-Path $HookFile -Parent
$watcher.Filter = Split-Path $HookFile -Leaf
$watcher.NotifyFilter = [System.IO.NotifyFilters]::LastWrite -bor [System.IO.NotifyFilters]::Size
$watcher.EnableRaisingEvents = $true

$onChange = {
    Start-Sleep -Milliseconds 100   # 等写入完成
    if (-not (Test-Path $HookFile)) { return }
    $currentSize = (Get-Item $HookFile).Length
    if ($currentSize -le $script:lastSize) { return }

    try {
        $stream = [System.IO.File]::Open(
            $HookFile,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        $stream.Position = $script:lastSize
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        $newContent = $reader.ReadToEnd()
        $reader.Close()
        $stream.Close()
        $script:lastSize = $currentSize
    } catch {
        Write-Log "读取新增内容失败: $_"
        return
    }

    foreach ($line in ($newContent -split "`n")) {
        $line = $line.Trim()
        if ([string]::IsNullOrEmpty($line)) { continue }
        Send-ToOpenClaw $line
    }
}

# 注册事件
$null = Register-ObjectEvent -InputObject $watcher -EventName Changed -Action $onChange -SourceIdentifier "PetHookChanged"
$null = Register-ObjectEvent -InputObject $watcher -EventName Created -Action $onChange -SourceIdentifier "PetHookCreated"

Write-Log "==== 桥接器启动 ===="
Write-Log "  监听文件: $HookFile"
Write-Log "  日志文件: $LogFile"
Write-Log "  当前偏移: $script:lastSize bytes"
Write-Log "  按 Ctrl+C 停止"

# ── 主循环（同时跑兜底轮询） ─────────────────────────────
# 注意：PowerShell 5.1 不支持纯 try/finally，必须配合 catch
try {
    while ($true) {
        Start-Sleep -Milliseconds $PollMs
        # 兜底：如果文件被替换/重建，lastSize 可能 > 当前 size，重置
        if (Test-Path $HookFile) {
            $currentSize = (Get-Item $HookFile).Length
            if ($currentSize -lt $script:lastSize) {
                Write-Log "检测到文件被重建/截断，重置偏移"
                $script:lastSize = 0
            }
        }
    }
} catch {
    Write-Log "主循环异常: $_"
} finally {
    Write-Log "==== 桥接器停止 ===="
    Unregister-Event -SourceIdentifier "PetHookChanged" -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier "PetHookCreated" -ErrorAction SilentlyContinue
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
}
