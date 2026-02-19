param(
    [int]$MaxFileLines = 1000,
    [int]$MaxFuncLines = 200,
    [int]$MaxFilesPerDir = 10
)

$ErrorActionPreference = "Stop"

$skillRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$qualityGate = Join-Path $skillRoot "scripts\quality_gate.py"
$selfTest = Join-Path $skillRoot "scripts\test_quality_gate.py"

Write-Host "==> protocol-crawler quality gate"
python $qualityGate `
    --root $skillRoot `
    --max-file-lines $MaxFileLines `
    --max-func-lines $MaxFuncLines `
    --max-files-per-dir $MaxFilesPerDir
if ($LASTEXITCODE -ne 0) {
    throw "quality gate failed"
}

Write-Host "==> protocol-crawler gate self-test"
python $selfTest
if ($LASTEXITCODE -ne 0) {
    throw "quality gate self-test failed"
}

Write-Host "CI gate passed."
