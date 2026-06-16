param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Invoke-AigdmPython {
    param([string[]]$Arguments)

    if ($env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX "python.exe"))) {
        & (Join-Path $env:CONDA_PREFIX "python.exe") @Arguments
        return $LASTEXITCODE
    }

    $localPython = Join-Path $ProjectRoot ".conda\python.exe"
    if (Test-Path $localPython) {
        & $localPython @Arguments
        return $LASTEXITCODE
    }

    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($conda) {
        & conda run -n aigdm-system python @Arguments
        return $LASTEXITCODE
    }

    & python @Arguments
    return $LASTEXITCODE
}

$argsList = @("manage.py", "setup_env")
if ($NonInteractive) {
    $argsList += "--non-interactive"
}

Invoke-AigdmPython $argsList
exit $LASTEXITCODE
