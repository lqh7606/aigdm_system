param(
    [ValidateSet("Gui", "Menu", "Install", "Start", "StartBackground", "Stop", "Status", "Restart", "Help")]
    [string]$Action = "Gui",
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8001,
    [string]$CondaEnvName = "aigdm-system",
    [switch]$WithSampleData,
    [switch]$SkipCollectStatic,
    [switch]$NoStart,
    [switch]$Background
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $ProjectRoot ".env"
$LauncherRoot = Join-Path $ProjectRoot ".runtime\launcher"
$StatePath = Join-Path $LauncherRoot "runserver.json"
$StdoutLogPath = Join-Path $ProjectRoot "runserver.out.log"
$StderrLogPath = Join-Path $ProjectRoot "runserver.err.log"
$LauncherBuild = "20260615-b64-stdin-v2"
Set-Location $ProjectRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
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

function Set-ProcessEnvironmentValue {
    param(
        [System.Diagnostics.ProcessStartInfo]$StartInfo,
        [string]$Name,
        [string]$Value
    )

    try {
        if ($null -ne $StartInfo.EnvironmentVariables) {
            $StartInfo.EnvironmentVariables[$Name] = $Value
            return
        }
        if ($null -ne $StartInfo.Environment) {
            $StartInfo.Environment[$Name] = $Value
        }
    } catch {
        # Encoding environment variables are best-effort; explicit stream encodings still apply below.
    }
}

function ConvertTo-Base64Utf8 {
    param([string]$Text)

    if ($null -eq $Text) {
        $Text = ""
    }
    return [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Text))
}

function Test-Base64Text {
    param([string]$Text)

    return ($Text -match '^[A-Za-z0-9+/]*={0,2}$')
}

function Invoke-Checked {
    param(
        [scriptblock]$Command,
        [string]$ErrorMessage
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Read-EnvFile {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }
    Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }
        $parts = $line.Split("=", 2)
        $values[$parts[0].Trim()] = $parts[1].Trim().Trim("'").Trim('"')
    }
    return $values
}

function Ensure-DirectoriesFromEnv {
    param([hashtable]$Values)

    foreach ($key in @("AIGDM_MODEL_DIR", "AIGDM_IMPORT_DIR", "AIGDM_BACKUP_DIR", "AIGDM_STATIC_ROOT")) {
        $path = $Values[$key]
        if ($path) {
            if (-not [System.IO.Path]::IsPathRooted($path)) {
                $path = Join-Path $ProjectRoot $path
            }
            try {
                New-Item -ItemType Directory -Force -Path $path | Out-Null
            } catch {
                Write-Warn "无法创建 $key 目录：$path"
                Write-Warn $_.Exception.Message
            }
        }
    }
}

function Get-CondaEnvPath {
    param([string]$Name)

    try {
        $json = & conda env list --json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) {
            return $null
        }
        $envInfo = $json | ConvertFrom-Json
        foreach ($envPath in $envInfo.envs) {
            if ((Split-Path -Leaf $envPath) -eq $Name) {
                return $envPath
            }
        }
    } catch {
        return $null
    }
    return $null
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

