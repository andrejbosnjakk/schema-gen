# Smoke test of the built (or installed) desktop app: .\packaging\smoke.ps1 [-Exe <schemagen.exe>]
# Starts it with a fresh SCHEMAGEN_HOME, waits for /api/health, checks the "schemagen" window, closes it, checks the server stopped.
param([string]$Exe = "$PSScriptRoot\build\app\schemagen\schemagen.exe", [string]$Home_ = "$env:RUNNER_TEMP\schemagen-home")
$ErrorActionPreference = "Stop"
if (-not $env:RUNNER_TEMP) { $Home_ = Join-Path $env:TEMP "schemagen-smoke" }
Remove-Item -Recurse -Force $Home_ -ErrorAction SilentlyContinue
$env:SCHEMAGEN_HOME = $Home_; $log = "$Home_\logs\schemagen.log"

$sw = [Diagnostics.Stopwatch]::StartNew(); $p = Start-Process $Exe -PassThru; $url = $null
while (-not $url -and $sw.Elapsed.TotalSeconds -lt 90) {
    if ($p.HasExited) { throw "the app exited during startup (code $($p.ExitCode)); see $log" }
    if (Test-Path $log) { $m = Select-String -Path $log -Pattern "serving (http://\S+)"; if ($m) { $url = $m.Matches[0].Groups[1].Value } }
    Start-Sleep -Milliseconds 100
}
if (-not $url) { throw "no server within 90 s; see $log" }
$health = Invoke-RestMethod "${url}api/health"
"health after {0:N2} s at {1}: {2}" -f $sw.Elapsed.TotalSeconds, $url, ($health | ConvertTo-Json -Compress)
while (-not (Get-Process -Id $p.Id).MainWindowTitle -and $sw.Elapsed.TotalSeconds -lt 90) { Start-Sleep -Milliseconds 200 }
$title = (Get-Process -Id $p.Id).MainWindowTitle
if ($title -ne "schemagen") { throw "window title '$title', expected 'schemagen'" }
"window '$title' after {0:N2} s" -f $sw.Elapsed.TotalSeconds
Start-Sleep 2
(Get-Process -Id $p.Id).CloseMainWindow() | Out-Null
if (-not $p.WaitForExit(15000)) { $p.Kill(); throw "the app did not exit after its window closed" }
try { Invoke-WebRequest "${url}api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; throw "the server still answers after exit" } catch [System.Net.WebException] { "closed; server stopped" }
Get-Content $log
