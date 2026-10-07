# Installs Themis on Windows. Safe to run again: it is also how you repair an install.
#
#   irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1 | iex
#
# With options (they go to `themis install`: -Port 8080, -Yes, -NoService, -Channel beta, -ThemisHome D:\Themis ...):
#
#   & ([scriptblock]::Create((irm https://github.com/RT-codes/ThemisForge/releases/latest/download/install.ps1))) -Port 8080
#
# Run it in a normal PowerShell window (not "as administrator"). All this script does is make sure `uv` is there (it fetches
# the right Python by itself), download the control file of the newest release, and run it. The control file
# (scripts/themisctl.py, plain Python, easy to read) does the installing. Themis needs Docker Desktop with Linux containers:
# the installer checks it, and offers to install it with winget if it is missing.
param(
    [int]$Port = 8000,
    [string]$HostName = "127.0.0.1",
    [string]$Channel = "",
    [string]$Version = "",
    [string]$ThemisHome = "",  # not $Home: that is a read-only variable in PowerShell
    [switch]$Https,
    [switch]$NoService,
    [switch]$SkipImage,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$Base = if ($env:THEMIS_INSTALL_BASE) { $env:THEMIS_INSTALL_BASE } else { "https://github.com/RT-codes/ThemisForge/releases/latest/download" }

function Install-Themis {
    if ($env:OS -ne "Windows_NT") { throw "This installer is for Windows. On Linux use install.sh." }

    # uv, the Python tool Themis uses: installed for this user only, no administrator rights
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        $localBin = Join-Path $env:USERPROFILE ".local\bin"
        if (Test-Path (Join-Path $localBin "uv.exe")) {
            $env:Path = "$localBin;$env:Path"
        } else {
            Write-Host "==> Installing uv (the Python tool Themis uses) from https://astral.sh/uv"
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
            $env:Path = "$localBin;$env:Path"
        }
    }

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("themis-install-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        Write-Host "==> Downloading the installer"
        $ctl = Join-Path $tmp "themisctl.py"
        Invoke-WebRequest -UseBasicParsing -Uri "$Base/themisctl.py" -OutFile $ctl

        $ctlArgs = @("install", "--port", $Port, "--host", $HostName)
        if ($Channel) { $ctlArgs += @("--channel", $Channel) }
        if ($Version) { $ctlArgs += @("--version", $Version) }
        if ($ThemisHome) { $ctlArgs += @("--home", $ThemisHome) }
        if ($Https) { $ctlArgs += "--https" }
        if ($NoService) { $ctlArgs += "--no-service" }
        if ($SkipImage) { $ctlArgs += "--skip-image" }
        if ($Yes) { $ctlArgs += "--yes" }

        $env:PYTHONUTF8 = "1"
        & uv run --no-project --python 3.13 python $ctl @ctlArgs
        if ($LASTEXITCODE -ne 0) { throw "The installer stopped (exit code $LASTEXITCODE)." }
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

Install-Themis
