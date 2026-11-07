$ErrorActionPreference = 'Stop'

$skillRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$venvRoot = [System.IO.Path]::GetFullPath((Join-Path $skillRoot '.venv'))
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$venvConfig = Join-Path $venvRoot 'pyvenv.cfg'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'

if (-not $venvRoot.StartsWith($skillRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The virtual environment path must stay inside the alien_conv skill folder.'
}

if (-not (Test-Path -LiteralPath $venvPython) -or -not (Test-Path -LiteralPath $venvConfig)) {
    if (Test-Path -LiteralPath $venvRoot) {
        throw "Found an incomplete local environment at '$venvRoot'. Repair it with 'py -3.13 -m venv --upgrade `"$venvRoot`"', then rerun setup."
    }
    Write-Host "Creating Alien Conversation environment: $venvRoot"
    & python -m venv $venvRoot
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
Write-Host 'Start the host-driven bridge:'
Write-Host '.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\alien_conv.py --tts-voice zira'
Write-Host 'Start the manual local conversation:'
Write-Host '.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\local_test.py --model gemma4:12b --tts-engine sapi5 --tts-voice zira'
