$json = openclaw sessions list --active 10 --json 2>&1 | Out-String
Write-Host "=== raw first 300 chars ==="
Write-Host $json.Substring(0, [Math]::Min(300, $json.Length))
Write-Host ""
Write-Host "=== parse ==="
try {
    $obj = $json | ConvertFrom-Json -ErrorAction Stop
    Write-Host "top-level keys: $($obj.PSObject.Properties.Name -join '|')"
    $sessions = if ($obj.sessions) { $obj.sessions } else { @($obj) }
    Write-Host "sessions count: $($sessions.Count)"
    $sessions | ForEach-Object { Write-Host "  key=$($_.key) kind=$($_.kind)" }
} catch {
    Write-Host "parse error: $_"
}
