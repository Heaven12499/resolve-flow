[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$SkipSmokeTest,
    [switch]$RotateSecrets
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$examplePath = Join-Path $repoRoot ".env.example"

function New-HexSecret([int]$byteCount) {
    return [Convert]::ToHexString(
        [Security.Cryptography.RandomNumberGenerator]::GetBytes($byteCount)
    ).ToLowerInvariant()
}

function Set-EnvValue([string]$content, [string]$name, [string]$value) {
    $pattern = "(?m)^$([regex]::Escape($name))=.*$"
    if ([regex]::IsMatch($content, $pattern)) {
        return [regex]::Replace($content, $pattern, "$name=$value")
    }
    return $content.TrimEnd() + [Environment]::NewLine + "$name=$value" + [Environment]::NewLine
}

function Set-RandomSecrets([string]$content) {
    $script:adminPassword = "Adm-$(New-HexSecret 10)"
    $content = Set-EnvValue $content "BUSINESS_JWT_SECRET" (New-HexSecret 32)
    $content = Set-EnvValue $content "INTERNAL_API_TOKEN" (New-HexSecret 32)
    $content = Set-EnvValue $content "AUTH_SECRET" (New-HexSecret 32)
    $content = Set-EnvValue $content "AUTH_ADMIN_PASSWORD" $script:adminPassword
    $content = Set-EnvValue $content "AUTH_SUPERVISOR_PASSWORD" "Sup-$(New-HexSecret 10)"
    $content = Set-EnvValue $content "AUTH_AGENT_PASSWORD" "Agt-$(New-HexSecret 10)"
    return $content
}

function Read-EnvValue([string]$name) {
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^$([regex]::Escape($name))=" } | Select-Object -Last 1
    if (-not $line) { return $null }
    return $line.Substring($line.IndexOf("=") + 1)
}

function Assert-Secret([string]$name, [int]$minimumLength) {
    $value = Read-EnvValue $name
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith("replace-with-") -or $value.Length -lt $minimumLength) {
        throw ".env 中的 $name 必须替换为至少 $minimumLength 位的随机值。可备份并删除 .env 后重新运行本脚本自动生成。"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未检测到 Docker CLI，请先安装并启动 Docker Desktop。"
}

Set-Location $repoRoot
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Compose 不可用。" }

if (-not (Test-Path -LiteralPath $envPath)) {
    $content = [IO.File]::ReadAllText($examplePath)
    $content = Set-RandomSecrets $content
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Host "已生成本地 .env 和随机密钥。"
    Write-Host "管理员账号：admin / $adminPassword"
} elseif ($RotateSecrets) {
    $content = Set-RandomSecrets ([IO.File]::ReadAllText($envPath))
    [IO.File]::WriteAllText($envPath, $content, [Text.UTF8Encoding]::new($false))
    Write-Host "已保留现有配置并轮换本地密钥。"
    Write-Host "管理员账号：admin / $adminPassword"
} else {
    Write-Host "检测到已有 .env，将保留现有配置。"
}

Assert-Secret "BUSINESS_JWT_SECRET" 32
Assert-Secret "INTERNAL_API_TOKEN" 32
Assert-Secret "AUTH_ADMIN_PASSWORD" 12
Assert-Secret "AUTH_SUPERVISOR_PASSWORD" 12
Assert-Secret "AUTH_AGENT_PASSWORD" 12

$composeArgs = @("compose", "up", "-d", "--remove-orphans")
if (-not $SkipBuild) { $composeArgs += "--build" }
& docker @composeArgs
if ($LASTEXITCODE -ne 0) { throw "Docker Compose 启动失败。" }

if (-not $SkipSmokeTest) {
    & (Join-Path $PSScriptRoot "Test-LocalStack.ps1")
}

Write-Host "ResolveFlow 已启动："
Write-Host "  Web UI      http://localhost:5173"
Write-Host "  Business API http://localhost:8080"
Write-Host "  AI API       http://localhost:8000"
Write-Host "  Prometheus   http://localhost:9090"
