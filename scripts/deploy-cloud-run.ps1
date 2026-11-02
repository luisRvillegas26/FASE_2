param(
    [Parameter(Mandatory=$true)][string]$ProjectId,
    [string]$Region = 'us-central1',
    [string]$Repository = 'opella',
    [string]$Service = 'opella-demanda-demo',
    [Parameter(Mandatory=$true)][string]$Tag
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step fallo" } }
$image = "${Region}-docker.pkg.dev/${ProjectId}/${Repository}/${Service}:${Tag}"
# Prerequisites: authenticated gcloud, billing, enabled APIs and existing Docker repository.
gcloud auth configure-docker "${Region}-docker.pkg.dev" --quiet
Check 'Docker authentication'
docker build --platform linux/amd64 -t $image .
Check 'Build'
docker push $image
Check 'Push'
gcloud run deploy $Service --project $ProjectId --region $Region --image $image --port 8080 --memory 512Mi --cpu 1 --min-instances 0 --max-instances 2 --concurrency 8 --timeout 60 --no-allow-unauthenticated
Check 'Cloud Run deploy'
