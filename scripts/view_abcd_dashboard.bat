@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0view_abcd_dashboard.ps1"
if errorlevel 1 pause
