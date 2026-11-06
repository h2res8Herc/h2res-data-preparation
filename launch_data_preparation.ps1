param([switch]$Check, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
$preparationRoot = $PSScriptRoot
$preparationLog = Join-Path $preparationRoot 'DATA_PREPARATION_STARTUP.log'
$preparationEntry = Join-Path $preparationRoot 'data_preparation_gui.py'
. (Join-Path $preparationRoot 'preparation_python.ps1')

try {
    Set-Location -LiteralPath $preparationRoot
    @('Energy Data Sourcing and Preparation', ('Package: ' + $preparationRoot),
      ('Started: ' + (Get-Date -Format o))) | Set-Content -LiteralPath $preparationLog -Encoding UTF8
    $projectPython = Join-Path $preparationRoot '.venv\Scripts\python.exe'
    $selected = $null
    $verified = $null
    if (Test-Path -LiteralPath $projectPython -PathType Leaf) {
        $info = Get-PreparationPythonInfo $projectPython $preparationRoot
        if (-not $info.compatible) { throw 'The local Python environment is unusable. Run SETUP_WINDOWS.bat to repair it. The launcher will not switch to another interpreter.' }
        $selected = $projectPython
    } elseif (Test-Path -LiteralPath (Join-Path $preparationRoot 'PACKAGE_MANIFEST.json') -PathType Leaf) {
        throw 'Setup has not completed in this extracted folder. Run SETUP_WINDOWS.bat first. It supports existing compatible Anaconda/Python installations; Python 3.12 uses bundled offline wheels. See SETUP_WINDOWS.log if setup fails.'
    } else {
        # Development checkouts may use an already prepared external interpreter.
        foreach ($candidate in (Get-PreparationPythonCandidates $preparationRoot)) {
            if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
            $info = Get-PreparationPythonInfo $candidate $preparationRoot
            if ($info.compatible) {
                $candidateCheck = Invoke-PreparationCapture $candidate ('"' + $preparationEntry + '" --check') $preparationRoot
                if ($candidateCheck.ExitCode -eq 0) { $selected = $candidate; $verified = $candidateCheck; break }
                ('Skipped incomplete development interpreter: ' + $candidate + [Environment]::NewLine + $candidateCheck.ErrorOutput) |
                    Add-Content -LiteralPath $preparationLog -Encoding UTF8
            }
        }
    }
    if (-not $selected) { throw 'No compatible Python 3.10+ (64-bit) with Tcl/Tk found. Run SETUP_WINDOWS.bat or specify its -PythonExe option.' }
    ('Python: ' + $selected) | Add-Content -LiteralPath $preparationLog -Encoding UTF8
    $arguments = '"' + $preparationEntry + '"'
    if (-not $verified) { $verified = Invoke-PreparationCapture $selected ($arguments + ' --check') $preparationRoot }
    if ($verified.Output) { Add-Content -LiteralPath $preparationLog -Value $verified.Output -Encoding UTF8 }
    if ($verified.ErrorOutput) { Add-Content -LiteralPath $preparationLog -Value $verified.ErrorOutput -Encoding UTF8 }
    if ($verified.ExitCode -ne 0) {
        if ($verified.ErrorOutput) { Write-Host $verified.ErrorOutput.TrimEnd() }
        throw 'Preparation dependencies are incomplete in the selected environment. Run SETUP_WINDOWS.bat to finish installation. The launcher will not fall back to Anaconda or another Python.'
    }
    if ($Check) { Write-Host $verified.Output.TrimEnd(); exit 0 }
    if ($SmokeTest) { $arguments += ' --smoke-test' }
    Write-Host 'Starting Energy Data Sourcing and Preparation'
    $run = Invoke-PreparationCapture $selected $arguments $preparationRoot
    ('Preparation process exit code: ' + $run.ExitCode) | Add-Content -LiteralPath $preparationLog -Encoding UTF8
    if ($run.Output) { Add-Content -LiteralPath $preparationLog -Value $run.Output -Encoding UTF8; Write-Host $run.Output.TrimEnd() }
    if ($run.ErrorOutput) { Add-Content -LiteralPath $preparationLog -Value $run.ErrorOutput -Encoding UTF8; Write-Host $run.ErrorOutput.TrimEnd() }
    if ($run.ExitCode -ne 0) { throw ('Data preparation exited with code ' + $run.ExitCode) }
    exit 0
} catch {
    $message = $_.Exception.Message
    Add-Content -LiteralPath $preparationLog -Value $message -Encoding UTF8
    Write-Host $message
    Write-Host ('Startup log: ' + $preparationLog)
    exit 1
}
