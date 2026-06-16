param(
    [string]$CondaEnvName = "aigdm-system"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = $PSScriptRoot
if (-not $ScriptRoot) {
    $ScriptRoot = Join-Path (Get-Location) "scripts"
}
$ProjectRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
$EnvPath = Join-Path $ProjectRoot ".env"
$script:InstallLogPath = Join-Path $ProjectRoot "install-aigdm.log"
Set-Location $ProjectRoot
try {
    Set-Content -Path $script:InstallLogPath -Value ("AIGDM installer log started at " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -Encoding UTF8
} catch {
    # Logging is diagnostic only; do not block the installer if the log cannot be initialized.
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

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

function Get-EnvDefault {
    param(
        [hashtable]$Values,
        [string]$Key,
        [string]$Fallback
    )
    if ($Values.ContainsKey($Key) -and $Values[$Key]) {
        return $Values[$Key]
    }
    return $Fallback
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

function Get-EmbeddedRuntimeArchive {
    return Join-Path $ProjectRoot "runtime\$CondaEnvName.zip"
}

function Get-EmbeddedRuntimeRoot {
    return Join-Path $ProjectRoot ".runtime\$CondaEnvName"
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

function Write-OptionalLog {
    param(
        [System.Windows.Forms.TextBox]$LogBox,
        [string]$Message
    )
    if ($LogBox) {
        $LogBox.AppendText($Message + [Environment]::NewLine)
        $LogBox.SelectionStart = $LogBox.TextLength
        $LogBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    }
    if ($script:InstallLogPath) {
        try {
            Add-Content -Path $script:InstallLogPath -Value $Message -Encoding UTF8
        } catch {
            # Keep the UI responsive even if the install directory is not writable.
        }
    }
}

function Expand-EmbeddedRuntime {
    param([System.Windows.Forms.TextBox]$LogBox = $null)

    $archive = Get-EmbeddedRuntimeArchive
    if (-not (Test-Path $archive)) {
        return $null
    }

    $runtimeRoot = Get-EmbeddedRuntimeRoot
    $runtimePython = Join-Path $runtimeRoot "python.exe"
    $unpackMarker = Join-Path $runtimeRoot ".aigdm-conda-unpacked"
    $archivePreUnpacked = Test-RuntimeArchivePreUnpacked $archive
    if ((Test-Path $runtimePython) -and $archivePreUnpacked -and -not (Test-Path $unpackMarker)) {
        Write-OptionalLog $LogBox "==> 检测到旧内置运行时，重新解压预修复运行时"
        Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
    }

    if (-not (Test-Path $runtimePython)) {
        Write-OptionalLog $LogBox "==> 解压内置离线运行时"
        if (Test-Path $runtimeRoot) {
            Remove-Item -LiteralPath $runtimeRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        Expand-Archive -Path $archive -DestinationPath $runtimeRoot -Force
    }

    if (-not (Test-Path $runtimePython)) {
        throw "内置离线运行时解压后未找到 python.exe：$runtimePython"
    }

    $unpack = Join-Path $runtimeRoot "Scripts\conda-unpack.exe"
    if (Test-Path $unpackMarker) {
        Write-OptionalLog $LogBox "==> 内置运行时已预修复，跳过路径修复"
    } elseif (Test-Path $unpack) {
        Invoke-ExternalProcess $unpack @() $LogBox "修复内置运行时路径"
        New-Item -ItemType File -Path $unpackMarker -Force | Out-Null
    }

    return $runtimePython
}

function Resolve-AigdmPython {
    param([System.Windows.Forms.TextBox]$LogBox = $null)

    $embeddedPython = Expand-EmbeddedRuntime $LogBox
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
            throw "未找到 Conda 环境 '$CondaEnvName'。请先运行：conda env create -f environment.yml"
        }
        $condaPython = Join-Path $condaEnvPath "python.exe"
        if (Test-Path $condaPython) {
            return $condaPython
        }
        throw "Conda 环境存在，但未找到 python.exe：$condaPython"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }
    throw "未找到 Python 或 Conda。请先安装 Anaconda/Miniconda 或 Python 3.9。"
}

function New-TextBox {
    param(
        [string]$Text = "",
        [bool]$Password = $false,
        [int]$Width = 210
    )
    $box = New-Object System.Windows.Forms.TextBox
    $box.Width = $Width
    $box.Text = $Text
    $box.Dock = "Fill"
    $box.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
    if ($Password) {
        $box.UseSystemPasswordChar = $true
    }
    return $box
}

function New-InstallerGroupBox {
    param([string]$Text)

    $group = New-Object System.Windows.Forms.GroupBox
    $group.Text = $Text
    $group.Dock = "Fill"
    $group.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
    $group.Padding = New-Object System.Windows.Forms.Padding(8, 22, 8, 8)
    return $group
}

function New-InputTable {
    param(
        [int]$Rows,
        [int]$LabelWidth,
        [int]$RowHeight = 34
    )

    $table = New-Object System.Windows.Forms.TableLayoutPanel
    $table.Dock = "Top"
    $table.ColumnCount = 2
    $table.RowCount = $Rows
    $table.Padding = New-Object System.Windows.Forms.Padding(4, 2, 4, 4)
    $table.Height = ($Rows * $RowHeight) + $table.Padding.Top + $table.Padding.Bottom + 2
    $table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Absolute, $LabelWidth))) | Out-Null
    $table.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
    for ($row = 0; $row -lt $Rows; $row++) {
        $table.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, $RowHeight))) | Out-Null
    }
    return $table
}

