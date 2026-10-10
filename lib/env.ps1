# Shared setup for boards/*/build.ps1. Dot-source it:  . "$PSScriptRoot\..\..\lib\env.ps1"
#
# Finds KiCad 10 (override with $env:KICAD_BIN = folder containing kicad-cli.exe) and the
# freerouting jar + Java 25 runtime that tools\setup-tools.ps1 downloads into tools\.
$ErrorActionPreference = 'Stop'

$Lib  = $PSScriptRoot
$Repo = Split-Path $Lib -Parent

$kicad = @($env:KICAD_BIN,
           "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin",
           "$env:ProgramFiles\KiCad\10.0\bin") |
    Where-Object { $_ -and (Test-Path (Join-Path $_ 'kicad-cli.exe')) } |
    Select-Object -First 1
if (-not $kicad) { throw 'KiCad 10 not found. Set KICAD_BIN to the folder that contains kicad-cli.exe.' }
$cli = Join-Path $kicad 'kicad-cli.exe'
$kpy = Join-Path $kicad 'python.exe'     # KiCad's bundled Python: the only one with pcbnew

$java = Get-ChildItem "$Repo\tools\jre\*\bin\java.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
$fr = "$Repo\tools\freerouting\freerouting-2.5.0.jar"
if (-not $java -or -not (Test-Path $fr)) {
    throw 'freerouting or its Java runtime is missing. Run tools\setup-tools.ps1 once.'
}

# Run one pipeline step; stop the whole build on the first failure.
function Step($name, [scriptblock]$body) {
    Write-Host "== $name" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
}

# freerouting autoroute. The DSN carries no copper-to-edge rule, so pass it explicitly or the
# router hugs the board edge. Extra arguments are appended (e.g. neck-down settings).
# Reproducible routing needs both: the DSN must not change between runs (lib/pcbgen.py seeds
# KiCad's UUID generator; the Specctra exporter orders by UUID) and freerouting's optimizer must
# run on one thread (with several, the same DSN gives different vias/tracks each run, and some
# of those fail DRC). Retrying would only repeat the result, so stop when more than
# $allowUnrouted connections are left (relay8 leaves its mains nets to the script on purpose).
function Invoke-Freerouting($dsn, $ses, $passes, [string[]]$extra = @(), [int]$allowUnrouted = 0) {
    & $java -jar $fr -de $dsn -do $ses "--router.autorouter.max_passes=$passes" `
        --gui.enabled=false --router.copper_to_edge_clearance_um=500 `
        --router.optimizer.max_threads=1 @extra *> freerouting.log
    $line = Select-String freerouting.log -Pattern 'Auto-routing stage completed' |
        Select-Object -Last 1 -ExpandProperty Line
    Write-Host ('  ' + ($line -replace '^.*completed:', ''))
    if ($line -match '\((\d+) unrouted' -and [int]$Matches[1] -le $allowUnrouted) { return }
    throw "freerouting left more than $allowUnrouted unrouted connections (see freerouting.log)"
}
