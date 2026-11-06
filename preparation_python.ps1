# Shared discovery/probing for setup and the launcher; global Python is unchanged.
function Invoke-PreparationCapture {
    param([string]$Executable, [string]$Arguments, [string]$WorkingDirectory)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.EnvironmentVariables['PYTHONUTF8'] = '1'
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $output = $process.StandardOutput.ReadToEndAsync()
        $errors = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        return [pscustomobject]@{ ExitCode=$process.ExitCode; Output=$output.GetAwaiter().GetResult(); ErrorOutput=$errors.GetAwaiter().GetResult() }
    } finally { $process.Dispose() }
}

function Get-PreparationPythonCandidates {
    param([string]$Root)
    $paths = @((Join-Path $Root '.venv\Scripts\python.exe'))
    if ($env:DATA_PREPARATION_PYTHON) { $paths += $env:DATA_PREPARATION_PYTHON }
    if ($env:CONDA_PREFIX) { $paths += Join-Path $env:CONDA_PREFIX 'python.exe' }
    foreach ($parent in @($env:USERPROFILE, $env:ProgramData, $env:LOCALAPPDATA)) {
        if (-not $parent) { continue }
        foreach ($distribution in @('anaconda3','miniconda3','miniforge3','mambaforge')) {
            $distributionRoot = Join-Path $parent $distribution
            $paths += Join-Path $distributionRoot 'python.exe'
            $environments = Join-Path $distributionRoot 'envs'
            if (Test-Path -LiteralPath $environments -PathType Container) {
                foreach ($item in (Get-ChildItem -LiteralPath $environments -Directory -ErrorAction SilentlyContinue)) {
                    $paths += Join-Path $item.FullName 'python.exe'
                }
            }
        }
    }
    if ($env:LOCALAPPDATA) {
        foreach ($version in @('312','313','311','310','314','315')) {
            $paths += Join-Path $env:LOCALAPPDATA ('Programs\Python\Python' + $version + '\python.exe')
        }
        $managedRoot = Join-Path $env:LOCALAPPDATA 'Python'
        if (Test-Path -LiteralPath $managedRoot -PathType Container) {
            foreach ($item in (Get-ChildItem -LiteralPath $managedRoot -Directory -Filter 'pythoncore-*' -ErrorAction SilentlyContinue)) {
                $paths += Join-Path $item.FullName 'python.exe'
            }
        }
    }
    foreach ($registryRoot in @('HKCU:\Software\Python','HKLM:\Software\Python','HKLM:\Software\WOW6432Node\Python')) {
        if (-not (Test-Path -LiteralPath $registryRoot)) { continue }
        foreach ($company in (Get-ChildItem -LiteralPath $registryRoot -ErrorAction SilentlyContinue)) {
            foreach ($tag in (Get-ChildItem -LiteralPath $company.PSPath -ErrorAction SilentlyContinue)) {
                $install = Join-Path $tag.PSPath 'InstallPath'
                if (-not (Test-Path -LiteralPath $install)) { continue }
                $key = Get-Item -LiteralPath $install
                if ($key.GetValue('ExecutablePath')) { $paths += $key.GetValue('ExecutablePath') }
                elseif ($key.GetValue('')) { $paths += Join-Path $key.GetValue('') 'python.exe' }
            }
        }
    }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            # Listing installed runtimes never requests an installation.
            $listed = Invoke-PreparationCapture $launcher.Source '-0p' $Root
            foreach ($match in [regex]::Matches(($listed.Output + $listed.ErrorOutput), '(?im)([A-Z]:\\[^\r\n]*?python(?:[0-9.]+)?\.exe)')) {
                $paths += $match.Groups[1].Value.Trim()
            }
        } catch { }
    }
    foreach ($command in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        if ($command.Source -and $command.Source -notmatch '\\Microsoft\\WindowsApps\\') { $paths += $command.Source }
    }
    return @($paths | Where-Object { $_ } | Select-Object -Unique)
}

function Get-PreparationPythonInfo {
    param([string]$Executable, [string]$Root)
    try {
        if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw 'Executable does not exist' }
        $probe = Invoke-PreparationCapture $Executable ('"' + (Join-Path $Root 'python_environment.py') + '"') $Root
        if ($probe.ExitCode -ne 0) { throw $probe.ErrorOutput }
        return ($probe.Output | ConvertFrom-Json)
    } catch {
        return [pscustomobject]@{ executable=$Executable; compatible=$false; offline_wheels=$false; version_text='unavailable'; bits=0; tkinter_available=$false; tkinter_error=$_.Exception.Message }
    }
}

function Select-PreparationSetupPython {
    param([string]$Root, [string]$PythonExe, [switch]$Offline, [string]$Log)
    if ($PythonExe) { $paths = @($PythonExe) }
    else { $paths = @(Get-PreparationPythonCandidates $Root) }
    $fallback = $null
    $localPython = Join-Path $Root '.venv\Scripts\python.exe'
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $info = Get-PreparationPythonInfo $path $Root
        if ($Log) {
            ('Checked Python: ' + $path + ' | version=' + $info.version_text + ' | bits=' + $info.bits + ' | tkinter=' + $info.tkinter_available + ' | ' + $info.tkinter_error) |
                Add-Content -LiteralPath $Log -Encoding UTF8
        }
        if (-not $info.compatible) { continue }
        if ($Offline -and -not $info.offline_wheels) { continue }
        if ($PythonExe -or $path -eq $localPython -or $info.offline_wheels) { return $info }
        if (-not $fallback) { $fallback = $info }
    }
    if ($fallback -and -not $Offline) { return $fallback }
    if ($Offline) { throw 'Offline setup requires 64-bit Python 3.12 with Tcl/Tk for the bundled wheels. Run setup without -Offline to use another compatible installed Python with internet access.' }
    if ($PythonExe) { throw ('The selected interpreter is unavailable or incompatible: ' + $PythonExe + '. Python 3.10+ (64-bit) with Tcl/Tk is required. See the checked-version details in SETUP_WINDOWS.log.') }
    throw 'No compatible Python found. Install 64-bit Python 3.12 with Tcl/Tk, or supply an existing Python 3.10+ / Anaconda interpreter with SETUP_WINDOWS.bat -PythonExe "C:\path\python.exe". See SETUP_WINDOWS.log for every checked installation.'
}
