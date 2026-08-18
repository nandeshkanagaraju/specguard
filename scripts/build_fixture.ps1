# Build the demo fixture's git history: two commits, tagged `clean` and `drifted`.
# Run this once after cloning.  PowerShell:  .\scripts\build_fixture.ps1
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Repo = Join-Path $Here "samples\orderflow"
$Src  = Join-Path $Here "samples\_variants"

Remove-Item -Recurse -Force (Join-Path $Repo ".git")        -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $Repo ".specguard")  -ErrorAction SilentlyContinue

Copy-Item (Join-Path $Src "clean\orderflow\*.py") (Join-Path $Repo "orderflow") -Force
git -C $Repo init -q -b main
git -C $Repo config user.email "team@orderflow.example"
git -C $Repo config user.name  "OrderFlow Team"
git -C $Repo add -A
git -C $Repo commit -q -m "OrderFlow: pricing, shipping, inventory and checkout per SPEC.md"
git -C $Repo tag clean

Copy-Item (Join-Path $Src "drifted\orderflow\*.py") (Join-Path $Repo "orderflow") -Force
git -C $Repo add -A
git -C $Repo commit -q -m "Tidy checkout, simplify validation, adjust free-shipping check"
git -C $Repo tag drifted
git -C $Repo checkout -q clean

Write-Host "fixture ready - tags 'clean' and 'drifted', currently on 'clean'"
