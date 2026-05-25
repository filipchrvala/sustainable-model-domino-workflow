# Web form for project settings, consumption CSV, and scenario (WebUserInputPiece)
$Root = $PSScriptRoot
Set-Location $Root
Write-Host "Web vstup: http://localhost:8501" -ForegroundColor Cyan
Write-Host "Po ulozeni: python run_workflow.py --input-mode web" -ForegroundColor Gray
python -m streamlit run scripts/streamlit_web_input.py
