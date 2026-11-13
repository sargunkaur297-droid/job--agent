# Removes the daily task:  powershell -ExecutionPolicy Bypass -File scripts\unschedule_windows.ps1
Unregister-ScheduledTask -TaskName "JobAgentDaily" -Confirm:$false
Write-Host "Daily Job Agent task removed."