function Expand-EmbeddedRuntime {
    $runtimeArchive = Join-Path $ProjectRoot "runtime\$CondaEnvName.zip"
    if (-not (Test-Path $runtimeArchive)) {
        return $null
    }

    $runtimeRoot = Join-Path $ProjectRoot ".runtime\$CondaEnvName"
    $runtimePython = Join-Path $runtimeRoot "python.exe"
    $unpackMarker = Join-Path $runtimeRoot ".aigdm-conda-unpacked"
    $archivePreUnpacked = Test-RuntimeArchivePreUnpacked $runtimeArchive
    if ((Test-Path $runtimePython) -and $archivePreUnpacked -and -not (Test-Path $unpackMarker)) {
        Write-Step "Refreshing embedded runtime"
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }

    if (-not (Test-Path $runtimePython)) {
        Write-Step "Extracting embedded runtime"
        if (Test-Path $runtimeRoot) {
            Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        Expand-Archive -Path $runtimeArchive -DestinationPath $runtimeRoot -Force
    }

    if (-not (Test-Path $runtimePython)) {
        throw "Embedded runtime was extracted but python.exe was not found: $runtimePython"
    }

    $unpack = Join-Path $runtimeRoot "Scripts\conda-unpack.exe"
    if (Test-Path $unpackMarker) {
        Write-Host "Embedded runtime is already unpacked." -ForegroundColor Cyan
    } elseif (Test-Path $unpack) {
        & $unpack
        if ($LASTEXITCODE -ne 0) {
            throw "Embedded runtime path repair failed."
        }
        New-Item -ItemType File -Path $unpackMarker -Force | Out-Null
    }

    return $runtimePython
}

function Resolve-AigdmPython {
    $embeddedPython = Expand-EmbeddedRuntime
    if ($embeddedPython) {
        return $embeddedPython
    }

    if ($env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX "python.exe"))) {
        return Join-Path $env:CONDA_PREFIX "python.exe"
    }

    $localPython = Join-Path $ProjectRoot ".conda\python.exe"
    if (Test-Path $localPython) {
        return $localPython
    }

    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($conda) {
        $condaEnvPath = Get-CondaEnvPath $CondaEnvName
        if (-not $condaEnvPath) {
            Write-Host "Conda environment '$CondaEnvName' was not found. Creating it from environment.yml..."
            Invoke-Checked { & conda env create -f (Join-Path $ProjectRoot "environment.yml") } "Failed to create conda environment."
            $condaEnvPath = Get-CondaEnvPath $CondaEnvName
        }
        if ($condaEnvPath) {
            $condaPython = Join-Path $condaEnvPath "python.exe"
            if (Test-Path $condaPython) {
                return $condaPython
            }
        }
        throw "Conda environment '$CondaEnvName' exists, but python.exe was not found."
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "Python or Conda was not found. Install Anaconda/Miniconda or Python 3.9 first."
}

function Invoke-AigdmPython {
    param([string[]]$Arguments)

    if (-not $script:PythonExe) {
        $script:PythonExe = Resolve-AigdmPython
    }
    & $script:PythonExe @Arguments
    return $LASTEXITCODE
}

function Invoke-AigdmPythonWithInput {
    param(
        [string[]]$Arguments,
        [string]$InputText
    )

    if (-not $script:PythonExe) {
        $script:PythonExe = Resolve-AigdmPython
    }
    $script:LastAigdmPythonOutput = ""

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $script:PythonExe
    $startInfo.Arguments = Join-ProcessArguments $Arguments
    $startInfo.WorkingDirectory = $ProjectRoot
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    Set-ProcessEnvironmentValue $startInfo "PYTHONUTF8" "1"
    Set-ProcessEnvironmentValue $startInfo "PYTHONIOENCODING" "utf-8"
    try {
        $startInfo.StandardInputEncoding = New-Object System.Text.UTF8Encoding($false)
        $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    } catch {
        # Older .NET runtimes may not expose output encoding setters.
    }

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    if ($null -ne $InputText) {
        $process.StandardInput.Write($InputText)
    }
    $process.StandardInput.Close()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdoutTask.Wait()
    $stderrTask.Wait()
    foreach ($line in (($stdoutTask.Result -split "`r?`n") + ($stderrTask.Result -split "`r?`n"))) {
        if ($line -ne "") {
            Write-Host ([string]$line)
        }
    }
    $script:LastAigdmPythonOutput = (($stdoutTask.Result, $stderrTask.Result) -join [Environment]::NewLine).Trim()
    return $process.ExitCode
}

