# Installs Themis on Windows. Safe to run again: it is also how you repair an install.
#
# Open PowerShell (Start menu, type "PowerShell"; not Command Prompt, not "as administrator") and run:
#
#   irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex
#
# From Command Prompt (cmd) the same thing is:
#
#   powershell -NoProfile -Command "irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex"
#
# With options (they go to `themis install`: -Port 8080, -Yes, -NoService, -Channel beta, -ThemisHome D:\Themis ...):
#
#   & ([scriptblock]::Create((irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1))) -Port 8080
#
# All this script does is make sure `uv` is there (it fetches the right Python by itself), download the control file of the
# newest release, and run it. The control file (scripts/themisctl.py, plain Python, easy to read) does the installing.
# Themis needs Docker Desktop with Linux containers: the installer checks it, and offers to install it with winget.
#
# This script is run inside YOUR PowerShell window (that is what `| iex` does), so it is careful not to change it: it never
# calls `exit` (which would close the window), keeps its settings inside its own function, runs other installers in a
# separate process, and shows a problem as a message instead of closing. The options can also be given as environment
# variables (THEMIS_PORT, THEMIS_BUNDLE, THEMIS_YES, THEMIS_NO_SERVICE, THEMIS_SKIP_IMAGE), which `| iex` allows.
param(
    [int]$Port = 0,
    [string]$HostName = "127.0.0.1",
    [string]$Channel = "",
    [string]$Version = "",
    [string]$Bundle = "",  # install from this bundle file instead of downloading (offline, testing)
    [string]$ThemisHome = "",  # not $Home: that is a read-only variable in PowerShell
    [switch]$Https,
    [switch]$NoService,
    [switch]$SkipImage,
    [switch]$Yes
)

function Install-Themis {
    param($Port, $HostName, $Channel, $Version, $Bundle, $ThemisHome, $Https, $NoService, $SkipImage, $Yes)

    $ErrorActionPreference = "Stop"  # only inside this function: the person's own window keeps its settings
    $Base = if ($env:THEMIS_INSTALL_BASE) { $env:THEMIS_INSTALL_BASE } else { "https://github.com/RT-codes/ThemisForge/releases/latest/download" }
    if (-not $Port) { $Port = if ($env:THEMIS_PORT) { [int]$env:THEMIS_PORT } else { 8000 } }
    if (-not $Bundle) { $Bundle = $env:THEMIS_BUNDLE }
    if ($env:THEMIS_YES) { $Yes = $true }
    if ($env:THEMIS_NO_SERVICE) { $NoService = $true }
    if ($env:THEMIS_SKIP_IMAGE) { $SkipImage = $true }

    $tmp = $null
    $oldUtf8 = $env:PYTHONUTF8
    try {
        if ($env:OS -ne "Windows_NT") { throw "This installer is for Windows. On Linux use install.sh." }

        # Windows PowerShell 5.1 may not use TLS 1.2 by default, which GitHub and astral.sh require
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072 } catch { }

        # uv, the Python tool Themis uses: installed for this user only, no administrator rights
        $localBin = Join-Path $env:USERPROFILE ".local\bin"
        $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            foreach ($dir in @($localBin, $cargoBin)) {
                if (Test-Path (Join-Path $dir "uv.exe")) { $env:Path = "$dir;$env:Path" }
            }
        }
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Write-Host "==> Installing uv (the Python tool Themis uses) from https://astral.sh/uv"
            # in a process of its own: an installer that calls `exit` must not close this window
            & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
            foreach ($dir in @($localBin, $cargoBin)) {
                if (Test-Path (Join-Path $dir "uv.exe")) { $env:Path = "$dir;$env:Path" }
            }
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                throw "uv could not be installed. Install it from https://docs.astral.sh/uv/ and run this again."
            }
        }

        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("themis-install-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        Write-Host "==> Downloading the installer"
        $ctl = Join-Path $tmp "themisctl.py"
        Invoke-WebRequest -UseBasicParsing -Uri "$Base/themisctl.py" -OutFile $ctl

        $ctlArgs = @("install", "--port", $Port, "--host", $HostName)
        if ($Channel) { $ctlArgs += @("--channel", $Channel) }
        if ($Version) { $ctlArgs += @("--version", $Version) }
        if ($Bundle) { $ctlArgs += @("--bundle", $Bundle) }
        if ($ThemisHome) { $ctlArgs += @("--home", $ThemisHome) }
        if ($Https) { $ctlArgs += "--https" }
        if ($NoService) { $ctlArgs += "--no-service" }
        if ($SkipImage) { $ctlArgs += "--skip-image" }
        if ($Yes) { $ctlArgs += "--yes" }

        $env:PYTHONUTF8 = "1"
        & uv run --no-project --python 3.13 python $ctl @ctlArgs
        if ($LASTEXITCODE -ne 0) { throw "The installer stopped (exit code $LASTEXITCODE). The messages above say why." }
    } catch {
        # a message, never a closed window: nothing here may call `exit`
        Write-Host ""
        Write-Host "Themis could not be installed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Run this again once that is fixed. To keep the window open and read everything, start PowerShell with:  powershell -NoExit" -ForegroundColor Yellow
        $global:LASTEXITCODE = 1
    } finally {
        $env:PYTHONUTF8 = $oldUtf8
        if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
    }
}

Install-Themis -Port $Port -HostName $HostName -Channel $Channel -Version $Version -Bundle $Bundle -ThemisHome $ThemisHome -Https $Https -NoService $NoService -SkipImage $SkipImage -Yes $Yes
