param([string]$ExpectedSid = '')
$ErrorActionPreference = 'Stop'
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $sid = $identity.User.Value
    if ($ExpectedSid -and $ExpectedSid -ne $sid) {
        throw 'Use the SAME Windows administrator account that runs Live Desk and OBS.'
    }
    if (Get-Process obs64,obs32 -ErrorAction SilentlyContinue) {
        throw 'Finish all live/recording outputs, then close OBS normally and run this setup again. No OBS was stopped.'
    }
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -ExpectedSid "' + $sid + '"'
        $child = Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
        exit $child.ExitCode
    }
    $root = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'obs-studio'
    $exe = Join-Path $root 'bin\64bit\obs64.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Standard 64-bit OBS installation is required.' }
    if ((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion -notmatch '^32\.') {
        throw 'This layout helper was validated for OBS 32 on Windows x64.'
    }
    $payloadPath = Join-Path $PSScriptRoot 'OBS-LAYOUT-PAYLOAD.txt'
    if (-not (Test-Path -LiteralPath $payloadPath -PathType Leaf)) { throw 'Layout helper payload is missing. Install the complete Live Desk update.' }
    $text = [IO.File]::ReadAllText($payloadPath)
    if ($text.Length -gt 1048576) { throw 'Layout helper payload exceeds its limit.' }
    $parts = $text -split "`n",2
    if ($parts.Length -ne 2 -or $parts[0].Trim() -notmatch '^sha256:([a-f0-9]{64})$') { throw 'Invalid layout helper payload.' }
    $expectedHash = $Matches[1]
    $bytes = [Convert]::FromBase64String($parts[1])
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = ([BitConverter]::ToString($hasher.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    if ($hash -ne $expectedHash) { throw 'Layout helper checksum mismatch. Nothing was installed.' }
    $destination = Join-Path $root 'obs-plugins\64bit\live-desk-layout.dll'
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $destination) -PathType Container)) { throw 'OBS plugin directory is missing.' }
    [IO.File]::WriteAllBytes($destination,$bytes)
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Installed helper checksum verification failed.' }
    Write-Host 'READY: OBS layout protection installed. Open OBS using Live Desk, then Check connections.'
    Write-Host 'No scenes, profiles, stream keys, logins or live outputs were changed.'
    Read-Host 'Press Enter to finish'
    exit 0
} catch {
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Press Enter to finish'
    exit 1
}
