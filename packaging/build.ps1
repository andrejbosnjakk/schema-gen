# Build the Windows desktop app and its installer: .\packaging\build.ps1 [-Python <python.exe>] [-SkipFrontend]
#   1. frontend (npm ci + npm run build into schemagen/app/static), if node is installed
#   2. a build venv packaging\.venv with schemagen, pywebview and PyInstaller
#   3. PyInstaller (packaging\build\app\schemagen\schemagen.exe) and the third-party notices
#   4. Inno Setup, if iscc is found: packaging\dist\schemagen-setup-<version>.exe
param([string]$Python = "", [switch]$SkipFrontend)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot; $root = Split-Path $here -Parent

function Run([string]$exe, [string[]]$a, [string]$cwd = $root) {
    Push-Location $cwd; $ErrorActionPreference = "Continue"  # Windows PowerShell treats a native command's stderr as an error
    try { & $exe @a; if ($LASTEXITCODE) { throw "$exe $($a -join ' ') failed ($LASTEXITCODE)" } } finally { Pop-Location }
}

if (-not $SkipFrontend -and (Get-Command npm -ErrorAction SilentlyContinue)) {
    Run "npm" @("ci") "$root\frontend"; Run "npm" @("run", "build") "$root\frontend"
} else { Write-Host "frontend: using the committed build in schemagen\app\static" }

$venv = "$here\.venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    if (-not $Python) { $Python = (Get-Command python).Source }
    Run $Python @("-m", "venv", $venv)
}
$py = "$venv\Scripts\python.exe"
Run $py @("-m", "pip", "install", "-q", "--upgrade", "pip")
Run $py @("-m", "pip", "install", "-q", "-e", $root, "-r", "$here\requirements.txt")

Run $py @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "$here\build\app", "--workpath", "$here\build\work", "$here\schemagen.spec")
Run $py @("$here\third_party.py")
$version = & $py -c "import schemagen; print(schemagen.__version__)"
$size = (Get-ChildItem "$here\build\app\schemagen" -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("app: {0}\build\app\schemagen\schemagen.exe ({1:N0} MB)" -f $here, $size)

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if ($iscc) {
    Run $iscc @("/Q", "/DAppVersion=$version", "$here\installer.iss") $here
    Write-Host "installer: $here\dist\schemagen-setup-$version.exe"
} else { Write-Host "Inno Setup (iscc) not found: skipped the installer" }
