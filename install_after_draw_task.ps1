$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$python=(Get-Command python -ErrorAction SilentlyContinue).Source
if(-not $python){$python=(Get-Command py -ErrorAction Stop).Source}
$action=New-ScheduledTaskAction -Execute $python -Argument ('"'+(Join-Path $root 'cloud_pipeline.py')+'"') -WorkingDirectory $root
$triggers=@()
foreach($day in @('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')){$triggers+=New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At '20:40'}
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'TW539 開獎後全自動更新同步' -Action $action -Trigger $triggers -Settings $settings -Description '官方開獎後更新資料、重算戰報並同步手機雲端' -Force | Out-Null
Write-Host '已安裝：TW539 開獎後全自動更新同步'
