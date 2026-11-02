param([int]$Port = 8081)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force evidence | Out-Null
$container = 'opella-demanda-validation'
function Assert-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step fallo (exit $LASTEXITCODE)" }
}
function Invoke-DockerLogged {
    param([string[]]$Arguments, [string]$LogPath, [string]$Step)
    # Windows PowerShell 5.1 wraps native stderr as NativeCommandError.
    # Docker writes normal build progress there; only its exit code signals failure.
    $previousPreference = $ErrorActionPreference
    $exitCode = $null
    try {
        $ErrorActionPreference = 'Continue'
        & docker @Arguments 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $LogPath -ErrorAction Stop
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) { throw "$Step fallo (exit $exitCode). Revisar $LogPath" }
}
Invoke-DockerLogged -Arguments @('version') -LogPath evidence/docker-version.txt -Step 'Docker engine'
Invoke-DockerLogged -Arguments @('compose','config') -LogPath evidence/compose-config.txt -Step 'Compose config'
Invoke-DockerLogged -Arguments @('build','--progress=plain','-t','opella-demanda-api:1.0.0','.') -LogPath evidence/docker-build.txt -Step 'Docker build'
docker run -d --name $container -p "127.0.0.1:${Port}:8080" --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true opella-demanda-api:1.0.0
Assert-Exit 'Docker run'
try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $null = Invoke-RestMethod "http://127.0.0.1:$Port/health/ready" -TimeoutSec 2
            $ready = $true
            break
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $ready) { throw 'Contenedor no disponible en 60 segundos' }
    # Test the published port from the host. No docker cp or container writes.
    & (Join-Path $PSScriptRoot 'smoke.ps1') -BaseUrl "http://127.0.0.1:$Port" -OutputPath (Join-Path (Get-Location).Path 'evidence\container-http.json')
    docker inspect $container | Out-File -Encoding utf8 evidence/container-inspect.json
    docker image inspect opella-demanda-api:1.0.0 | Out-File -Encoding utf8 evidence/image-inspect.json
    Write-Host 'VALIDACION DOCKER COMPLETADA. Evidencia en evidence/.'
} finally {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        docker logs $container 2>&1 | ForEach-Object { $_.ToString() } | Out-File -Encoding utf8 evidence/container.log
        docker rm -f $container | Out-Null
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}
