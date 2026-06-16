@echo off
setlocal
chcp 65001 >nul
title AIGDM Installer
cd /d "%~dp0"
set "AIGDM_INSTALLER_ROOT=%~dp0"
echo Starting AIGDM installer...
echo Current directory: %CD%
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root = $env:AIGDM_INSTALLER_ROOT; Set-Location -LiteralPath $root; $scriptPath = Join-Path $root 'scripts\install_wizard.ps1'; $script = [scriptblock]::Create([System.IO.File]::ReadAllText($scriptPath, [System.Text.Encoding]::UTF8)); & $script @args" %*
set "AIGDM_EXIT_CODE=%ERRORLEVEL%"
echo.
echo AIGDM installer exited with code: %AIGDM_EXIT_CODE%
pause
exit /b %AIGDM_EXIT_CODE%
