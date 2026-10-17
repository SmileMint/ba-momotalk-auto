$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$forwardArgs = @($args)
try {
    $scriptPath = Join-Path $PSScriptRoot 'ba_momotalk_auto.py'
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $basePython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
        $pythonArgs = @()
        if (-not $basePython -or $basePython -like '*WindowsApps*') {
            $basePython = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
            $pythonArgs = @('-3')
        }
        if (-not $basePython) { throw '找不到 Python。请安装 Python 3.10 或更新版本，再重新双击启动。' }
        & $basePython @pythonArgs -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        if ($LASTEXITCODE -ne 0) { throw '需要 Python 3.10 或更新版本。' }
        Write-Host '首次启动：正在创建项目虚拟环境……'
        & $basePython @pythonArgs -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw '虚拟环境创建失败。请检查 Python 安装和文件夹写入权限。' }
    }
    & $python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '项目 .venv 的 Python 版本过旧或无法运行。请删除项目目录中的 .venv 后重新启动，以使用 Python 3.10 或更新版本重建。' }
    # Missing imports are an expected probe result in a new virtual environment.
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $python -c 'import numpy, PIL, cv2' 2>$null
        $dependencyExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    if ($dependencyExitCode -ne 0) {
        Write-Host '正在安装运行依赖到项目虚拟环境……'
        & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络后重试。' }
    }
    $adb = @('D:\MuMu Player 12\shell\adb.exe', 'D:\MuMuPlayer-12.0\shell\adb.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $adb) {
        $installations = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'MuMu' -and $_.InstallLocation }
        $adb = $installations | ForEach-Object { Join-Path $_.InstallLocation 'shell\adb.exe' } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    }
    if (-not $adb) {
        $adb = Read-Host '请输入 MuMu 的 adb.exe 完整路径（无需引号）'
        $adb = $adb.Trim('"')
        if (-not (Test-Path -LiteralPath $adb -PathType Leaf)) { throw 'ADB 路径不存在。' }
    }
    & $adb start-server
    $devices = @(& $adb devices | ForEach-Object {
        if ($_ -match '^(\S+)\s+device\s*$') { $Matches[1] }
    })
    if ($devices.Count -eq 0) {
        & $adb connect '127.0.0.1:16384'
        $devices = @(& $adb devices | ForEach-Object {
            if ($_ -match '^(\S+)\s+device\s*$') { $Matches[1] }
        })
    }
    if ($devices.Count -eq 0) {
        $inputAddress = (Read-Host '未发现设备。请输入 ADB 端口或地址（16384 / 127.0.0.1:16384 / 5555,16384）').Trim()
        $portText = $null
        if ($inputAddress -match '^127\.0\.0\.1:(\d+)$') { $portText = $Matches[1] }
        elseif ($inputAddress -match '^\d+(\s*,\s*\d+)*$') { $portText = ($inputAddress -split ',')[-1].Trim() }
        $port = 0
        if (-not $portText -or -not [int]::TryParse($portText, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
            throw '请输入有效的本地 ADB 端口（1–65535）或 127.0.0.1:端口。'
        }
        $address = "127.0.0.1:$port"
        & $adb connect $address
        $devices = @(& $adb devices | ForEach-Object { if ($_ -match '^(\S+)\s+device\s*$') { $Matches[1] } })
        if ($devices.Count -eq 0) { throw '连接失败，请检查模拟器的 ADB 调试端口。' }
    }
    if ($devices.Count -eq 1) { $serial = $devices[0] }
    else {
        Write-Host '检测到多个设备：'
        for ($i = 0; $i -lt $devices.Count; $i++) { Write-Host "$($i + 1). $($devices[$i])" }
        $selection = Read-Host '请选择运行碧蓝档案的设备编号'
        $number = 0
        if (-not [int]::TryParse($selection, [ref]$number) -or $number -lt 1 -or $number -gt $devices.Count) { throw '设备编号无效。' }
        $serial = $devices[$number - 1]
    }
    Write-Host "开始运行，设备：$serial。按 Ctrl+C 可停止。" -ForegroundColor Green
    Write-Host '请确保游戏处于主界面或 MomoTalk 界面。'
    & $python -u $scriptPath --adb $adb --serial $serial @forwardArgs
    Write-Host "脚本已结束，退出码：$LASTEXITCODE"
} catch {
    Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
} finally {
    Read-Host '按回车关闭窗口'
}
