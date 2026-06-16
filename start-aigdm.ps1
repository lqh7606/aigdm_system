param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8001,
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
$ProjectRoot = ""
if ($MyInvocation.MyCommand.Path) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
} else {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

function ConvertTo-ProcessArgument {
    param([string]$Argument)

    if ($null -eq $Argument -or $Argument -eq "") {
        return '""'
    }
    if ($Argument -notmatch '[\s"]') {
        return $Argument
    }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashCount = 0
    foreach ($char in $Argument.ToCharArray()) {
        if ($char -eq [char]92) {
            $backslashCount += 1
            continue
        }
        if ($char -eq [char]34) {
            if ($backslashCount -gt 0) {
                [void]$builder.Append(('\' * ($backslashCount * 2)))
                $backslashCount = 0
            }
            [void]$builder.Append('\"')
            continue
        }
        if ($backslashCount -gt 0) {
            [void]$builder.Append(('\' * $backslashCount))
            $backslashCount = 0
        }
        [void]$builder.Append($char)
    }
    if ($backslashCount -gt 0) {
        [void]$builder.Append(('\' * ($backslashCount * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Join-ProcessArguments {
    param([string[]]$Arguments)

    $quoted = @()
    foreach ($argument in $Arguments) {
        $quoted += ConvertTo-ProcessArgument $argument
    }
    return ($quoted -join " ")
}

function Invoke-ExternalProcess {
    param(
        [string]$FileName,
        [string[]]$Arguments = @(),
        [string]$StepName = "执行外部命令"
    )

    Write-Host $StepName -ForegroundColor Cyan
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.Arguments = Join-ProcessArguments $Arguments
    $startInfo.WorkingDirectory = $ProjectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    try {
        $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    } catch {
        # Older .NET runtimes may not expose output encoding setters.
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdoutTask.Wait()
    $stderrTask.Wait()

    foreach ($line in (($stdoutTask.Result -split "`r?`n") + ($stderrTask.Result -split "`r?`n"))) {
        if ($line -ne "") {
            Write-Host $line
        }
    }
    if ($process.ExitCode -ne 0) {
        throw "$StepName 失败，退出码：$($process.ExitCode)"
    }
    return $process.ExitCode
}

function Test-RuntimeArchivePreUnpacked {
    param([string]$ArchivePath)

    if (-not (Test-Path $ArchivePath)) {
        return $false
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName -eq ".aigdm-conda-unpacked") {
                return $true
            }
        }
    } finally {
        $zip.Dispose()
    }
    return $false
}

function Test-EmbeddedRuntime {
    param([string]$PythonPath)

    [void](Invoke-ExternalProcess $PythonPath @("-c", "import sys, os; print('AIGDM runtime check ok')"))
}
function Expand-EmbeddedRuntime {
    $runtimeArchive = Join-Path $ProjectRoot "runtime\aigdm-system.zip"
    $runtimeRoot = Join-Path $ProjectRoot ".runtime\aigdm-system"
    $runtimePython = Join-Path $runtimeRoot "python.exe"
    $unpackMarker = Join-Path $runtimeRoot ".aigdm-conda-unpacked"

    if (Test-Path $runtimePython) {
        Write-Host "检测到预先解压的内置运行时" -ForegroundColor Cyan
        $unpack = Join-Path $runtimeRoot "Scripts\conda-unpack.exe"
        if (Test-Path $unpackMarker) {
            Write-Host "内置运行时已预修复，跳过路径修复" -ForegroundColor Cyan
        } elseif (Test-Path $unpack) {
            try {
                [void](Invoke-ExternalProcess $unpack @() "修复内置运行时路径")
            } catch {
                Write-Host "未能完成路径修复，继续尝试部署（兼容降级）" -ForegroundColor Yellow
                Write-Host ("失败原因：" + $_.Exception.Message) -ForegroundColor Yellow
            }
            New-Item -ItemType File -Path $unpackMarker -Force | Out-Null
        } else {
            New-Item -ItemType File -Path $unpackMarker -Force | Out-Null
        }

        Test-EmbeddedRuntime $runtimePython
        return $runtimePython
    }

    if (Test-Path $runtimeRoot) {
        Write-Host "发现无效内置运行时目录，准备重新解压" -ForegroundColor Cyan
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }

    if (-not (Test-Path $runtimeArchive)) {
        return $null
    }

    Write-Host "解压内置离线运行时" -ForegroundColor Cyan
    if (Test-Path $runtimeRoot) {
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    Expand-Archive -Path $runtimeArchive -DestinationPath $runtimeRoot -Force

    if (-not (Test-Path $runtimePython)) {
        throw "解压内置运行时后未找到 python.exe：$runtimePython"
    }

    $unpack = Join-Path $runtimeRoot "Scripts\conda-unpack.exe"
    if (Test-Path $unpackMarker) {
        Write-Host "内置运行时已预修复，跳过路径修复" -ForegroundColor Cyan
    } elseif (Test-Path $unpack) {
        try {
            [void](Invoke-ExternalProcess $unpack @() "修复内置运行时路径")
        } catch {
            Write-Host "未能完成路径修复，继续尝试部署（兼容降级）" -ForegroundColor Yellow
            Write-Host ("失败原因：" + $_.Exception.Message) -ForegroundColor Yellow
        }
        New-Item -ItemType File -Path $unpackMarker -Force | Out-Null
    }

    Test-EmbeddedRuntime $runtimePython
    return $runtimePython
}
function Invoke-AigdmPython {
    param([string[]]$Arguments)

    $embeddedPython = Expand-EmbeddedRuntime
    if ($embeddedPython) {
        & $embeddedPython @Arguments
        return $LASTEXITCODE
    }

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

if (-not (Test-Path (Join-Path $ProjectRoot ".env"))) {
    Write-Host "未找到 .env，请先运行 scripts\setup.ps1 或 python manage.py setup_env。" -ForegroundColor Yellow
    exit 1
}

if (-not $SkipDoctor) {
    Invoke-AigdmPython @("manage.py", "doctor", "--strict")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "部署检查未通过，已停止启动。" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "启动 AIGDM：http://$HostAddress`:$Port/" -ForegroundColor Green
Invoke-AigdmPython @("manage.py", "runserver", "$HostAddress`:$Port")
exit $LASTEXITCODE

