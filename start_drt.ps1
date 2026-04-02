<#
.SYNOPSIS
    AI DRT System - Windows deployment script with background mode and log collection.

.DESCRIPTION
    Start/Stop/Check the DRT Flask server on Windows.
    Logs are saved to the logs/ directory with daily rotation.

.PARAMETER Stop
    Stop the running DRT server.

.PARAMETER Restart
    Restart the DRT server (stop then start).

.PARAMETER Status
    Check if the DRT server is running.

.PARAMETER Port
    Port number (default: 5001).

.EXAMPLE
    .\start_drt.ps1              # Start server in background
    .\start_drt.ps1 -Stop        # Stop server
    .\start_drt.ps1 -Restart     # Restart server
    .\start_drt.ps1 -Status      # Check status
    .\start_drt.ps1 Restart      # Also works without dash
#>

param(
    [Parameter(Position=0)]
    [ValidateSet('Stop','Restart','Status','')]
    [string]$Action,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Status,
    [int]$Port = 5001
)

# Map positional $Action to switches
if ($Action) {
    switch ($Action) {
        'Stop'    { $Stop    = $true }
        'Restart' { $Restart = $true }
        'Status'  { $Status  = $true }
    }
}

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ScriptDir "logs"
$PidFile = Join-Path $ScriptDir "logs\drt.pid"
$AppFile = Join-Path $ScriptDir "app.py"
$EnvFile = Join-Path $ScriptDir ".env"
$DateStr = Get-Date -Format "yyyyMMdd"
$LogFile = Join-Path $LogDir "drt_$DateStr.log"
$ErrorLogFile = Join-Path $LogDir "drt_error_$DateStr.log"
$ScriptLogFile = Join-Path $LogDir "drt_script_$DateStr.log"

# Ensure logs directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$timestamp] [$Level] $Message"
    Write-Host $entry
    Add-Content -Path $ScriptLogFile -Value $entry -Encoding UTF8
}

function Find-Python {
    # Try venv first
    $venvPython = Join-Path $ScriptDir "..\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return (Resolve-Path $venvPython).Path }

    $venvPython2 = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython2) { return (Resolve-Path $venvPython2).Path }

    # Try system python
    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPython) { return $sysPython.Source }

    return $null
}

function Get-RunningProcess {
    if (Test-Path $PidFile) {
        $savedPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($savedPid) {
            $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
            if ($proc -and $proc.ProcessName -match "python") {
                return $proc
            }
        }
    }
    # Fallback: find by command line
    Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object {
        try {
            $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            $cmdline -and $cmdline -match "app\.py"
        } catch { $false }
    } | Select-Object -First 1
}

# --- Status ---
if ($Status) {
    $proc = Get-RunningProcess
    if ($proc) {
        Write-Host "DRT System is RUNNING (PID: $($proc.Id))" -ForegroundColor Green
        Write-Host "  URL: http://localhost:$Port"
        Write-Host "  Log: $LogFile"
        if (Test-Path $ErrorLogFile) {
            $errCount = (Get-Content $ErrorLogFile -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
            Write-Host "  Errors: $errCount lines in $ErrorLogFile" -ForegroundColor $(if ($errCount -gt 0) {"Yellow"} else {"Gray"})
        }
    } else {
        Write-Host "DRT System is NOT running." -ForegroundColor Yellow
    }
    exit 0
}

# --- Stop ---
if ($Stop) {
    $proc = Get-RunningProcess
    if ($proc) {
        Write-Log "Stopping DRT System (PID: $($proc.Id))..."
        Stop-Process -Id $proc.Id -Force
        Start-Sleep -Seconds 1
        if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
        Write-Log "DRT System stopped."
        Write-Host "DRT System stopped." -ForegroundColor Green
    } else {
        Write-Host "DRT System is not running." -ForegroundColor Yellow
    }
    exit 0
}

# --- Restart ---
if ($Restart) {
    $proc = Get-RunningProcess
    if ($proc) {
        Write-Log "Restarting DRT System (PID: $($proc.Id))..."
        Stop-Process -Id $proc.Id -Force
        if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
        # Wait for process to exit and port to be released
        $waitMax = 10
        for ($i = 0; $i -lt $waitMax; $i++) {
            Start-Sleep -Seconds 1
            $still = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
            $portBusy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
                Where-Object { $_.State -eq 'Listen' }
            if (-not $still -and -not $portBusy) { break }
            Write-Log "Waiting for port $Port to be released... ($($i+1)s)"
        }
        Write-Log "DRT System stopped. Starting again..."
    } else {
        Write-Log "DRT System was not running. Starting..."
    }
    # Fall through to the Start section below
}

# --- Start ---
# Check if already running
$existing = Get-RunningProcess
if ($existing) {
    Write-Host "DRT System is already running (PID: $($existing.Id))." -ForegroundColor Yellow
    Write-Host "Use '.\start_drt.ps1 -Stop' to stop it first."
    exit 1
}

# Find Python
$python = Find-Python
if (-not $python) {
    Write-Host "ERROR: Python not found. Please install Python 3.9+ or create a venv." -ForegroundColor Red
    exit 1
}
Write-Log "Python: $python"

# Check .env
if (-not (Test-Path $EnvFile)) {
    Write-Host "WARNING: .env file not found. Using default configuration." -ForegroundColor Yellow
    Write-Log ".env file not found, using defaults." "WARN"
}

# Check dependencies against requirements.txt
$reqFile = Join-Path $ScriptDir "requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Host "ERROR: requirements.txt not found." -ForegroundColor Red
    exit 1
}

