param(
    [string]$OutputDir = "",
    [string]$PackageName = "",
    [string]$CondaEnvName = "aigdm-system",
    [switch]$FullOffline
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = $PSScriptRoot
if (-not $ScriptRoot) {
    $ScriptRoot = Join-Path (Get-Location) "scripts"
}
$ProjectRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "dist"
}
if (-not $PackageName) {
    $prefix = "aigdm-windows-installer"
    if ($FullOffline) {
        $prefix = "aigdm-windows-installer-full"
    }
    $PackageName = $prefix + "-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}
if ([System.IO.Path]::GetFileName($PackageName) -ne $PackageName) {
    throw "PackageName 不能包含路径分隔符。"
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$PackageRoot = [System.IO.Path]::GetFullPath((Join-Path $OutputDir $PackageName))
$ZipPath = [System.IO.Path]::GetFullPath((Join-Path $OutputDir "$PackageName.zip"))
$outputPrefix = $OutputDir.TrimEnd([char[]](92, 47)) + [System.IO.Path]::DirectorySeparatorChar
if (-not $PackageRoot.StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "PackageRoot 不在输出目录下：$PackageRoot"
}
if (-not $ZipPath.StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ZipPath 不在输出目录下：$ZipPath"
}

$excludeDirs = @(
    ".git",
    ".pytest_cache",
    ".runtime",
    "__pycache__",
    "backups",
    "dist",
    "import_files",
    "staticfiles"
)

$excludeFiles = @(
    ".env",
    "db.sqlite3",
    "runserver.err.log",
    "runserver.out.log"
)

$fullOfflineExcludeDirs = @(
    ".agents",
    ".codex",
    ".idea",
    ".mypy_cache",
    ".ruff_cache",
    ".vscode",
    "deploy",
    "docs",
    "htmlcov",
    "tests"
)

$fullOfflineExcludeFiles = @(
    ".coverage",
    ".gitignore",
    "build-windows-installer-package.bat",
    "environment.yml",
    "one-click-mysql-deploy.bat",
    "README.md",
    "README.zh-CN.md",
    "requirements.lock",
    "requirements.txt",
    "tests.py"
)

$fullOfflineExcludePathPatterns = @(
    "scripts/build_windows_installer_package.ps1",
    "scripts/one_click_mysql_deploy.ps1",
    "scripts/setup.ps1",
    "*.log",
    "*.pyc",
    "*.pyo",
    "*.sqlite3"
)

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-ExcludedPath {
    param([string]$RelativePath)
    $normalizedPath = $RelativePath -replace '\\', '/'
    $parts = $RelativePath -split '[\\/]'
    foreach ($dir in $excludeDirs) {
        if ($parts -contains $dir) {
            return $true
        }
    }
    if ($excludeFiles -contains (Split-Path -Leaf $RelativePath)) {
        return $true
    }
    if ($FullOffline) {
        foreach ($dir in $fullOfflineExcludeDirs) {
            if ($parts -contains $dir) {
                return $true
            }
        }
        if ($fullOfflineExcludeFiles -contains (Split-Path -Leaf $RelativePath)) {
            return $true
        }
        foreach ($pattern in $fullOfflineExcludePathPatterns) {
            if ($normalizedPath -like $pattern) {
                return $true
            }
        }
    }
    return $false
}

function Get-CondaEnvPath {
    param([string]$Name)
    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $conda) {
        throw "未找到 conda 命令。完整离线包需要在打包机安装 Anaconda/Miniconda。"
    }
    $json = & conda env list --json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) {
        throw "无法读取 Conda 环境列表。"
    }
    $envInfo = $json | ConvertFrom-Json
    foreach ($envPath in $envInfo.envs) {
        if ((Split-Path -Leaf $envPath) -eq $Name) {
            return $envPath
        }
    }
    throw "未找到 Conda 环境 '$Name'。请先运行：conda env create -f environment.yml"
}

