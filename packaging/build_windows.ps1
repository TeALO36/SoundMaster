[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Version = $env:APP_VERSION,
    [Parameter(Mandatory = $false)]
    [string]$PythonExecutable = $env:SOUNDMASTER_PYTHON
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$GeneratedVersion = Join-Path $Root "src\soundmaster\_build_version.py"

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "0.4.0"
}
$Version = $Version.Trim()
if ($Version.StartsWith("v")) {
    $Version = $Version.Substring(1)
}
if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    throw "Version '$Version' is not a stable semantic version (MAJOR.MINOR.PATCH)."
}

$ProjectVersionLine = Select-String -Path (Join-Path $Root "pyproject.toml") -Pattern '^version = "([^"]+)"$' | Select-Object -First 1
if ($null -eq $ProjectVersionLine) {
    throw "Could not read the project version from pyproject.toml."
}
$ProjectVersion = $ProjectVersionLine.Matches[0].Groups[1].Value
if ($Version -ne $ProjectVersion) {
    throw "Release version '$Version' must match pyproject.toml version '$ProjectVersion'. Bump pyproject.toml before tagging."
}

if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $LocalPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $LocalPython) {
        $PythonExecutable = $LocalPython
    } else {
        $PythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
        if ($null -eq $PythonCommand) {
            throw "No Python interpreter found. Run setup_env.bat first."
        }
        $PythonExecutable = $PythonCommand.Source
    }
}
if (-not (Test-Path $PythonExecutable)) {
    throw "Python interpreter not found: $PythonExecutable"
}

function Invoke-Python {
    param([string[]]$Arguments)
    & $PythonExecutable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

try {
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
    if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }

    Set-Content -Path $GeneratedVersion -Value "__version__ = '$Version'" -Encoding utf8
    Invoke-Python @(
        "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", $DistDir,
        "--workpath", $BuildDir,
        (Join-Path $Root "packaging\SoundMaster.spec")
    )

    $PortableDir = Join-Path $DistDir "SoundMaster"
    if (-not (Test-Path (Join-Path $PortableDir "SoundMaster.exe"))) {
        throw "PyInstaller did not produce SoundMaster.exe."
    }

    # The marker makes only the ZIP build store data beside the executable.
    Set-Content -Path (Join-Path $PortableDir ".portable") -Value "SoundMaster portable mode" -Encoding utf8
    Copy-Item (Join-Path $Root "README.md") $PortableDir -Force
    Copy-Item (Join-Path $Root "LICENSE") $PortableDir -Force
    Copy-Item (Join-Path $Root "CHANGELOG.md") $PortableDir -Force
    Copy-Item (Join-Path $Root "THIRD_PARTY_NOTICES.md") $PortableDir -Force

    $PortableZip = Join-Path $DistDir "SoundMaster-v$Version-Portable.zip"
    Compress-Archive -Path $PortableDir -DestinationPath $PortableZip -CompressionLevel Optimal -Force
    if (-not (Test-Path $PortableZip)) {
        throw "Portable ZIP was not created: $PortableZip"
    }

    # Do not let the portable marker leak into the installed per-user build.
    Remove-Item (Join-Path $PortableDir ".portable") -Force

    $Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($null -eq $Iscc) {
        $KnownIsccPaths = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        $KnownIscc = $KnownIsccPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($KnownIscc) {
            $Iscc = @{ Source = $KnownIscc }
        }
    }
    if ($null -eq $Iscc) {
        throw "Inno Setup compiler (ISCC.exe) is required to create the installer."
    }
    & $Iscc.Source "/DMyAppVersion=$Version" (Join-Path $Root "packaging\installer.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
    $InstallerPath = Join-Path $DistDir "installer\SoundMaster-v$Version-Setup.exe"
    if (-not (Test-Path $InstallerPath)) {
        throw "Inno Setup completed but the installer was not found: $InstallerPath"
    }

    Write-Host "Created: $PortableZip"
    Write-Host "Created: $InstallerPath"
}
finally {
    if (Test-Path $GeneratedVersion) {
        Remove-Item $GeneratedVersion -Force
    }
}