Write-Log "Checking dependencies from requirements.txt..."
$missingPkgs = @()
Get-Content $reqFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        # Extract package name (before ==, >=, <=, ~=, !=, etc.)
        $pkgName = ($line -split '[><=!~]')[0].Trim()
        if ($pkgName) {
            $check = & $python -m pip show $pkgName 2>$null
            if (-not $check) {
                $missingPkgs += $line
            }
        }
    }
}

if ($missingPkgs.Count -gt 0) {
    Write-Host ""
    Write-Host "The following dependencies are missing:" -ForegroundColor Yellow
    foreach ($pkg in $missingPkgs) {
        Write-Host "  - $pkg" -ForegroundColor Yellow
    }
    Write-Host ""
    $answer = Read-Host "Install missing dependencies now? (Y/N)"
    if ($answer -match '^[Yy]') {
        Write-Log "Installing dependencies from requirements.txt..."
        & $python -m pip install -r $reqFile 2>&1 | Out-File -Append $LogFile -Encoding UTF8
        # Verify installation succeeded
        $stillMissing = @()
        foreach ($pkg in $missingPkgs) {
            $pkgName = ($pkg -split '[><=!~]')[0].Trim()
            $check = & $python -m pip show $pkgName 2>$null
            if (-not $check) { $stillMissing += $pkg }
        }
        if ($stillMissing.Count -gt 0) {
            Write-Host "ERROR: Failed to install: $($stillMissing -join ', ')" -ForegroundColor Red
            Write-Log "Dependency installation incomplete: $($stillMissing -join ', ')" "ERROR"
            exit 1
        }
        Write-Log "All dependencies installed successfully."
    } else {
        Write-Host "Startup cancelled. Dependencies are required to run DRT System." -ForegroundColor Red
        Write-Log "User declined dependency installation. Startup aborted." "WARN"
        exit 1
    }
} else {
    Write-Log "All dependencies are installed."
}

# Check port availability (ignore TIME_WAIT/CLOSE_WAIT which show PID 0)
$portInUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq 'Listen' }
if ($portInUse) {
    $usedBy = $portInUse | Select-Object -First 1
    Write-Host "ERROR: Port $Port is already in use (PID: $($usedBy.OwningProcess))." -ForegroundColor Red
    Write-Host "  Use '-Port <number>' to specify a different port, or stop the other process."
    exit 1
}

# Start the server in background
Write-Log "Starting DRT System on port $Port..."
Write-Log "Log file: $LogFile"
Write-Log "Error log: $ErrorLogFile"

$envVars = @{ "PORT" = "$Port"; "FLASK_DEBUG" = "0" }
if (Test-Path $EnvFile) {
    Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $k, $v = $line -split "=", 2
            $envVars[$k.Trim()] = $v.Trim()
        }
    }
}
foreach ($kv in $envVars.GetEnumerator()) {
    [System.Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, "Process")
}

$startInfo = @{
    FilePath     = $python
    ArgumentList = "`"$AppFile`""
    WorkingDirectory = $ScriptDir
    RedirectStandardOutput = $LogFile
    RedirectStandardError  = $ErrorLogFile
    WindowStyle  = "Hidden"
    PassThru     = $true
}

$proc = Start-Process @startInfo
$proc.Id | Set-Content $PidFile -Encoding UTF8

# Wait a moment and verify
Start-Sleep -Seconds 3
$running = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if ($running) {
    Write-Log "DRT System started successfully (PID: $($proc.Id))."
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  DRT System is running!" -ForegroundColor Green
    Write-Host "  URL:    http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "  PID:    $($proc.Id)" -ForegroundColor Cyan
    Write-Host "  Log:    $LogFile" -ForegroundColor Gray
    Write-Host "  Errors: $ErrorLogFile" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor White
    Write-Host "  .\start_drt.ps1 -Stop     Stop the server"
    Write-Host "  .\start_drt.ps1 -Restart   Restart the server"
    Write-Host "  .\start_drt.ps1 -Status   Check status"
    Write-Host "  Get-Content $ErrorLogFile -Tail 20   View recent errors"
} else {
    Write-Log "Failed to start DRT System!" "ERROR"
    Write-Host "ERROR: Server failed to start. Check logs:" -ForegroundColor Red
    if (Test-Path $ErrorLogFile) {
        Get-Content $ErrorLogFile -Tail 20
    }
    exit 1
}
