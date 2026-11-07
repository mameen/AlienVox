param(
    [string]$VenvName = '.venv'
)

$ErrorActionPreference = 'Stop'

$skillRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([System.IO.Path]::IsPathRooted($VenvName) -or $VenvName.Contains('..')) {
    throw 'VenvName must be a folder name inside the Alien Conversation skill.'
}
$venvRoot = [System.IO.Path]::GetFullPath((Join-Path $skillRoot $VenvName))
$skillPrefix = $skillRoot.TrimEnd('\') + '\'
if (-not $venvRoot.StartsWith($skillPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The virtual environment path must stay inside the alien_conv skill folder.'
}
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$venvConfig = Join-Path $venvRoot 'pyvenv.cfg'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'

if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $venvConfig)) {
    if (Test-Path -LiteralPath $venvRoot) {
        throw "Found an incomplete local environment at '$venvRoot'. Repair it with 'py -3.12 -m venv --clear `"$venvRoot`"', then rerun setup."
    }
    Write-Host "Creating Alien Conversation environment: $venvRoot"
    & py -3.12 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "python -m venv failed with exit code $LASTEXITCODE"
    }
}

Write-Host 'Installing the combined Alien Conversation requirements...'
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed with exit code $LASTEXITCODE"
}

Write-Host ''
Write-Host 'Setup complete. The bridge, manual chat, copied STT/TTS utilities, and Pipecat POC share this environment.'
Write-Host 'Start the interactive console with its embedded API (copy the URL from its title):'
$pythonPath = Join-Path $venvRoot 'Scripts\python.exe'
$clientPath = Join-Path $skillRoot 'scripts\local_test.py'
Write-Host "`"$pythonPath`" `"$clientPath`" --mode api-server --api-host 127.0.0.1 --api-port 8765"
Write-Host 'Start the manual local conversation:'
$localTestPath = Join-Path $skillRoot 'scripts\local_test.py'
Write-Host "`"$pythonPath`" `"$localTestPath`" --model gemma4:12b --tts-engine sapi5 --tts-voice zira"