function Add-Field {
    param(
        [System.Windows.Forms.TableLayoutPanel]$Panel,
        [string]$Label,
        [System.Windows.Forms.Control]$Control,
        [int]$Row
    )
    $labelControl = New-Object System.Windows.Forms.Label
    $labelControl.Text = $Label
    $labelControl.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $labelControl.AutoEllipsis = $true
    $labelControl.Dock = "Fill"
    $labelControl.Margin = New-Object System.Windows.Forms.Padding(2, 4, 6, 4)
    $Control.Dock = "Fill"
    $Control.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
    $Panel.Controls.Add($labelControl, 0, $Row)
    $Panel.Controls.Add($Control, 1, $Row)
}

function Append-Log {
    param(
        [System.Windows.Forms.TextBox]$LogBox,
        [string]$Message
    )
    Write-OptionalLog $LogBox $Message
}

function ConvertTo-ProcessArgument {
    param([string]$Argument)

    if ($null -eq $Argument) {
        return '""'
    }
    if ($Argument -eq "") {
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

function Invoke-ExternalProcess {
    param(
        [string]$FileName,
        [string[]]$Arguments = @(),
        [System.Windows.Forms.TextBox]$LogBox = $null,
        [string]$StepName = "执行外部命令",
        [string]$StandardInput = $null
    )
    Append-Log $LogBox "==> $StepName"
    Append-Log $LogBox ("> " + $FileName + " " + (Join-ProcessArguments $Arguments))

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.Arguments = Join-ProcessArguments $Arguments
    $startInfo.WorkingDirectory = $ProjectRoot
    $startInfo.UseShellExecute = $false
    if ($null -ne $StandardInput) {
        $startInfo.RedirectStandardInput = $true
    }
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
    if ($null -ne $StandardInput) {
        $process.StandardInput.Write($StandardInput)
        $process.StandardInput.Close()
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    while (-not $process.HasExited) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
    $process.WaitForExit()
    $stdoutTask.Wait()
    $stderrTask.Wait()
    $stdout = $stdoutTask.Result
    $stderr = $stderrTask.Result
    $exitCode = $process.ExitCode

    foreach ($line in (($stdout -split "`r?`n") + ($stderr -split "`r?`n"))) {
        if ($line -ne "") {
            Append-Log $LogBox ([string]$line)
        }
    }
    if ($exitCode -ne 0) {
        throw "$StepName 失败，退出码：$exitCode。完整日志：$script:InstallLogPath"
    }
    return $exitCode
}

function Invoke-InstallCommand {
    param(
        [string]$PythonExe,
        [string[]]$Arguments,
        [System.Windows.Forms.TextBox]$LogBox,
        [string]$StepName,
        [string]$StandardInput = $null
    )
    [void](Invoke-ExternalProcess $PythonExe $Arguments $LogBox $StepName $StandardInput)
}

function Ensure-Directory {
    param([string]$Path)
    if (-not $Path) {
        return
    }
    $target = $Path
    if (-not [System.IO.Path]::IsPathRooted($target)) {
        $target = Join-Path $ProjectRoot $target
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}

$envValues = Read-EnvFile $EnvPath
$defaultModelDir = Join-Path $ProjectRoot "model_files"
$defaultImportDir = Join-Path $ProjectRoot "import_files"
$defaultBackupDir = Join-Path $ProjectRoot "backups"
$defaultStaticRoot = Join-Path $ProjectRoot "staticfiles"
$embeddedRuntimeArchive = Get-EmbeddedRuntimeArchive
$runtimeStatus = "运行时：使用本机 Python/Conda"
if (Test-Path $embeddedRuntimeArchive) {
    $runtimeStatus = "运行时：内置离线运行时"
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "AIGDM 安装向导"
$form.StartPosition = "CenterScreen"
$workingArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$formWidth = [Math]::Min(980, [Math]::Max(640, $workingArea.Width - 80))
$formHeight = [Math]::Min(760, [Math]::Max(480, $workingArea.Height - 80))
$minFormWidth = [Math]::Min(760, [Math]::Max(520, $workingArea.Width - 120))
$minFormHeight = [Math]::Min(560, [Math]::Max(420, $workingArea.Height - 120))
$form.Size = New-Object System.Drawing.Size($formWidth, $formHeight)
$form.MinimumSize = New-Object System.Drawing.Size($minFormWidth, $minFormHeight)
$form.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$form.AutoScaleMode = "Dpi"

$formLayout = New-Object System.Windows.Forms.TableLayoutPanel
$formLayout.Dock = "Fill"
$formLayout.ColumnCount = 1
$formLayout.RowCount = 2
$formLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
$formLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 52))) | Out-Null
$form.Controls.Add($formLayout)

$scrollHost = New-Object System.Windows.Forms.Panel
$scrollHost.Dock = "Fill"
$scrollHost.AutoScroll = $true
$formLayout.Controls.Add($scrollHost, 0, 0)

$root = New-Object System.Windows.Forms.TableLayoutPanel
$root.Dock = "Top"
$root.AutoSize = $true
$root.AutoSizeMode = "GrowAndShrink"
$root.ColumnCount = 1
$root.RowCount = 4
$root.Padding = New-Object System.Windows.Forms.Padding(14)
$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 62))) | Out-Null
$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 304))) | Out-Null
$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 204))) | Out-Null
$root.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 180))) | Out-Null
$root.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100))) | Out-Null
$scrollHost.Controls.Add($root)

