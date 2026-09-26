param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Test-SupportedPython($Exe, $PrefixArgs) {
    try {
        & $Exe @PrefixArgs -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,14) and sys.maxsize>2**32 else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.12', '-3.11', '-3.13', '-3.14')) {
            if (Test-SupportedPython 'py' @($version)) {
                return @{Exe='py'; PrefixArgs=@($version)}
            }
        }
    }
    $knownPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if ((Test-Path -LiteralPath $knownPython) -and (Test-SupportedPython $knownPython @())) {
        return @{Exe=$knownPython; PrefixArgs=@()}
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*WindowsApps*' -and (Test-SupportedPython $command.Source @())) {
        return @{Exe=$command.Source; PrefixArgs=@()}
    }
    return $null
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'This installer requires 64-bit Windows.' }
    if (Test-Path -LiteralPath $venvPython) {
        if (-not (Test-SupportedPython $venvPython @())) {
            throw 'The existing .venv is unusable or unsupported. Rename .venv, then run install.bat again. Your data folder is separate and will be kept.'
        }
        $python = @{Exe=$venvPython; PrefixArgs=@()}
    } else { $python = Find-Python }
    if ($CheckOnly) {
        if (-not $python) { throw 'No supported 64-bit Python 3.11-3.14 installation found.' }
        Write-Host ('Python detected: ' + $python.Exe + ' ' + ($python.PrefixArgs -join ' '))
        exit 0
    }
    if (-not $python) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/ (include the Python launcher), then rerun install.bat. Automatic installation requires Windows App Installer / winget.'
        }
        Write-Host 'Installing Python 3.12 for your Windows account using winget...'
        & winget install --id Python.Python.3.12 --exact --source winget --scope user --silent
        if ($LASTEXITCODE -ne 0) { throw 'Python installation did not finish. Install Python 3.12 manually and rerun install.bat.' }
        $python = Find-Python
        if (-not $python) { throw 'Python was installed but could not be found. Close this window and rerun install.bat.' }
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host 'Creating the local Python environment...'
        $exe = $python.Exe
        $prefixArgs = $python.PrefixArgs
        & $exe @prefixArgs -m venv (Join-Path $projectRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check write access and Python installation.' }
    }
    Write-Host 'Installing the app, FFmpeg, and Whisper dependencies...'
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip setup failed. Check your internet connection and rerun install.bat.' }
    & $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-whisper.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Review the error above and rerun install.bat.' }
    & $venvPython -c 'from stt.app import create_app; from stt.media import ffmpeg_executable; from faster_whisper import WhisperModel; assert ffmpeg_executable(), ''FFmpeg unavailable''; print(''App, FFmpeg and Whisper are installed.'')'
    if ($LASTEXITCODE -ne 0) { throw 'Installation verification failed. Review the error above.' }
    Write-Host 'Ready. Run download-models.bat to download all models, or run.bat to start the app.'
    exit 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
