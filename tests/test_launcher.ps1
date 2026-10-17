$ErrorActionPreference = 'Stop'
$original = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\start_momotalk.ps1') -Raw
$original = $original.Replace('& $basePython @pythonArgs', 'Invoke-FakePython').Replace('& $python', 'Invoke-FakePython').Replace('& $adb', 'Invoke-FakeAdb')
$cases = @(
    @{ Name='fresh venv'; Fresh=$true; MissingDeps=$true; Devices=@('emulator-5556') },
    @{ Name='old venv'; Old=$true; Devices=@('emulator-5556'); Error='版本过旧' },
    @{ Name='manual ADB and bare port'; Manual=$true; Port='16385'; Devices=@(); Expected='127.0.0.1:16385' },
    @{ Name='full address'; Port='127.0.0.1:16386'; Devices=@(); Expected='127.0.0.1:16386' },
    @{ Name='diagnostic comma ports'; Port='5555,16387'; Devices=@(); Expected='127.0.0.1:16387' },
    @{ Name='invalid port'; Port='65536'; Devices=@(); Error='有效的本地' },
    @{ Name='multiple devices'; Devices=@('emulator-5556','emulator-5558'); Choice='2'; ExpectedSerial='emulator-5558' },
    @{ Name='invalid device selection'; Devices=@('emulator-5556','emulator-5558'); Choice='3'; Error='设备编号无效' }
)
foreach ($case in $cases) {
    & {
        param($case, $original)
        $script:events = [Collections.Generic.List[string]]::new()
        $script:created = $false
        $script:installed = $false
        $script:connected = $false
        $script:launched = $false
        $script:messages = [Collections.Generic.List[string]]::new()
        function Test-Path {
            param($LiteralPath, $PathType)
            if ($LiteralPath -like '*python.exe') { return (-not $case.Fresh -or $script:created) }
            if ($LiteralPath -eq 'C:\fake\adb.exe') { return $true }
            return (-not $case.Manual)
        }
        function Get-Command { param($Name, $ErrorAction); return @{Source='fake-python.exe'} }
        function Get-ItemProperty { return @() }
        function Read-Host {
            param($Prompt)
            if ($Prompt -like '*完整路径*') { return 'C:\fake\adb.exe' }
            if ($Prompt -like '*端口或地址*') { return $case.Port }
            if ($Prompt -like '*设备编号*') { return $case.Choice }
            return ''
        }
        function Write-Host { param($Object, $ForegroundColor); $script:messages.Add([string]$Object) }
        function Invoke-FakePython {
            $script:events.Add('python ' + ($args -join ' '))
            $global:LASTEXITCODE = 0
            if ($args -contains 'venv') { $script:created=$true }
            elseif ($args -contains 'pip') { $script:installed=$true }
            elseif (($args -join ' ') -like '*version_info*' -and $case.Old) { $global:LASTEXITCODE=1 }
            elseif (($args -join ' ') -like '*import numpy*' -and $case.MissingDeps -and -not $script:installed) { $global:LASTEXITCODE=1 }
            elseif ($args -contains '-u') {
                $script:launched=$true
                if ($case.ExpectedSerial -and $args[$args.IndexOf('--serial')+1] -ne $case.ExpectedSerial) { throw 'Wrong device' }
            }
        }
        function Invoke-FakeAdb {
            $script:events.Add('adb ' + ($args -join ' '))
            if ($args[0] -eq 'connect' -and $args[1] -eq $case.Expected) { $script:connected=$true }
            if ($args[0] -eq 'devices') {
                'List of devices attached'
                if ($script:connected) { "$($case.Expected)`tdevice" }
                else { foreach ($device in $case.Devices) { "$device`tdevice" } }
            }
        }
        $before = Get-Location
        try { & ([scriptblock]::Create($original.Replace('Set-Location -LiteralPath $PSScriptRoot','').Replace("Join-Path `$PSScriptRoot", "Join-Path 'C:\fake'"))) }
        finally { Set-Location $before }
        $messages = $script:messages -join "`n"
        if ($case.Error) {
            if ($messages -notlike "*$($case.Error)*" -or $script:launched) { throw "FAIL $($case.Name): $messages" }
        } else {
            if (-not $script:launched) { throw "FAIL $($case.Name): $messages" }
            if ($case.Fresh -and (-not $script:created -or -not $script:installed)) { throw 'Fresh setup skipped' }
            if ($case.Expected -and -not $script:connected) { throw 'Port normalization failed' }
        }
        Microsoft.PowerShell.Utility\Write-Host "PASS $($case.Name)"
    } $case $original
}
