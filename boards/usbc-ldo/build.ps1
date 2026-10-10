# USB-C 5V -> 3.3V LDO + LED test board: schematic -> ERC -> netlist -> PCB -> autoroute -> GND pour -> DRC.
#   powershell -ExecutionPolicy Bypass -File build.ps1
. "$PSScriptRoot\..\..\lib\env.ps1"
Set-Location $PSScriptRoot

Step 'schematic' { python gen/board.py }
Step 'ERC'       { & $cli sch erc --severity-all --exit-code-violations -o erc.rpt usbc-ldo.kicad_sch | Out-Null }
Step 'netlist'   { & $cli sch export netlist --format kicadsexpr -o net.txt usbc-ldo.kicad_sch | Out-Null }
# Design review: datasheet rules on the netlist (TVS polarity, LED current, decoupling, straps...)
Step 'review'        { & $kpy "$Lib\review.py" . }
Step 'PCB'       { & $kpy gen/pcb.py }
Step 'DSN'       { & $kpy "$Lib\route.py" dsn usbc-ldo . }
Step 'autoroute' { Invoke-Freerouting usbc-ldo.dsn usbc-ldo.ses 30 }
Step 'import'    { & $kpy "$Lib\route.py" ses usbc-ldo . }
Step 'DRC'       {
    & $cli pcb drc --severity-all --schematic-parity --exit-code-violations -o drc.rpt usbc-ldo.kicad_pcb | Out-Null
}
Select-String drc.rpt -Pattern '^\*\* Found' | ForEach-Object { '  ' + $_.Line }
Step 'render'    {
    & $cli pcb render --side top --width 1600 --height 1000 --quality basic -o board-top.png usbc-ldo.kicad_pcb | Out-Null
}
# Gerber + drill zip, JLCPCB BOM / CPL; checks drill count and refdes against the board
Step 'fab'           { & $kpy "$Lib\fab.py" usbc-ldo . }
Write-Host '== done' -ForegroundColor Green
