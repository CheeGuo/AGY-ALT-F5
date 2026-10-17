<#
.SYNOPSIS
    Synchronizes Google Agent Development Kit (ADK) documentation into references/
.DESCRIPTION
    Follows the canonical pointer at https://github.com/google/adk-python/blob/main/llms-full.txt
    and downloads the latest llms-full.txt and llms.txt.
    Uses purely relative paths from this script's directory.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [int]$TimeoutSec = 30
)

$ErrorActionPreference = "Stop"

$SkillRoot = Resolve-Path "$PSScriptRoot/.."
$RefsDir = Join-Path $SkillRoot "references"
if (-not (Test-Path $RefsDir)) {
    New-Item -ItemType Directory -Path $RefsDir -Force | Out-Null
}

$PointerUrl = "https://raw.githubusercontent.com/google/adk-python/main/llms-full.txt"
$DefaultFull = "https://adk.dev/llms-full.txt"
$DefaultIndex = "https://adk.dev/llms.txt"

Write-Host "=== Google ADK Documentation Synchronizer (PowerShell) ==="
Write-Host "Skill root: $SkillRoot"
Write-Host "Target dir: $RefsDir"

$FullUrl = $DefaultFull
$IndexUrl = $DefaultIndex

try {
    Write-Host "[*] Checking pointer from GitHub ($PointerUrl)..."
    $pointerContent = (Invoke-RestMethod -Uri $PointerUrl -TimeoutSec $TimeoutSec -UserAgent "ADK-Skill-Updater/1.0")
    if ($pointerContent -match '\[.*?llms-full.*?\]\((https?://[^\)]+)\)') {
        $FullUrl = $matches[1]
    }
    if ($pointerContent -match '\[.*?llms\.txt.*?\]\((https?://[^\)]+)\)') {
        $IndexUrl = $matches[1]
    }
    Write-Host "[+] Resolved URLs:"
    Write-Host "    - Full:  $FullUrl"
    Write-Host "    - Index: $IndexUrl"
} catch {
    Write-Warning "Could not fetch GitHub pointer: $_. Using fallback defaults."
}

$TargetFull = Join-Path $RefsDir "llms-full.txt"
$TargetIndex = Join-Path $RefsDir "llms.txt"

try {
    Write-Host "[*] Downloading llms-full.txt..."
    Invoke-WebRequest -Uri $FullUrl -OutFile $TargetFull -TimeoutSec $TimeoutSec -UserAgent "ADK-Skill-Updater/1.0"
    $sizeFull = (Get-Item $TargetFull).Length
    Write-Host "[+] Updated llms-full.txt ($sizeFull bytes)"

    Write-Host "[*] Downloading llms.txt..."
    Invoke-WebRequest -Uri $IndexUrl -OutFile $TargetIndex -TimeoutSec $TimeoutSec -UserAgent "ADK-Skill-Updater/1.0"
    $sizeIndex = (Get-Item $TargetIndex).Length
    Write-Host "[+] Updated llms.txt ($sizeIndex bytes)"

    $meta = @{
        last_updated_utc = (Get-Date).ToUniversalTime().ToString("o")
        pointer_source = $PointerUrl
        llms_full_url = $FullUrl
        llms_index_url = $IndexUrl
        full_file_size_bytes = $sizeFull
        index_file_size_bytes = $sizeIndex
    }
    $metaJson = $meta | ConvertTo-Json -Depth 3
    Set-Content -Path (Join-Path $RefsDir ".last_updated.json") -Value $metaJson -Encoding UTF8
    Write-Host "[+] Updated references/.last_updated.json"
    Write-Host "=== Synchronization Complete ==="
} catch {
    Write-Error "Failed to synchronize ADK documentation: $_"
    exit 1
}