$resizeContent = {
    $availableWidth = $scrollHost.ClientSize.Width - 4
    if ($availableWidth -lt 760) {
        $availableWidth = 760
    }
    $root.Width = $availableWidth
}
$scrollHost.Add_Resize($resizeContent)
$form.Add_Shown($resizeContent)

$titlePanel = New-Object System.Windows.Forms.TableLayoutPanel
$titlePanel.Dock = "Fill"
$titlePanel.RowCount = 2
$titlePanel.ColumnCount = 1
$titlePanel.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 34))) | Out-Null
$titlePanel.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Absolute, 24))) | Out-Null
$root.Controls.Add($titlePanel, 0, 0)

$title = New-Object System.Windows.Forms.Label
$title.Text = "AIGDM 一键安装配置"
$title.Dock = "Fill"
$title.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 15, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(17, 97, 107)
$title.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$title.AutoEllipsis = $true
$titlePanel.Controls.Add($title, 0, 0)

$runtimeLabel = New-Object System.Windows.Forms.Label
$runtimeLabel.Text = $runtimeStatus
$runtimeLabel.Dock = "Fill"
$runtimeLabel.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$runtimeLabel.ForeColor = [System.Drawing.Color]::FromArgb(89, 99, 110)
$runtimeLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
$runtimeLabel.AutoEllipsis = $true
$titlePanel.Controls.Add($runtimeLabel, 0, 1)

