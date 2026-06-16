@echo off
setlocal
chcp 65001 >nul
title Build AIGDM Windows Installer Package
cd /d "%~dp0"
set "AIGDM_PACKAGE_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root = $env:AIGDM_PACKAGE_ROOT; Set-Location -LiteralPath $root; $scriptPath = Join-Path $root 'scripts\build_windows_installer_package.ps1'; $script = [scriptblock]::Create([System.IO.File]::ReadAllText($scriptPath, [System.Text.Encoding]::UTF8)); & $script @args" %*
exit /b %ERRORLEVEL%
