$ErrorActionPreference = "Stop"

$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillName = "codeguard-skill"
$candidateRoots = @(
    "$env:USERPROFILE\.trae\claude\skills",
    "$env:USERPROFILE\.trae-cn\claude\skills",
    "$env:USERPROFILE\.trae\skills",
    "$env:USERPROFILE\.trae-cn\skills"
)

$skillsRoot = $candidateRoots | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $skillsRoot) {
    $skillsRoot = $candidateRoots[0]
}

$skillDir = Join-Path $skillsRoot $skillName
$bundleFiles = @(
    "SKILL.md",
    "README.md",
    "LICENSE",
    "agents\openai.yaml",
    "scripts\codeguard.py",
    "scripts\codeguard-cli.py"
)

Write-Host "Installing CodeGuard into $skillDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $skillDir | Out-Null

foreach ($relativePath in $bundleFiles) {
    $sourcePath = Join-Path $sourceDir $relativePath
    if (-not (Test-Path $sourcePath)) {
        throw "Required file not found: $sourcePath"
    }

    $targetPath = Join-Path $skillDir $relativePath
    $targetParent = Split-Path -Parent $targetPath
    if (-not (Test-Path $targetParent)) {
        New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
    }

    Copy-Item -Path $sourcePath -Destination $targetPath -Force
    Write-Host "  copied $relativePath" -ForegroundColor Yellow
}

$registrySource = Join-Path $sourceDir ".trae\skills\codeguard-skill.json"
$registryTarget = Join-Path $skillsRoot "codeguard-skill.json"
Copy-Item -Path $registrySource -Destination $registryTarget -Force
Write-Host "  copied .trae\skills\codeguard-skill.json" -ForegroundColor Yellow

Write-Host ""
Write-Host "Installation complete." -ForegroundColor Green
Write-Host "Restart Trae to reload the skill registry." -ForegroundColor Green