$topPanel = New-Object System.Windows.Forms.TableLayoutPanel
$topPanel.Dock = "Fill"
$topPanel.ColumnCount = 2
$topPanel.RowCount = 1
$topPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50))) | Out-Null
$topPanel.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 50))) | Out-Null
$root.Controls.Add($topPanel, 0, 1)

$dbGroup = New-InstallerGroupBox "MySQL 配置"
$topPanel.Controls.Add($dbGroup, 0, 0)

$dbTable = New-InputTable 6 116 32
$dbGroup.Controls.Add($dbTable)

$txtDbHost = New-TextBox (Get-EnvDefault $envValues "AIGDM_DB_HOST" "127.0.0.1")
$txtDbPort = New-TextBox (Get-EnvDefault $envValues "AIGDM_DB_PORT" "3306")
$txtDbName = New-TextBox (Get-EnvDefault $envValues "AIGDM_DB_NAME" "aigdm")
$txtDbUser = New-TextBox (Get-EnvDefault $envValues "AIGDM_DB_USER" "aigdm")
$txtDbPassword = New-TextBox (Get-EnvDefault $envValues "AIGDM_DB_PASSWORD" "") $true
$txtAllowedHosts = New-TextBox (Get-EnvDefault $envValues "AIGDM_ALLOWED_HOSTS" "127.0.0.1,localhost,aigdm.local")

Add-Field $dbTable "MySQL 地址" $txtDbHost 0
Add-Field $dbTable "MySQL 端口" $txtDbPort 1
Add-Field $dbTable "数据库名" $txtDbName 2
Add-Field $dbTable "数据库用户" $txtDbUser 3
Add-Field $dbTable "数据库密码" $txtDbPassword 4
Add-Field $dbTable "允许访问主机" $txtAllowedHosts 5

$adminGroup = New-InstallerGroupBox "系统管理员与启动"
$topPanel.Controls.Add($adminGroup, 1, 0)

$adminTable = New-InputTable 7 132 32
$adminGroup.Controls.Add($adminTable)

$txtAdminUsername = New-TextBox (Get-EnvDefault $envValues "AIGDM_ADMIN_USERNAME" "aigdm_admin")
$txtAdminPassword = New-TextBox "" $true
$txtAdminPasswordConfirm = New-TextBox "" $true
$txtHostAddress = New-TextBox "127.0.0.1"
$txtPort = New-TextBox "8001"
$chkSampleData = New-Object System.Windows.Forms.CheckBox
$chkSampleData.Text = "写入演示样例数据"
$chkSampleData.Checked = $false
$chkSampleData.Dock = "Fill"
$chkSampleData.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)
$chkStartAfterInstall = New-Object System.Windows.Forms.CheckBox
$chkStartAfterInstall.Text = "安装完成后启动本机服务"
$chkStartAfterInstall.Checked = $true
$chkStartAfterInstall.Dock = "Fill"
$chkStartAfterInstall.Margin = New-Object System.Windows.Forms.Padding(4, 4, 4, 4)

Add-Field $adminTable "管理员用户名" $txtAdminUsername 0
Add-Field $adminTable "管理员密码" $txtAdminPassword 1
Add-Field $adminTable "确认密码" $txtAdminPasswordConfirm 2
Add-Field $adminTable "启动地址" $txtHostAddress 3
Add-Field $adminTable "启动端口" $txtPort 4
$adminTable.Controls.Add($chkSampleData, 1, 5)
$adminTable.Controls.Add($chkStartAfterInstall, 1, 6)

$dirGroup = New-InstallerGroupBox "数据目录"
$root.Controls.Add($dirGroup, 0, 2)

$dirTable = New-InputTable 4 126 34
$dirGroup.Controls.Add($dirTable)

$txtModelDir = New-TextBox (Get-EnvDefault $envValues "AIGDM_MODEL_DIR" $defaultModelDir) $false 620
$txtImportDir = New-TextBox (Get-EnvDefault $envValues "AIGDM_IMPORT_DIR" $defaultImportDir) $false 620
$txtBackupDir = New-TextBox (Get-EnvDefault $envValues "AIGDM_BACKUP_DIR" $defaultBackupDir) $false 620
$txtStaticRoot = New-TextBox (Get-EnvDefault $envValues "AIGDM_STATIC_ROOT" $defaultStaticRoot) $false 620

