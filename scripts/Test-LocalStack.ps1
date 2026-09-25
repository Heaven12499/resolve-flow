[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"

function Read-EnvValue([string]$name) {
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^$([regex]::Escape($name))=" } | Select-Object -Last 1
    if (-not $line) { return $null }
    return $line.Substring($line.IndexOf("=") + 1)
}

function Wait-Endpoint([string]$uri, [datetime]$deadline) {
    do {
        try {
            $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ([datetime]::UtcNow -lt $deadline)
    throw "等待服务超时：$uri"
}

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "缺少 .env，请先运行 scripts/Start-Local.ps1。"
}

$deadline = [datetime]::UtcNow.AddSeconds($TimeoutSeconds)
Wait-Endpoint "http://localhost:8080/actuator/health/readiness" $deadline
Wait-Endpoint "http://localhost:8000/health" $deadline
Wait-Endpoint "http://localhost:9090/-/ready" $deadline

$adminPassword = Read-EnvValue "AUTH_ADMIN_PASSWORD"
if ([string]::IsNullOrWhiteSpace($adminPassword)) {
    throw ".env 中缺少 AUTH_ADMIN_PASSWORD。"
}

$loginBody = @{ username = "admin"; password = $adminPassword } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/auth/login" -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)"; "X-Request-Id" = "local-smoke-test" }
$tickets = Invoke-RestMethod -Method Get -Uri "http://localhost:8080/api/tickets" -Headers $headers
$metrics = Invoke-WebRequest -Uri "http://localhost:8000/metrics" -UseBasicParsing

if ($metrics.Content -notmatch "resolveflow_ai_http_requests_total") {
    throw "AI metrics 端点缺少预期指标。"
}

$ticketCount = @($tickets).Count
if ($ticketCount -lt 1) {
    throw "业务 API 未返回演示工单。"
}
Write-Host "本地验收通过：Java、Python、Prometheus 均健康，可读取工单 $ticketCount 条。"
