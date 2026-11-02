param([string]$Owner = 'luisRvillegas26', [string]$Name = 'opella-demanda-api')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step fallo" } }
gh auth status
Check 'GitHub authentication'
git rev-parse --show-toplevel
Check 'Local repository'
git rev-parse --verify HEAD
Check 'Existing commit'
gh repo create "$Owner/$Name" --private --source . --remote origin --push
Check 'Create and publish repository'
