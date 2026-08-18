# SpecGuard setup for Windows.
#
#   PowerShell:  .\setup.ps1
#
# Creates a virtualenv, installs SpecGuard into it, and builds the demo fixture.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "SpecGuard setup" -ForegroundColor Cyan
Write-Host "==============="

# --- find a usable Python -------------------------------------------------
$Py = $null
foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "python")) {
    $parts = $candidate.Split(" ")
    $exe   = $parts[0]
    $args  = if ($parts.Length -gt 1) { $parts[1..($parts.Length - 1)] } else { @() }
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $ok = & $exe @args -c "import sys; print(1 if sys.version_info >= (3,11) else 0)" 2>$null
        if ($ok -eq "1") { $Py = $candidate; break }
    } catch { }
}

if (-not $Py) {
    Write-Host ""
    Write-Host "  Python 3.11 or newer is required and was not found." -ForegroundColor Red
    Write-Host "  Install it from https://www.python.org/downloads/"
    Write-Host "  Tick 'Add python.exe to PATH' in the installer, then re-run this script."
    exit 1
}

$parts = $Py.Split(" ")
$PyExe  = $parts[0]
$PyArgs = if ($parts.Length -gt 1) { $parts[1..($parts.Length - 1)] } else { @() }
Write-Host "  python: $(& $PyExe @PyArgs --version)"

# --- install --------------------------------------------------------------
Write-Host "  creating .venv..."
& $PyExe @PyArgs -m venv .venv

$VPy = ".\.venv\Scripts\python.exe"
$VSg = ".\.venv\Scripts\specguard.exe"

& $VPy -m pip install --quiet --upgrade pip
Write-Host "  installing SpecGuard..."
& $VPy -m pip install --quiet -e ".[dev]"

if (-not (Test-Path $VSg)) {
    Write-Host "  install failed - specguard.exe was not created" -ForegroundColor Red
    exit 1
}
Write-Host "  installed: ok"

# --- build the demo fixture ------------------------------------------------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host "  building the demo fixture..."
    & ".\scripts\build_fixture.ps1"
} else {
    Write-Host "  git not found - skipping the demo fixture" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. Try this:" -ForegroundColor Green
Write-Host ""
Write-Host "  .\demo.ps1 drift                       # a week of development happened"
Write-Host "  .\.venv\Scripts\python.exe -m pytest samples\orderflow\tests -q"
Write-Host "                                         # 15 passed - tests are still green"
Write-Host "  .\.venv\Scripts\specguard.exe check samples\orderflow"
Write-Host "                                         # ...and 3 rules have drifted anyway"
Write-Host ""
Write-Host "  .\.venv\Scripts\specguard.exe serve samples\orderflow"
Write-Host "                                         # dashboard at http://127.0.0.1:8000"
Write-Host ""
Write-Host "To use it on your own project, see WINDOWS.md."
