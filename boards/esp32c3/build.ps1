# ESP32-C3 minimal board: schematic -> ERC -> netlist -> netlist check -> PCB -> autoroute -> GND pour -> DRC.
#   powershell -ExecutionPolicy Bypass -File build.ps1
. "$PSScriptRoot\..\..\lib\env.ps1"
Set-Location $PSScriptRoot

Step 'schematic'     { python gen/board.py }
Step 'ERC'           { & $cli sch erc --severity-all --exit-code-violations -o erc.rpt esp32c3.kicad_sch | Out-Null }
Step 'netlist'       { & $cli sch export netlist --format kicadsexpr -o net.txt esp32c3.kicad_sch | Out-Null }
# ERC ignores "global label appears only once" by default: a typo in a label is caught only here
Step 'netlist check' { & $kpy "$Lib\check_netlist.py" . }
Step 'PCB'           { & $kpy gen/pcb.py }
Step 'DSN'           { & $kpy "$Lib\route.py" dsn esp32c3 . }
# Automatic neck-down narrows tracks to 0.125 mm next to 0402 pads (below JLCPCB's 0.127 mm).
# neck_width_um narrows only when a connection cannot route otherwise, and only to 0.15 mm.
Step 'autoroute'     {
    Invoke-Freerouting esp32c3.dsn esp32c3.ses 50 @('--router.automatic_neckdown=false', '--router.neck_width_um=150')
}
Step 'import'        { & $kpy "$Lib\route.py" ses esp32c3 . }
Step 'DRC'           {
    & $cli pcb drc --severity-all --schematic-parity --exit-code-violations -o drc.rpt esp32c3.kicad_pcb | Out-Null
}
Select-String drc.rpt -Pattern '^\*\* Found' | ForEach-Object { '  ' + $_.Line }
Step 'render'        {
    & $cli pcb render --side top --width 1400 --height 1600 --quality basic -o board-top.png esp32c3.kicad_pcb | Out-Null
}
Write-Host '== done' -ForegroundColor Green
