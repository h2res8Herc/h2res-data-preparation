param([switch]$WithCds, [switch]$CheckOnly, [switch]$Offline, [string]$PythonExe)
$ErrorActionPreference = 'Stop'
$setupRoot = $PSScriptRoot
$setupLog = Join-Path $setupRoot 'SETUP_WINDOWS.log'
Set-Location -LiteralPath $setupRoot
. (Join-Path $setupRoot 'preparation_python.ps1')

function Invoke-SetupPython {
    param([string]$Executable, [string[]]$PythonArguments)
    $setupErrorMode = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @PythonArguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            Write-Host $line
            Add-Content -LiteralPath $setupLog -Value $line -Encoding UTF8
        }
        $setupCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $setupErrorMode }
    if ($setupCode -ne 0) { throw ('Python command failed with exit code ' + $setupCode) }
}

try {
    ('Setup started: ' + (Get-Date -Format o)) | Set-Content -LiteralPath $setupLog -Encoding UTF8
    $selected = Select-PreparationSetupPython -Root $setupRoot -PythonExe $PythonExe -Offline:$Offline -Log $setupLog
    $python = $selected.executable
    Write-Host ('Selected Python ' + $selected.version_text + ' (' + $selected.bits + '-bit): ' + $python)
    if ($selected.offline_wheels) { Write-Host 'Dependency mode: tested Python 3.12 lock and bundled wheels.' }
    else { Write-Host 'Dependency mode: online installation for this Python version. Internet access is required.' }
    if ($CheckOnly) { exit 0 }
    $environment = Join-Path $setupRoot '.venv'
    $environmentPython = Join-Path $environment 'Scripts\python.exe'
    if (Test-Path -LiteralPath $environment) {
        $local = Get-PreparationPythonInfo $environmentPython $setupRoot
        if (-not $local.compatible -or ($local.version[0] -ne $selected.version[0]) -or ($local.version[1] -ne $selected.version[1])) {
            $expected = [System.IO.Path]::GetFullPath((Join-Path $setupRoot '.venv'))
            $resolved = (Resolve-Path -LiteralPath $environment).Path
            $item = Get-Item -LiteralPath $environment -Force
            if ($resolved -ne $expected -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'The local .venv path is not a regular directory inside the package.' }
            $backup = Join-Path $setupRoot ('.venv_previous_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
            if ([System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($backup)) -ne $setupRoot) { throw 'Invalid environment backup target' }
            Move-Item -LiteralPath $resolved -Destination $backup
            Write-Host ('Preserved the unusable environment at ' + $backup)
        }
    }
    if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
        Invoke-SetupPython -Executable $python -PythonArguments @('-m','venv',$environment)
    }
    $venv = Get-PreparationPythonInfo $environmentPython $setupRoot
    if (-not $venv.compatible) { throw 'The project environment cannot import Tcl/Tk. If using Anaconda, run setup from Anaconda Prompt, or install standard 64-bit Python 3.12 with Tcl/Tk.' }
    $installArguments = @('-m','pip','install','--disable-pip-version-check','--only-binary=:all:')
    if ($venv.offline_wheels) {
        $wheels = Join-Path $setupRoot 'wheels'
        if (Test-Path -LiteralPath $wheels -PathType Container) { $installArguments += @('--no-index','--find-links',$wheels) }
        elseif ($Offline) { throw 'The bundled wheels folder is missing; copy it from the transfer archive.' }
        $requirements = Join-Path $setupRoot 'requirements-lock-win-py312.txt'
    } else {
        if ($Offline) { throw 'This Python version requires online dependencies; offline wheels target Python 3.12.' }
        $requirements = Join-Path $setupRoot 'requirements.txt'
    }
    $installArguments += @('-r',$requirements)
    Invoke-SetupPython -Executable $environmentPython -PythonArguments $installArguments
    if ($WithCds) {
        if ($Offline) { throw 'Optional CDS dependencies require online setup; omit -Offline when using -WithCds.' }
        Invoke-SetupPython -Executable $environmentPython -PythonArguments @('-m','pip','install','--disable-pip-version-check','-r',(Join-Path $setupRoot 'requirements-cds.txt'))
    }
    Invoke-SetupPython -Executable $environmentPython -PythonArguments @('preparation_dependencies.py')
    Invoke-SetupPython -Executable $environmentPython -PythonArguments @('data_preparation_gui.py','--check')
    Write-Host ('Setup complete. The launcher will use ' + $environmentPython)
    exit 0
} catch {
    $message = $_.Exception.Message
    Add-Content -LiteralPath $setupLog -Value $message -Encoding UTF8
    Write-Host $message
    Write-Host ('Setup log: ' + $setupLog)
    exit 1
}
