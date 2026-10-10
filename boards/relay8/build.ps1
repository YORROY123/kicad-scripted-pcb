# ESP32-C3 8-channel MAINS relay board.
#   schematic -> ERC -> netlist check -> place + mains (pre-routed) -> freerouting (low voltage only)
#   -> GND pour -> mains finish -> DRC (errors block, warnings listed)
#   powershell -ExecutionPolicy Bypass -File build.ps1
# WARNING: this board switches 110/230 VAC. A clean DRC is not an electrical-safety review.
. "$PSScriptRoot\..\..\lib\env.ps1"
Set-Location $PSScriptRoot

Step 'schematic'     { python gen/board.py }
Step 'ERC'           { & $cli sch erc --severity-all --exit-code-violations -o erc.rpt relay8.kicad_sch | Out-Null }
Step 'netlist'       { & $cli sch export netlist --format kicadsexpr -o net.txt relay8.kicad_sch | Out-Null }
Step 'netlist check' { & $kpy "$Lib\check_netlist.py" . }
# Design review: datasheet rules on the netlist (TVS polarity, LED current, decoupling, straps...)
Step 'review'        { & $kpy "$Lib\review.py" . }
# placement, isolation slots, mains tracks, low-voltage routing keepouts, relay8.kicad_dru
Step 'place+mains'   { & $kpy gen/pcb.py place }
Step 'DSN'           { & $kpy "$Lib\route.py" dsn relay8 . }
# mains nets are already connected; the keepouts stop low-voltage tracks entering the mains area
Step 'autoroute'     {
    Invoke-Freerouting relay8.dsn relay8.ses 60 @('--router.automatic_neckdown=false', '--router.neck_width_um=150') 16
}
# route.py deletes every track and zone (keepouts included) before importing,
# so the finish stage re-adds the mains tracks and adds GND-pour keepouts.
Step 'import'        { & $kpy "$Lib\route.py" ses relay8 . }
Step 'mains finish'  { & $kpy gen/pcb.py finish }
Step 'DRC'           {
    & $cli pcb drc --severity-error --schematic-parity --exit-code-violations -o drc.rpt relay8.kicad_pcb | Out-Null
}
Select-String drc.rpt -Pattern '^\*\* Found' | ForEach-Object { '  errors: ' + $_.Line }
& $cli pcb drc --severity-warning -o drc-warnings.rpt relay8.kicad_pcb | Out-Null
Select-String drc-warnings.rpt -Pattern '^\[' | ForEach-Object { ($_.Line -split '\(')[0] } |
    Group-Object | ForEach-Object { '  warning: {0} x {1}' -f $_.Count, $_.Name }
Step 'render'        {
    & $cli pcb render --side top --width 1800 --height 1200 --quality basic -o board-top.png relay8.kicad_pcb | Out-Null
}
# Gerber + drill zip, JLCPCB BOM / CPL; checks drill count and refdes against the board
Step 'fab'           { & $kpy "$Lib\fab.py" relay8 . }
Write-Host '== done' -ForegroundColor Green
