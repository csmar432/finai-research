# ─────────────────────────────────────────────────────────────────────────────
# scripts/install_service.ps1 — Cross-platform service installer for Windows
#
# Wraps scripts/event_monitor.py as a Windows Task Scheduler job, replacing the
# missing cross-platform --daemon flag (os.fork() is Unix-only).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1 -Action Install
#   powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1 -Action Start
#   powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1 -Action Stop
#   powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1 -Action Uninstall
#   powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1 -Action Status
#
# Equivalent on:
#   Linux:  config/daemon/setup-daemon.sh linux  (systemd)
#   macOS:  config/daemon/setup-daemon.sh macos  (launchd)
#
# Notes:
#   - Runs as the current user (does not require admin)
#   - Restarts on failure (Task Scheduler built-in)
#   - Log file: logs/monitor-stdout.log / monitor-stderr.log (relative to repo root)
# ─────────────────────────────────────────────────────────────────────────────

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Start", "Stop", "Uninstall", "Status")]
    [string]$Action,

    [string]$TaskName = "FinAI Event Monitor",
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Stop"

# ── Resolve paths ─────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = (Get-Command python).Source
}
$EventMonitor = Join-Path $ProjectRoot "scripts\event_monitor.py"
$LogDir = Join-Path $ProjectRoot "logs"
$StdoutLog = Join-Path $LogDir "monitor-stdout.log"
$StderrLog = Join-Path $LogDir "monitor-stderr.log"

# ── Action handlers ───────────────────────────────────────────────────────────

function Install-Task {
    if (-not (Test-Path $VenvPython)) {
        throw "Python not found at $VenvPython. Create venv first: python -m venv .venv"
    }
    if (-not (Test-Path $EventMonitor)) {
        throw "event_monitor.py not found at $EventMonitor"
    }
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }

    # Remove existing task with same name (clean reinstall)
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Removing existing task '$TaskName'..."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    $action = New-ScheduledTaskAction `
        -Execute "$VenvPython" `
        -Argument "-u `"$EventMonitor`" --interval $IntervalSeconds --auto-trigger" `
        -WorkingDirectory "$ProjectRoot"

    # Trigger: at user logon (one-shot) + repeat every IntervalSeconds for up to 1 day
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 5 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "FinAI Research Workflow — Event-Driven Research Trigger Monitor. Polls earnings/macro/policy events every $IntervalSeconds seconds and triggers the research pipeline." `
        | Out-Null

    Write-Host "Installed scheduled task '$TaskName'."
    Write-Host "  Python: $VenvPython"
    Write-Host "  Script: $EventMonitor --interval $IntervalSeconds --auto-trigger"
    Write-Host "  Logs:   $StdoutLog / $StderrLog"
    Write-Host ""
    Write-Host "Start with: powershell $PSCommandPath -Action Start"
}

function Start-Task {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Started '$TaskName'."
}

function Stop-Task {
    Stop-ScheduledTask -TaskName $TaskName
    Write-Host "Stopped '$TaskName'."
}

function Uninstall-Task {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Uninstalled '$TaskName'."
}

function Get-Status {
    $info = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $info) {
        Write-Host "Task '$TaskName' is not installed."
        return
    }
    $running = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
    Write-Host "Task:    $TaskName"
    Write-Host "State:   $($info.State)"
    Write-Host "LastRun: $($running.LastRunTime)"
    Write-Host "NextRun: $($running.NextRunTime)"
    Write-Host "Result:  $($running.LastTaskResult)"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
switch ($Action) {
    "Install"   { Install-Task }
    "Start"     { Start-Task }
    "Stop"      { Stop-Task }
    "Uninstall" { Uninstall-Task }
    "Status"    { Get-Status }
}
