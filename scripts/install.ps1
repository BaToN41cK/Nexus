<#
.SYNOPSIS
    Install script for Nexus AI Assistant (Windows).
.DESCRIPTION
    Creates a virtual environment, installs dependencies,
    and optionally adds the nexus command to PATH.
#>

param(
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"
Write-Host "=== Nexus Installation (Windows) ===" -ForegroundColor Cyan

# Navigate to project root (parent of scripts/)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray

# ---------------------------------------------------------------------------
# Find a working Python executable
# ---------------------------------------------------------------------------
function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python 3\.\d+") {
                return $cmd
            }
        } catch {
            # continue
        }
    }
    return $null
}

$pyCmd = Find-Python
if (-not $pyCmd) {
    Write-Host "ERROR: Python 3.9+ not found." -ForegroundColor Red
    Write-Host "Install from https://www.python.org/downloads/ or via winget:" -ForegroundColor Yellow
    Write-Host '  winget install Python.Python.3.12' -ForegroundColor White
    exit 1
}

$pyVersion = & $pyCmd --version 2>&1
Write-Host "Found: $pyCmd ($pyVersion)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Create virtual environment
# ---------------------------------------------------------------------------
$venvDir = Join-Path $ProjectRoot "venv"
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $pyCmd -m venv $venvDir
    if (-not (Test-Path $activateScript)) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        Write-Host "Try creating it manually:" -ForegroundColor Yellow
        Write-Host "  $pyCmd -m venv venv" -ForegroundColor White
        exit 1
    }
    Write-Host "Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Activate
# ---------------------------------------------------------------------------
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& $activateScript

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& python -m pip install --upgrade pip 2>&1 | Out-Null

Write-Host "Installing Nexus..." -ForegroundColor Yellow
& pip install -e .

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
$envExample = Join-Path $ProjectRoot "config\.env.example"
$envFile    = Join-Path $ProjectRoot "config\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "Creating config\.env from example..." -ForegroundColor Yellow
    Copy-Item $envExample $envFile
    Write-Host "NOTE: Edit config\.env and add your GROQ_API_KEY." -ForegroundColor Yellow
} else {
    Write-Host "config\.env already exists." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# PATH (optional)
# ---------------------------------------------------------------------------
if (-not $NoPath) {
    $userPath  = [Environment]::GetEnvironmentVariable("Path", "User")
    $nexusPath = Join-Path $venvDir "Scripts"
    if ($userPath -notlike "*$nexusPath*") {
        Write-Host "Adding venv\Scripts to user PATH..." -ForegroundColor Yellow
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$nexusPath", "User")
        Write-Host "PATH updated. Restart your terminal to apply." -ForegroundColor Green
    } else {
        Write-Host "PATH already contains venv\Scripts." -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=== Installation complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Edit config\.env and add your GROQ_API_KEY" -ForegroundColor White
Write-Host "  2. Activate the venv:  .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host '  3. Test:  nexus run "Привет!"' -ForegroundColor White