function Get-CondaPackCommand {
    $command = Get-Command conda-pack -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "未找到 conda-pack。请先运行：conda install -n base -c conda-forge conda-pack"
}

function Assert-RequiredFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "缺少必要文件：$Path"
    }
}

function Assert-PackageDoesNotContain {
    param(
        [string]$Root,
        [string[]]$RelativePaths
    )
    foreach ($relativePath in $RelativePaths) {
        $target = Join-Path $Root $relativePath
        if (Test-Path $target) {
            throw "安装包不应包含：$relativePath"
        }
    }
}

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
        [string]$WorkingDirectory = $ProjectRoot,
        [string]$StepName = "执行外部命令"
    )

    Write-Host "==> $StepName" -ForegroundColor Cyan
    Write-Host ("> " + $FileName + " " + (Join-ProcessArguments $Arguments))
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.Arguments = Join-ProcessArguments $Arguments
    $startInfo.WorkingDirectory = $WorkingDirectory
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

function Repair-CondaUnpackScriptForWindows {
    param([string]$RuntimeRoot)

    $scriptPath = Join-Path $RuntimeRoot "Scripts\conda-unpack-script.py"
    if (-not (Test-Path $scriptPath)) {
        return
    }

    $content = [System.IO.File]::ReadAllText($scriptPath, [System.Text.Encoding]::UTF8)
    if ($content.Contains("# AIGDM Windows path normalization")) {
        return
    }

    $needle = "    with open(path, 'rb+') as fh:"
    $replacement = @"
    if on_win:
        # AIGDM Windows path normalization: conda-pack 0.6.0 may join an
        # extended-length Windows prefix with POSIX-style record paths such as
        # Library/bin/c_rehash.pl, which Python cannot open on Windows.
        path = os.path.normpath(path.replace('/', '\\'))
    with open(path, 'rb+') as fh:
"@.TrimEnd()
    if (-not $content.Contains($needle)) {
        throw "无法修补 conda-unpack-script.py：未找到目标 open(path) 语句。"
    }
    $content = $content.Replace($needle, $replacement)
    [System.IO.File]::WriteAllText($scriptPath, $content, [System.Text.Encoding]::UTF8)
}

function Compress-RuntimeArchive {
    param(
        [string]$RuntimeRoot,
        [string]$DestinationPath
    )

    if (Test-Path $DestinationPath) {
        Remove-Item -LiteralPath $DestinationPath -Force
    }
    $items = Get-ChildItem -LiteralPath $RuntimeRoot -Force
    Compress-Archive -Path $items.FullName -DestinationPath $DestinationPath -Force
}

Write-Step "检查打包输入"
Assert-RequiredFile (Join-Path $ProjectRoot "install-aigdm.bat")
Assert-RequiredFile (Join-Path $ProjectRoot "scripts\install_wizard.ps1")
Assert-RequiredFile (Join-Path $ProjectRoot "start-aigdm.ps1")
Assert-RequiredFile (Join-Path $ProjectRoot "manage.py")
Assert-RequiredFile (Join-Path $ProjectRoot "environment.yml")
Assert-RequiredFile (Join-Path $ProjectRoot "model_files")
Write-Host "应用目录：$ProjectRoot"
Write-Host "输出目录：$OutputDir"
Write-Host "包名：$PackageName"
Write-Host "完整离线包：$FullOffline"
if ($FullOffline) {
    Write-Host "交付模式：精简客户安装包"
}

$condaEnvPath = $null
$condaPack = $null
if ($FullOffline) {
    Write-Step "检查离线运行时依赖"
    $condaEnvPath = Get-CondaEnvPath $CondaEnvName
    $condaPack = Get-CondaPackCommand
    Write-Host "Conda 环境：$condaEnvPath"
    Write-Host "conda-pack：$condaPack"
}

