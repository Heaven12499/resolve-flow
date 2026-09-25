[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未检测到 Docker CLI。"
}

& docker compose down
if ($LASTEXITCODE -ne 0) { throw "Docker Compose 停止失败。" }
Write-Host "ResolveFlow 已停止，数据库和模型 volume 均已保留。"
