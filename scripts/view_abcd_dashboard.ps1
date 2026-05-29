# Spusti CFO dashboard (Streamlit) z tohto repozitara.
$ErrorActionPreference = "Stop"

$WfRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DashUnified = Join-Path $WfRoot "tests\dashboard_data.json"
$DashPiece = Join-Path $WfRoot "tests\DashboardPiece_Outputs\dashboard_data.json"
$Snapshot = Join-Path $WfRoot "tests\_presentation\abcd_auto\dashboard_data.json"

Set-Location $WfRoot

if (-not (Test-Path $DashUnified)) {
    if (Test-Path $DashPiece) {
        Copy-Item $DashPiece $DashUnified -Force
        Write-Host "Skopirovane: DashboardPiece_Outputs -> tests\dashboard_data.json" -ForegroundColor Yellow
    }
    elseif (Test-Path $Snapshot) {
        Copy-Item $Snapshot $DashUnified -Force
        Write-Host "Skopirovane: _presentation\abcd_auto -> tests\dashboard_data.json" -ForegroundColor Yellow
    }
    else {
        Write-Host "Chyba: chyba dashboard_data.json. Najprv spustite workflow:" -ForegroundColor Red
        Write-Host "  cd C:\Users\NTB\Domino\industry_sg_vre_workflow" -ForegroundColor Cyan
        Write-Host "  python scripts\prepare_abcd_run.py" -ForegroundColor Cyan
        exit 1
    }
}

Write-Host ""
Write-Host "=== SPICE UC3 - investicny CFO dashboard ===" -ForegroundColor Cyan
Write-Host "Subor: $DashUnified"
Write-Host "URL:   http://localhost:8501"
Write-Host ""
Write-Host "Sidebar: Rezim prezentacie (screenshot) = zapnuty" -ForegroundColor Yellow
Write-Host "Ukoncenie: Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

python -m streamlit run scripts/streamlit_dashboard.py
