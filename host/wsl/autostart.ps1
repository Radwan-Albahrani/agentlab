# agentlab on WSL: start the distro at boot and again whenever it stops (a crash, Windows killing WSL when RAM
# runs out, a stray wsl --shutdown). `agentctl apply` sets $Distro and registers this as the \agentlab\Autostart
# task's encoded command. To keep WSL down on purpose: Stop-ScheduledTask -TaskPath '\agentlab\' -TaskName Autostart
$env:WSL_UTF8 = 1
$dir = Join-Path $env:LOCALAPPDATA 'agentlab'
New-Item -ItemType Directory -Force $dir | Out-Null
$log = Join-Path $dir 'autostart.log'
function Log($msg) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 1MB) { Move-Item $log "$log.old" -Force }
    "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $msg | Add-Content $log
}

Log "=== autostart for $Distro"
$wait = 15
while ($true) {
    $started = Get-Date
    Log 'starting the distro (systemd brings up Docker and the agents)'
    # WSL stops a distro once no wsl.exe client is attached; this returns only when the distro goes down.
    wsl.exe -d $Distro -u root --exec /bin/sleep infinity
    Log "the distro stopped (exit $LASTEXITCODE)"
    # Back off while it keeps failing (up to 5 min); a run that lasted over 10 min starts again at 15 s.
    $wait = if (((Get-Date) - $started).TotalMinutes -gt 10) { 15 } else { [Math]::Min($wait * 2, 300) }
    Log "starting it again in $wait s"
    Start-Sleep $wait
}