Write-Step "准备输出目录"
try {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
} catch {
    throw "无法创建输出目录：$OutputDir。可通过 -OutputDir 指定其他可写目录。原始错误：$($_.Exception.Message)"
}
if (Test-Path $PackageRoot) {
    Remove-Item -LiteralPath $PackageRoot -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null

Write-Step "复制应用文件"
Get-ChildItem -Path $ProjectRoot -Recurse -Force | ForEach-Object {
    $relativePath = $_.FullName.Substring($ProjectRoot.Length).TrimStart([char[]](92, 47))
    if (-not $relativePath -or (Test-ExcludedPath $relativePath)) {
        return
    }

    $target = Join-Path $PackageRoot $relativePath
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

if ($FullOffline) {
    Write-Step "打包离线 Python/Conda 运行时"
    $runtimeDir = Join-Path $PackageRoot "runtime"
    $runtimeZip = Join-Path $runtimeDir "$CondaEnvName.zip"
    $runtimeBuildRoot = Join-Path $OutputDir "$PackageName-runtime-build"
    $packedRuntimeZip = Join-Path $runtimeBuildRoot "$CondaEnvName-packed.zip"
    $expandedRuntimeRoot = Join-Path $runtimeBuildRoot $CondaEnvName
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    Write-Host "Conda 环境：$condaEnvPath"
    Write-Host "conda-pack：$condaPack"
    try {
        if (Test-Path $runtimeBuildRoot) {
            Remove-Item -LiteralPath $runtimeBuildRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Path $runtimeBuildRoot -Force | Out-Null

        Invoke-ExternalProcess $condaPack @("-p", $condaEnvPath, "-o", $packedRuntimeZip, "--force") $ProjectRoot "conda-pack 打包运行时"
        Assert-RequiredFile $packedRuntimeZip

        Write-Step "预解包并修复离线运行时"
        New-Item -ItemType Directory -Path $expandedRuntimeRoot -Force | Out-Null
        Expand-Archive -Path $packedRuntimeZip -DestinationPath $expandedRuntimeRoot -Force
        $runtimePython = Join-Path $expandedRuntimeRoot "python.exe"
        $runtimeUnpack = Join-Path $expandedRuntimeRoot "Scripts\conda-unpack.exe"
        Assert-RequiredFile $runtimePython
        Assert-RequiredFile $runtimeUnpack
        Repair-CondaUnpackScriptForWindows $expandedRuntimeRoot
        Invoke-ExternalProcess $runtimeUnpack @() $expandedRuntimeRoot "构建机修复运行时路径"
        New-Item -ItemType File -Path (Join-Path $expandedRuntimeRoot ".aigdm-conda-unpacked") -Force | Out-Null

        Write-Step "压缩已修复离线运行时"
        Compress-RuntimeArchive $expandedRuntimeRoot $runtimeZip
    } catch {
        Remove-Item -LiteralPath $PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        Remove-Item -LiteralPath $runtimeBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    Assert-RequiredFile $runtimeZip
}

Write-Step "校验安装包内容"
Assert-PackageDoesNotContain $PackageRoot @(".env", "db.sqlite3", ".git", ".codex", ".agents", "dist", ".pytest_cache", "deploy", "docs")
if ($FullOffline) {
    Assert-RequiredFile (Join-Path $PackageRoot "runtime\$CondaEnvName.zip")
    Assert-PackageDoesNotContain $PackageRoot @(
        ".gitignore",
        "README.md",
        "README.zh-CN.md",
        "requirements.txt",
        "requirements.lock",
        "environment.yml",
        "build-windows-installer-package.bat",
        "one-click-mysql-deploy.bat",
        "scripts\build_windows_installer_package.ps1",
        "scripts\setup.ps1",
        "scripts\one_click_mysql_deploy.ps1"
    )
}

Write-Step "压缩安装包"
Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath -Force
Assert-RequiredFile $ZipPath

Write-Host ""
Write-Host "Windows installer package created:" -ForegroundColor Green
Write-Host $ZipPath
Write-Host ""
Write-Host "Usage:"
Write-Host "  1. Unzip the package on the target Windows machine."
Write-Host "  2. Run install-aigdm.bat."
Write-Host "  3. Fill MySQL and administrator settings in the installer window."
