# Registers a daily Windows scheduled task that runs the Job Agent scan.
# Usage (from the project folder, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\schedule_windows.ps1 -Time 09:00
# Change the time any time by running it again with a different -Time (24-hour clock, your PC's local time).
param([string]$Time = "09:00")

$root = Split-Path -Parent $PSScriptRoot
$bat  = Join-Path $PSScriptRoot "run_daily.bat"
if (-not (Test-Path $bat)) { Write-Error "run_daily.bat not found next to this script."; exit 1 }

$action   = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: if the PC was off/asleep at that time, run as soon as it is back on.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "JobAgentDaily" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily Job Agent scan + email digest" -Force | Out-Null

Write-Host "Done. The scan will run every day at $Time."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName JobAgentDaily"
Write-Host "Then check the log: $root\data\run.log"