function Get-ServerState {
    if (-not (Test-Path $StatePath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $StatePath -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ManagedServerProcess {
    $state = Get-ServerState
    if (-not $state -or -not $state.pid) {
        return $null
    }
    try {
        return Get-Process -Id ([int]$state.pid) -ErrorAction Stop
    } catch {
        return $null
    }
}

function Remove-ServerState {
    if (Test-Path $StatePath) {
        Remove-Item -LiteralPath $StatePath -Force
    }
}

function Save-ServerState {
    param(
        [System.Diagnostics.Process]$Process,
        [bool]$IsBackground
    )

    New-Item -ItemType Directory -Force -Path $LauncherRoot | Out-Null
    $state = [ordered]@{
        pid = $Process.Id
        host = $HostAddress
        port = $Port
        background = $IsBackground
        project_root = $ProjectRoot
        started_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        stdout_log = $StdoutLogPath
        stderr_log = $StderrLogPath
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Show-Status {
    $state = Get-ServerState
    $process = Get-ManagedServerProcess
    if ($process) {
        Write-Host "AIGDM 服务正在运行。" -ForegroundColor Green
        Write-Host "PID: $($process.Id)"
        Write-Host "访问地址: http://$($state.host):$($state.port)/"
        Write-Host "本机地址: http://127.0.0.1:$($state.port)/"
        Write-Host "启动时间: $($state.started_at)"
        Write-Host "后台运行: $($state.background)"
        if ($state.stdout_log) {
            Write-Host "日志: $($state.stdout_log)"
        }
        return $true
    }

    if ($state) {
        Write-Warn "发现过期启动状态文件，记录的 PID 已不存在。"
        Remove-ServerState
    } else {
        Write-Host "AIGDM 服务未由当前启动器运行。"
    }
    return $false
}

function Show-LanHints {
    $envValues = Read-EnvFile $EnvPath
    $allowedHosts = $envValues["AIGDM_ALLOWED_HOSTS"]
    if ($HostAddress -eq "0.0.0.0") {
        Write-Host "本机地址: http://127.0.0.1:$Port/" -ForegroundColor Green
        Write-Host "内网地址: 请使用本机局域网 IP，例如 http://<服务器IP>:$Port/" -ForegroundColor Green
        if ($allowedHosts -and $allowedHosts -notmatch '(^|,)\s*\*\s*(,|$)') {
            Write-Warn "如需内网访问，AIGDM_ALLOWED_HOSTS 应包含服务器 IP 或 *。当前值：$allowedHosts"
        }
    } else {
        Write-Host "访问地址: http://$HostAddress`:$Port/" -ForegroundColor Green
    }
}

function Start-ManagedServer {
    param([bool]$IsBackground)

    $running = Get-ManagedServerProcess
    if ($running) {
        $state = Get-ServerState
        Write-Warn "AIGDM 已在运行。PID: $($running.Id)，地址: http://$($state.host):$($state.port)/"
        return
    }

    if (-not (Test-Path $EnvPath)) {
        throw "未找到 .env，请先运行安装向导。"
    }

    $script:PythonExe = Resolve-AigdmPython
    Write-Step "启动前检查"
    Invoke-Checked { Invoke-AigdmPython @("manage.py", "doctor", "--strict") } "部署检查未通过，服务未启动。"

    $runserverArgs = @("manage.py", "runserver", "$HostAddress`:$Port", "--noreload")
    $argumentText = Join-ProcessArguments $runserverArgs
    if ($IsBackground) {
        Write-Step "后台启动 AIGDM"
        New-Item -ItemType Directory -Force -Path $LauncherRoot | Out-Null
        foreach ($logPath in @($StdoutLogPath, $StderrLogPath)) {
            if (Test-Path $logPath) {
                Remove-Item -LiteralPath $logPath -Force
            }
        }
        $process = Start-Process `
            -FilePath $script:PythonExe `
            -ArgumentList $argumentText `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $StdoutLogPath `
            -RedirectStandardError $StderrLogPath `
            -PassThru
        Save-ServerState $process $true
        Start-Sleep -Seconds 2
        if ($process.HasExited) {
            Remove-ServerState
            throw "AIGDM 启动后立即退出，请查看日志：$StderrLogPath"
        }
        Write-Ok "后台服务已启动。PID: $($process.Id)"
        Show-LanHints
        return
    }

    Write-Step "前台启动 AIGDM"
    Show-LanHints
    $process = Start-Process `
        -FilePath $script:PythonExe `
        -ArgumentList $argumentText `
        -WorkingDirectory $ProjectRoot `
        -NoNewWindow `
        -PassThru
    Save-ServerState $process $false
    try {
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } finally {
        Remove-ServerState
    }
    exit $exitCode
}

function Confirm-SystemAdminForStop {
    param(
        [string]$Username = "",
        [string]$Password = ""
    )

    Write-Step "停机权限验证"
    $bstr = [IntPtr]::Zero
    try {
        $plainPassword = $Password
        if (-not $Username) {
            $Username = Read-Host "系统管理员用户名"
        }
        if (-not $plainPassword) {
            $securePassword = Read-Host "系统管理员密码" -AsSecureString
            $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
            $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        $expectedLength = [string]($plainPassword.Length)
        $passwordPayload = ConvertTo-Base64Utf8 $plainPassword
        $payloadIsBase64 = Test-Base64Text $passwordPayload
        if (-not $payloadIsBase64) {
            throw "停机权限验证失败：启动器生成的密码传输格式无效。"
        }
        $verifyArgs = @(
            "manage.py",
            "verify_system_admin",
            "--username",
            $Username,
            "--password-stdin-base64",
            "--expected-password-length",
            $expectedLength
        )
        $exitCode = Invoke-AigdmPythonWithInput -Arguments $verifyArgs -InputText $passwordPayload
        if ($exitCode -ne 0) {
            $details = "停机权限验证失败。启动器版本：$LauncherBuild；本地密码长度：$expectedLength；base64载荷长度：$($passwordPayload.Length)；本地base64格式：$payloadIsBase64。"
            if ($script:LastAigdmPythonOutput) {
                $details += [Environment]::NewLine + $script:LastAigdmPythonOutput
            }
            throw $details
        }
        Write-Ok "停机权限验证通过。"
    } finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

function Stop-ManagedServer {
    param(
        [string]$StopUsername = "",
        [string]$StopPassword = ""
    )

    $process = Get-ManagedServerProcess
    if (-not $process) {
        Show-Status | Out-Null
        return
    }

    $script:PythonExe = Resolve-AigdmPython
    Confirm-SystemAdminForStop -Username $StopUsername -Password $StopPassword

    Write-Step "停止 AIGDM 服务"
    Stop-Process -Id $process.Id -Force
    Start-Sleep -Seconds 1
    Remove-ServerState
    Write-Ok "服务已停止。"
}

function Install-Aigdm {
    Write-Host "AIGDM one-click MySQL deployment" -ForegroundColor Green
    Write-Host "Project: $ProjectRoot"

    $script:PythonExe = Resolve-AigdmPython
    Write-Ok "Python: $script:PythonExe"

    Write-Step "Checking Django project"
    Invoke-Checked { Invoke-AigdmPython @("manage.py", "check") } "Django project check failed."

    Write-Step "Checking MySQL configuration"
    $envValues = Read-EnvFile $EnvPath
    $needsInteractiveConfig = -not (Test-Path $EnvPath) `
        -or $envValues["AIGDM_DB_ENGINE"] -ne "mysql" `
        -or -not $envValues["AIGDM_DB_NAME"] `
        -or -not $envValues["AIGDM_DB_USER"] `
        -or -not $envValues["AIGDM_DB_PASSWORD"]

    if ($needsInteractiveConfig) {
        Write-Host ".env is missing or not fully configured for MySQL. Please enter MySQL settings in the prompts."
        Invoke-Checked { Invoke-AigdmPython @("manage.py", "setup_env", "--db-engine", "mysql") } "MySQL setup failed."
    } else {
        Invoke-Checked {
            Invoke-AigdmPython @(
                "manage.py",
                "shell",
                "-c",
                "from django.conf import settings; from django.db import connection; engine=settings.DATABASES['default']['ENGINE']; assert 'mysql' in engine, engine; cursor=connection.cursor(); cursor.execute('SELECT 1'); cursor.fetchone(); print('MySQL connection OK')"
            )
        } "MySQL connection failed. Check .env database settings and MySQL service."
    }

    $envValues = Read-EnvFile $EnvPath
    Ensure-DirectoriesFromEnv $envValues
    Write-Ok "MySQL configuration is ready."

    Write-Step "Applying database migrations"
    Invoke-Checked { Invoke-AigdmPython @("manage.py", "migrate") } "Database migration failed."

    Write-Step "Initializing roles, rules, thresholds, and admin account"
    $initArgs = @("manage.py", "initialize_system", "--create-admin")
    if ($WithSampleData) {
        $initArgs += "--with-sample-data"
    }
    Invoke-Checked { Invoke-AigdmPython $initArgs } "System initialization failed."

    if (-not $SkipCollectStatic) {
        Write-Step "Collecting static files"
        Invoke-Checked { Invoke-AigdmPython @("manage.py", "collectstatic", "--noinput") } "Static file collection failed."
    }

    Write-Step "Deployment report"
    Invoke-AigdmPython @("manage.py", "doctor")
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Doctor reported issues. The server can still start if there are only warnings."
    }

    if ($NoStart) {
        Write-Ok "Deployment finished. Server start was skipped."
        return
    }

    Start-ManagedServer ([bool]$Background)
}

function Restart-ManagedServer {
    param(
        [string]$StopUsername = "",
        [string]$StopPassword = ""
    )

    $process = Get-ManagedServerProcess
    if ($process) {
        Stop-ManagedServer -StopUsername $StopUsername -StopPassword $StopPassword
    }
    Start-ManagedServer $true
}

function Show-Help {
    Write-Host "AIGDM 启动器"
    Write-Host ""
    Write-Host "常用命令："
    Write-Host "  one-click-mysql-deploy.bat"
    Write-Host "  one-click-mysql-deploy.bat -Action Gui"
    Write-Host "  one-click-mysql-deploy.bat -Action Install -NoStart"
    Write-Host "  one-click-mysql-deploy.bat -Action Start"
    Write-Host "  one-click-mysql-deploy.bat -Action StartBackground"
    Write-Host "  one-click-mysql-deploy.bat -Action Stop"
    Write-Host "  one-click-mysql-deploy.bat -Action Status"
    Write-Host ""
    Write-Host "内网启动示例："
    Write-Host "  one-click-mysql-deploy.bat -Action StartBackground -HostAddress 0.0.0.0 -Port 8001"
    Write-Host ""
    Write-Host "停止和重启需要输入 Django 系统管理员账号和密码。"
}

function Show-Gui {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()
    $guiEnvValues = Read-EnvFile $EnvPath

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "AIGDM 启动器"
    $form.StartPosition = "CenterScreen"
    $form.Size = New-Object System.Drawing.Size(880, 620)
    $form.MinimumSize = New-Object System.Drawing.Size(820, 580)
    $form.AutoScaleMode = [System.Windows.Forms.AutoScaleMode]::Font
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

    $root = New-Object System.Windows.Forms.TableLayoutPanel
    $root.Dock = "Fill"
    $root.ColumnCount = 1
    $root.RowCount = 5
    $root.Padding = New-Object System.Windows.Forms.Padding(14)
    $root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 64))) | Out-Null
    $root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 148))) | Out-Null
    $root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 106))) | Out-Null
    $root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
    $root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 60))) | Out-Null
    $form.Controls.Add($root)

    $titlePanel = New-Object System.Windows.Forms.Panel
    $titlePanel.Dock = "Fill"
    $title = New-Object System.Windows.Forms.Label
    $title.Text = "AIGDM MySQL 启动器"
    $title.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
    $title.AutoSize = $true
    $title.Location = New-Object System.Drawing.Point(0, 2)
    $subtitle = New-Object System.Windows.Forms.Label
    $subtitle.Text = "安装后用于启动、停止和监控内网服务。"
    $subtitle.AutoSize = $true
    $subtitle.Location = New-Object System.Drawing.Point(2, 34)
    $titlePanel.Controls.Add($title)
    $titlePanel.Controls.Add($subtitle)
    $root.Controls.Add($titlePanel, 0, 0)

    $configGroup = New-Object System.Windows.Forms.GroupBox
    $configGroup.Text = "服务"
    $configGroup.Dock = "Fill"
    $configGroup.Padding = New-Object System.Windows.Forms.Padding -ArgumentList 14, 26, 14, 16
    $root.Controls.Add($configGroup, 0, 1)

    $configTable = New-Object System.Windows.Forms.TableLayoutPanel
    $configTable.Dock = "Fill"
    $configTable.ColumnCount = 4
    $configTable.RowCount = 2
    $configTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 98))) | Out-Null
    $configTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 55))) | Out-Null
    $configTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 74))) | Out-Null
    $configTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 45))) | Out-Null
    $configTable.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 42))) | Out-Null
    $configTable.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 42))) | Out-Null
    $configGroup.Controls.Add($configTable)

    $lblHost = New-Object System.Windows.Forms.Label
    $lblHost.Text = "绑定地址"
    $lblHost.TextAlign = "MiddleRight"
    $lblHost.Dock = "Fill"
    $txtHost = New-Object System.Windows.Forms.TextBox
    $txtHost.Text = $HostAddress
    $txtHost.Dock = "Fill"
    $lblPort = New-Object System.Windows.Forms.Label
    $lblPort.Text = "端口"
    $lblPort.TextAlign = "MiddleRight"
    $lblPort.Dock = "Fill"
    $txtPort = New-Object System.Windows.Forms.TextBox
    $txtPort.Text = [string]$Port
    $txtPort.Dock = "Fill"
    $lblUrl = New-Object System.Windows.Forms.Label
    $lblUrl.Text = "本机地址"
    $lblUrl.TextAlign = "MiddleRight"
    $lblUrl.Dock = "Fill"
    $txtUrl = New-Object System.Windows.Forms.TextBox
    $txtUrl.ReadOnly = $true
    $txtUrl.Dock = "Fill"
    $lblStatus = New-Object System.Windows.Forms.Label
    $lblStatus.Text = "状态"
    $lblStatus.TextAlign = "MiddleRight"
    $lblStatus.Dock = "Fill"
    $txtStatus = New-Object System.Windows.Forms.TextBox
    $txtStatus.ReadOnly = $true
    $txtStatus.Dock = "Fill"

    $configTable.Controls.Add($lblHost, 0, 0)
    $configTable.Controls.Add($txtHost, 1, 0)
    $configTable.Controls.Add($lblPort, 2, 0)
    $configTable.Controls.Add($txtPort, 3, 0)
    $configTable.Controls.Add($lblUrl, 0, 1)
    $configTable.Controls.Add($txtUrl, 1, 1)
    $configTable.Controls.Add($lblStatus, 2, 1)
    $configTable.Controls.Add($txtStatus, 3, 1)

    $adminGroup = New-Object System.Windows.Forms.GroupBox
    $adminGroup.Text = "停机权限"
    $adminGroup.Dock = "Fill"
    $adminGroup.Padding = New-Object System.Windows.Forms.Padding -ArgumentList 14, 26, 14, 16
    $root.Controls.Add($adminGroup, 0, 2)

    $adminTable = New-Object System.Windows.Forms.TableLayoutPanel
    $adminTable.Dock = "Fill"
    $adminTable.ColumnCount = 4
    $adminTable.RowCount = 1
    $adminTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 98))) | Out-Null
    $adminTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50))) | Out-Null
    $adminTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 80))) | Out-Null
    $adminTable.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50))) | Out-Null
    $adminTable.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 46))) | Out-Null
    $adminGroup.Controls.Add($adminTable)

    $lblUser = New-Object System.Windows.Forms.Label
    $lblUser.Text = "管理员账号"
    $lblUser.TextAlign = "MiddleRight"
    $lblUser.Dock = "Fill"
    $txtAdminUser = New-Object System.Windows.Forms.TextBox
    $txtAdminUser.Dock = "Fill"
    $txtAdminUser.Text = $guiEnvValues["AIGDM_ADMIN_USERNAME"]
    if (-not $txtAdminUser.Text) {
        $txtAdminUser.Text = "aigdm_admin"
    }
    $lblPass = New-Object System.Windows.Forms.Label
    $lblPass.Text = "密码"
    $lblPass.TextAlign = "MiddleRight"
    $lblPass.Dock = "Fill"
    $passPanel = New-Object System.Windows.Forms.TableLayoutPanel
    $passPanel.Dock = "Fill"
    $passPanel.ColumnCount = 3
    $passPanel.RowCount = 1
    $passPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
    $passPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 58))) | Out-Null
    $passPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, 54))) | Out-Null
    $txtAdminPass = New-Object System.Windows.Forms.TextBox
    $txtAdminPass.UseSystemPasswordChar = $true
    $txtAdminPass.Dock = "Fill"
    $chkShowPass = New-Object System.Windows.Forms.CheckBox
    $chkShowPass.Text = "显示"
    $chkShowPass.Dock = "Fill"
    $chkShowPass.Margin = New-Object System.Windows.Forms.Padding(4, 0, 0, 0)
    $chkShowPass.Add_CheckedChanged({
        $txtAdminPass.UseSystemPasswordChar = -not $chkShowPass.Checked
    })
    $lblPassLen = New-Object System.Windows.Forms.Label
    $lblPassLen.Text = "0位"
    $lblPassLen.TextAlign = "MiddleLeft"
    $lblPassLen.Dock = "Fill"
    $txtAdminPass.Add_TextChanged({
        $lblPassLen.Text = ([string]$txtAdminPass.Text.Length) + "位"
    })
    $passPanel.Controls.Add($txtAdminPass, 0, 0)
    $passPanel.Controls.Add($chkShowPass, 1, 0)
    $passPanel.Controls.Add($lblPassLen, 2, 0)
    $adminTable.Controls.Add($lblUser, 0, 0)
    $adminTable.Controls.Add($txtAdminUser, 1, 0)
    $adminTable.Controls.Add($lblPass, 2, 0)
    $adminTable.Controls.Add($passPanel, 3, 0)

    $logBox = New-Object System.Windows.Forms.TextBox
    $logBox.Dock = "Fill"
    $logBox.Multiline = $true
    $logBox.ScrollBars = "Vertical"
    $logBox.ReadOnly = $true
    $logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
    $root.Controls.Add($logBox, 0, 3)

    $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
    $buttons.Dock = "Fill"
    $buttons.FlowDirection = "LeftToRight"
    $buttons.WrapContents = $false
    $buttons.Padding = New-Object System.Windows.Forms.Padding(0, 8, 0, 0)
    $root.Controls.Add($buttons, 0, 4)

    function New-GuiButton {
        param([string]$Text, [int]$Width = 104)
        $button = New-Object System.Windows.Forms.Button
        $button.Text = $Text
        $button.Width = $Width
        $button.Height = 30
        $button.Margin = New-Object System.Windows.Forms.Padding(0, 0, 8, 0)
        return $button
    }

    $btnStart = New-GuiButton "后台启动" 92
    $btnStop = New-GuiButton "停止" 82
    $btnRestart = New-GuiButton "后台重启" 96
    $btnRefresh = New-GuiButton "刷新" 82
    $btnOpen = New-GuiButton "打开页面" 88
    $btnLog = New-GuiButton "打开日志" 92
    $btnInstall = New-GuiButton "安装向导" 88
    $btnClose = New-GuiButton "关闭" 78
    foreach ($button in @($btnStart, $btnStop, $btnRestart, $btnRefresh, $btnOpen, $btnLog, $btnInstall, $btnClose)) {
        $buttons.Controls.Add($button)
    }

    function Append-GuiLog {
        param([string]$Message)
        $logBox.AppendText(("[" + (Get-Date -Format "HH:mm:ss") + "] " + $Message + [Environment]::NewLine))
        $logBox.SelectionStart = $logBox.TextLength
        $logBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    }

    function Apply-GuiConfig {
        $parsedPort = 0
        if (-not [int]::TryParse($txtPort.Text.Trim(), [ref]$parsedPort)) {
            throw "端口必须是数字。"
        }
        if ($parsedPort -le 0 -or $parsedPort -gt 65535) {
            throw "端口必须在 1 到 65535 之间。"
        }
        $script:HostAddress = $txtHost.Text.Trim()
        if (-not $script:HostAddress) {
            throw "绑定地址不能为空。"
        }
        $script:Port = $parsedPort
        $txtUrl.Text = "http://127.0.0.1:$script:Port/"
    }

    function Refresh-GuiStatus {
        Apply-GuiConfig
        $process = Get-ManagedServerProcess
        if ($process) {
            $state = Get-ServerState
            $txtStatus.Text = "运行中 PID $($process.Id)"
            $txtHost.Text = [string]$state.host
            $txtPort.Text = [string]$state.port
            $txtUrl.Text = "http://127.0.0.1:$($state.port)/"
            Append-GuiLog "服务正在运行。PID: $($process.Id)"
        } else {
            $txtStatus.Text = "已停止"
            Append-GuiLog "服务未运行。"
        }
    }

    function Run-GuiAction {
        param(
            [string]$Name,
            [scriptblock]$Body
        )
        foreach ($button in @($btnStart, $btnStop, $btnRestart, $btnRefresh, $btnOpen, $btnLog, $btnInstall)) {
            $button.Enabled = $false
        }
        try {
            Append-GuiLog $Name
            & $Body
            Refresh-GuiStatus
        } catch {
            Append-GuiLog ("失败：" + $_.Exception.Message)
            [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "AIGDM 启动器", "OK", "Error") | Out-Null
        } finally {
            foreach ($button in @($btnStart, $btnStop, $btnRestart, $btnRefresh, $btnOpen, $btnLog, $btnInstall)) {
                $button.Enabled = $true
            }
        }
    }

    $btnStart.Add_Click({
        Run-GuiAction "正在后台启动服务..." {
            Apply-GuiConfig
            Start-ManagedServer $true
        }
    })

    $btnStop.Add_Click({
        Run-GuiAction "正在停止服务..." {
            Apply-GuiConfig
            $stopUsername = [string]$txtAdminUser.Text.Trim()
            $stopPassword = [string]$txtAdminPass.Text
            Append-GuiLog ("停机校验账号：" + $stopUsername + "，本地密码框长度：" + $stopPassword.Length)
            Stop-ManagedServer -StopUsername $stopUsername -StopPassword $stopPassword
            $txtAdminPass.Clear()
        }
    })

    $btnRestart.Add_Click({
        Run-GuiAction "正在后台重启服务..." {
            Apply-GuiConfig
            $stopUsername = [string]$txtAdminUser.Text.Trim()
            $stopPassword = [string]$txtAdminPass.Text
            Append-GuiLog ("重启校验账号：" + $stopUsername + "，本地密码框长度：" + $stopPassword.Length)
            Restart-ManagedServer -StopUsername $stopUsername -StopPassword $stopPassword
            $txtAdminPass.Clear()
        }
    })

    $btnRefresh.Add_Click({
        Run-GuiAction "正在刷新状态..." {
            Apply-GuiConfig
        }
    })

    $btnOpen.Add_Click({
        Run-GuiAction "正在打开本机地址..." {
            Apply-GuiConfig
            Start-Process $txtUrl.Text
        }
    })

    $btnLog.Add_Click({
        Run-GuiAction "正在打开日志..." {
            if (Test-Path $StderrLogPath) {
                Start-Process notepad.exe $StderrLogPath
            }
            if (Test-Path $StdoutLogPath) {
                Start-Process notepad.exe $StdoutLogPath
            }
            if ((-not (Test-Path $StderrLogPath)) -and (-not (Test-Path $StdoutLogPath))) {
                throw "未找到运行日志文件。"
            }
        }
    })

    $btnInstall.Add_Click({
        Run-GuiAction "正在打开安装向导..." {
            $installer = Join-Path $ProjectRoot "install-aigdm.bat"
            if (-not (Test-Path $installer)) {
                throw "未找到 install-aigdm.bat。"
            }
            Start-Process -FilePath $installer -WorkingDirectory $ProjectRoot
        }
    })

    $btnClose.Add_Click({ $form.Close() })

    $form.Add_Shown({
        try {
            Apply-GuiConfig
            Refresh-GuiStatus
            Append-GuiLog "启动器版本：$LauncherBuild"
            Append-GuiLog "停止或重启需要系统管理员账号。"
        } catch {
            Append-GuiLog ("失败：" + $_.Exception.Message)
        }
    })

    [void]$form.ShowDialog()
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "AIGDM MySQL 启动器" -ForegroundColor Green
        Write-Host "项目目录：$ProjectRoot"
        Write-Host "1. 安装/重新部署 MySQL 版本"
        Write-Host "2. 前台启动服务"
        Write-Host "3. 后台启动服务"
        Write-Host "4. 查看服务状态"
        Write-Host "5. 停止服务（需要系统管理员）"
        Write-Host "6. 后台重启服务（需要系统管理员）"
        Write-Host "7. 帮助"
        Write-Host "0. 退出"
        $choice = Read-Host "请选择"
        switch ($choice) {
            "1" { Install-Aigdm }
            "2" { Start-ManagedServer $false }
            "3" { Start-ManagedServer $true }
            "4" { Show-Status | Out-Null }
            "5" { Stop-ManagedServer }
            "6" { Restart-ManagedServer }
            "7" { Show-Help }
            "0" { return }
            default { Write-Warn "无效选项，请重新选择。" }
        }
    }
}

try {
    switch ($Action) {
        "Gui" { Show-Gui }
        "Menu" { Show-Menu }
        "Install" { Install-Aigdm }
        "Start" { Start-ManagedServer $false }
        "StartBackground" { Start-ManagedServer $true }
        "Stop" { Stop-ManagedServer }
        "Status" { Show-Status | Out-Null }
        "Restart" { Restart-ManagedServer }
        "Help" { Show-Help }
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host "[FAILED] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:"
    Write-Host "  1. For MySQL failures, check MySQL service, database, user, and privileges."
    Write-Host "  2. For LAN access failures, ensure AIGDM_ALLOWED_HOSTS includes the server IP or *."
    Write-Host "  3. For background startup failures, check: $StderrLogPath"
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}