Add-Field $dirTable "模型目录" $txtModelDir 0
Add-Field $dirTable "导入目录" $txtImportDir 1
Add-Field $dirTable "备份目录" $txtBackupDir 2
Add-Field $dirTable "静态文件目录" $txtStaticRoot 3

$logBox = New-Object System.Windows.Forms.TextBox
$logBox.Dock = "Fill"
$logBox.Multiline = $true
$logBox.ScrollBars = "Vertical"
$logBox.ReadOnly = $true
$logBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$root.Controls.Add($logBox, 0, 3)

$buttonPanel = New-Object System.Windows.Forms.FlowLayoutPanel
$buttonPanel.Dock = "Fill"
$buttonPanel.FlowDirection = "RightToLeft"
$buttonPanel.Padding = New-Object System.Windows.Forms.Padding(14, 8, 14, 8)
$formLayout.Controls.Add($buttonPanel, 0, 1)

$btnInstall = New-Object System.Windows.Forms.Button
$btnInstall.Text = "开始安装"
$btnInstall.Width = 110
$btnInstall.Height = 32
$btnInstall.BackColor = [System.Drawing.Color]::FromArgb(17, 97, 107)
$btnInstall.ForeColor = [System.Drawing.Color]::White
$btnInstall.FlatStyle = "Flat"
$buttonPanel.Controls.Add($btnInstall)

$btnTestDb = New-Object System.Windows.Forms.Button
$btnTestDb.Text = "测试 MySQL"
$btnTestDb.Width = 110
$btnTestDb.Height = 32
$buttonPanel.Controls.Add($btnTestDb)

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = "退出"
$btnClose.Width = 80
$btnClose.Height = 32
$buttonPanel.Controls.Add($btnClose)

$btnClose.Add_Click({ $form.Close() })

function Get-SetupArgs {
    return @(
        "manage.py", "setup_env",
        "--non-interactive",
        "--db-engine", "mysql",
        "--db-host", $txtDbHost.Text.Trim(),
        "--db-port", $txtDbPort.Text.Trim(),
        "--db-name", $txtDbName.Text.Trim(),
        "--db-user", $txtDbUser.Text.Trim(),
        "--db-password", $txtDbPassword.Text,
        "--model-dir", $txtModelDir.Text.Trim(),
        "--import-dir", $txtImportDir.Text.Trim(),
        "--backup-dir", $txtBackupDir.Text.Trim(),
        "--static-root", $txtStaticRoot.Text.Trim(),
        "--allowed-hosts", $txtAllowedHosts.Text.Trim(),
        "--admin-username", $txtAdminUsername.Text.Trim()
    )
}

function Validate-Inputs {
    foreach ($item in @(
        @("MySQL 地址", $txtDbHost.Text),
        @("MySQL 端口", $txtDbPort.Text),
        @("数据库名", $txtDbName.Text),
        @("数据库用户", $txtDbUser.Text),
        @("数据库密码", $txtDbPassword.Text),
        @("管理员用户名", $txtAdminUsername.Text),
        @("管理员密码", $txtAdminPassword.Text),
        @("启动端口", $txtPort.Text)
    )) {
        if (-not $item[1].Trim()) {
            throw "$($item[0])不能为空。"
        }
    }
    [void][int]::Parse($txtDbPort.Text.Trim())
    [void][int]::Parse($txtPort.Text.Trim())
    if ($txtAdminPassword.Text -ne $txtAdminPasswordConfirm.Text) {
        throw "两次输入的管理员密码不一致。"
    }
}

