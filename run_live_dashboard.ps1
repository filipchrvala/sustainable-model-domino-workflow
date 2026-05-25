# Spusti Streamlit dashboard + pozadie obnovy pri novych CSV v tests/sustainable/company_drop
$Root = $PSScriptRoot
Set-Location $Root

Write-Host "=== Live dashboard ===" -ForegroundColor Cyan
Write-Host "1) Drop new CSV into: tests\sustainable\company_drop"
Write-Host "2) Watcher refreshes alerts + dashboard JSON every 60s when files appear"
Write-Host "3) Streamlit auto-reloads JSON in the browser (enable in sidebar)"
Write-Host ""

$Watcher = Start-Process -FilePath "python" -ArgumentList @(
    "scripts\dashboard_live.py", "--watch", "--poll-seconds", "60"
) -WorkingDirectory $Root -PassThru -NoNewWindow

try {
    python -m streamlit run scripts/streamlit_dashboard.py
}
finally {
    if ($Watcher -and -not $Watcher.HasExited) {
        Stop-Process -Id $Watcher.Id -Force -ErrorAction SilentlyContinue
    }
}
