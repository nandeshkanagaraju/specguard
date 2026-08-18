# Switch the demo fixture between its clean and drifted commits.
#   .\demo.ps1 clean    the code matches the spec
#   .\demo.ps1 drift    a normal week of development happened
param([Parameter(Mandatory = $true)][ValidateSet("clean", "drift", "drifted")][string]$Which)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Tag  = if ($Which -eq "clean") { "clean" } else { "drifted" }
$Repo = "samples\orderflow"

if (-not (Test-Path "$Repo\.git")) {
    Write-Host "The demo fixture has no git history yet. Run: .\scripts\build_fixture.ps1" -ForegroundColor Yellow
    exit 1
}

git -C $Repo checkout --quiet $Tag
$sha = git -C $Repo rev-parse --short HEAD
Write-Host "orderflow is now at tag '$Tag' ($sha)"
git -C $Repo --no-pager log -1 --format="  %s"
