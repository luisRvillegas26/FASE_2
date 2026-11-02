param(
    [string]$BaseUrl = 'http://127.0.0.1:8080',
    [string]$OutputPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'evidence\container-http.json')
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$client = New-Object System.Net.Http.HttpClient
$client.Timeout = [TimeSpan]::FromSeconds(10)
$example = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\examples\predict.json') -Raw
$cases = @(
    @{ Method = 'GET'; Path = '/health/live'; Body = $null; Expected = 200 },
    @{ Method = 'GET'; Path = '/health/ready'; Body = $null; Expected = 200 },
    @{ Method = 'GET'; Path = '/v1/model'; Body = $null; Expected = 200 },
    @{ Method = 'GET'; Path = '/openapi.json'; Body = $null; Expected = 200 },
    @{ Method = 'POST'; Path = '/v1/predict'; Body = $example; Expected = 200 },
    @{ Method = 'POST'; Path = '/v1/predict'; Body = '{"instances":[]}'; Expected = 422 }
)
$records = @()
try {
    foreach ($case in $cases) {
        $request = New-Object System.Net.Http.HttpRequestMessage
        $request.Method = New-Object System.Net.Http.HttpMethod($case.Method)
        $request.RequestUri = [Uri]($BaseUrl.TrimEnd('/') + $case.Path)
        if ($null -ne $case.Body) {
            $request.Content = New-Object System.Net.Http.StringContent($case.Body, [Text.Encoding]::UTF8, 'application/json')
        }
        $response = $null
        try {
            $response = $client.SendAsync($request).GetAwaiter().GetResult()
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
            $status = [int]$response.StatusCode
            $passed = $status -eq $case.Expected
            if ($case.Method -eq 'POST' -and $case.Expected -eq 200 -and $passed) {
                $prediction = $body.predictions[0]
                $passed = ($body.predictions.Count -eq 1) -and ($prediction.demanda_semanal.Count -eq 4) -and
                    ($body.synthetic -eq $true) -and ($body.operationally_approved -eq $false) -and
                    ($body.umbral -eq 0.28) -and
                    ($prediction.alerta -eq ($prediction.probabilidad_faltante -ge $body.umbral))
            }
            $records += [pscustomobject]@{ method = $case.Method; path = $case.Path; status = $status;
                expected = $case.Expected; passed = $passed; response = $body }
            Write-Host "$($case.Method) $($case.Path): HTTP $status; passed=$passed"
        } finally {
            if ($null -ne $response) { $response.Dispose() }
            $request.Dispose()
        }
    }
} finally {
    $client.Dispose()
}
$allPassed = @($records | Where-Object { -not $_.passed }).Count -eq 0
$parent = Split-Path $OutputPath -Parent
if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
[pscustomobject]@{ utc = [DateTime]::UtcNow.ToString('o'); base_url = $BaseUrl;
    passed = $allPassed; requests = $records } | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
if (-not $allPassed) { throw "HTTP integration failed. See $OutputPath" }
Write-Host "HTTP smoke: 6/6; evidence=$OutputPath"