$btnTestDb.Add_Click({
    try {
        Validate-Inputs
        $btnTestDb.Enabled = $false
        $btnInstall.Enabled = $false
        Append-Log $logBox "==> 测试 MySQL 配置"
        $python = Resolve-AigdmPython $logBox
        Invoke-InstallCommand $python (Get-SetupArgs) $logBox "写入配置并测试 MySQL"
        Append-Log $logBox "[OK] MySQL 配置可用，.env 已更新：$EnvPath"
    } catch {
        Append-Log $logBox "[FAILED] $($_.Exception.ToString())"
        [System.Windows.Forms.MessageBox]::Show(($_.Exception.Message + [Environment]::NewLine + [Environment]::NewLine + "完整日志：" + $script:InstallLogPath), "MySQL 测试失败", "OK", "Error") | Out-Null
    } finally {
        $btnTestDb.Enabled = $true
        $btnInstall.Enabled = $true
    }
})

$btnInstall.Add_Click({
    try {
        Validate-Inputs
        $btnTestDb.Enabled = $false
        $btnInstall.Enabled = $false
        $logBox.Clear()
        $python = Resolve-AigdmPython $logBox
        Append-Log $logBox "AIGDM 安装开始"
        Append-Log $logBox "应用目录：$ProjectRoot"
        Append-Log $logBox "Python：$python"

        Invoke-InstallCommand $python (Get-SetupArgs) $logBox "写入配置并测试 MySQL"

        Ensure-Directory $txtModelDir.Text.Trim()
        Ensure-Directory $txtImportDir.Text.Trim()
        Ensure-Directory $txtBackupDir.Text.Trim()
        Ensure-Directory $txtStaticRoot.Text.Trim()
        Append-Log $logBox "[OK] 数据目录已准备"

        Invoke-InstallCommand $python @("manage.py", "check") $logBox "检查 Django 项目"
        Invoke-InstallCommand $python @("manage.py", "migrate") $logBox "应用数据库迁移"

        $initArgs = @("manage.py", "initialize_system", "--create-admin", "--admin-username", $txtAdminUsername.Text.Trim(), "--admin-password-stdin-base64")
        if ($chkSampleData.Checked) {
            $initArgs += "--with-sample-data"
        }
        $adminPasswordPayload = ConvertTo-Base64Utf8 $txtAdminPassword.Text
        if (-not (Test-Base64Text $adminPasswordPayload)) {
            throw "管理员密码传输格式生成失败。"
        }
        Invoke-InstallCommand -PythonExe $python -Arguments $initArgs -LogBox $logBox -StepName "初始化角色、默认权限、规则和管理员" -StandardInput $adminPasswordPayload
        Invoke-InstallCommand $python @("manage.py", "collectstatic", "--noinput") $logBox "收集静态文件"
        Invoke-InstallCommand $python @("manage.py", "doctor") $logBox "生成部署检查报告"

        if ($chkStartAfterInstall.Checked) {
            $startScript = Join-Path $ProjectRoot "start-aigdm.ps1"
            $startCommand = "`$scriptPath = `"$startScript`"; `$script = [scriptblock]::Create([System.IO.File]::ReadAllText(`$scriptPath, [System.Text.Encoding]::UTF8)); & `$script -HostAddress `"$($txtHostAddress.Text.Trim())`" -Port $($txtPort.Text.Trim()) -SkipDoctor"
            Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $startCommand) -WorkingDirectory $ProjectRoot | Out-Null
            Append-Log $logBox "[OK] 已启动服务窗口：http://$($txtHostAddress.Text.Trim()):$($txtPort.Text.Trim())/"
        }

        Append-Log $logBox "[DONE] 安装完成。"
        [System.Windows.Forms.MessageBox]::Show("AIGDM 安装完成。", "安装完成", "OK", "Information") | Out-Null
    } catch {
        Append-Log $logBox "[FAILED] $($_.Exception.ToString())"
        [System.Windows.Forms.MessageBox]::Show(($_.Exception.Message + [Environment]::NewLine + [Environment]::NewLine + "完整日志：" + $script:InstallLogPath), "安装失败", "OK", "Error") | Out-Null
    } finally {
        $btnTestDb.Enabled = $true
        $btnInstall.Enabled = $true
    }
})

Append-Log $logBox "请填写 MySQL 和管理员配置，然后点击“开始安装”。"
Append-Log $logBox "提示：MySQL 数据库和账号需要先在 MySQL 中创建，并授予该数据库权限。"
Append-Log $logBox $runtimeStatus

[void]$form.ShowDialog()
