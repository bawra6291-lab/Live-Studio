param([string]$ExpectedSid = '', [switch]$Remove)
$ErrorActionPreference = 'Stop'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $identity.User.Value
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($ExpectedSid -and $ExpectedSid -ne $sid) {
        throw 'Use the SAME Windows administrator account that runs Live Desk. Another account would use different OBS settings.'
    }
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host 'Approve the Windows UAC prompt once to configure administrator OBS launch.'
        # Quote the script path for Windows argument parsing; no shell command string.
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -ExpectedSid "' + $sid + '"'
        if ($Remove) { $arguments += ' -Remove' }
        $child = Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
        exit $child.ExitCode
    }
    $taskName = 'ISKCON-OBS-Admin-' + $sid
    if ($Remove) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host 'Administrator launch task removed. OBS and broadcasts were not stopped.'
    } else {
        $exe = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'obs-studio\bin\64bit\obs64.exe'
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw 'Install OBS in C:\Program Files\obs-studio first. This setup supports the standard 64-bit OBS installation.'
        }
        $action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory (Split-Path -Parent $exe)
        $user = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $task = New-ScheduledTask -Action $action -Principal $user -Settings $settings -Description 'Open installed OBS visibly as administrator for this Windows user. On demand only. Does not start or stop a stream.'
        Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
        Write-Host 'READY: Live Desk can now launch OBS as administrator in your logged-in desktop.'
        Write-Host 'No OBS restart was performed. An already-open OBS keeps its current privilege level.'
        Write-Host 'When idle, close OBS normally, then use Open / Show OBS in Live Desk.'
    }
    Read-Host 'Press Enter to finish'
    exit 0
} catch {
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Press Enter to finish'
    exit 1
}
