# CM5 carrier (work in progress): schematic -> ERC -> netlist -> netlist check -> design review.
# PCB: placement and DRC so far; routing comes next.
#   powershell -ExecutionPolicy Bypass -File build.ps1
. "$PSScriptRoot\..\..\lib\env.ps1"
Set-Location $PSScriptRoot

Step 'symbols'       { python gen/parts_sym.py }
Step 'footprints'    { & $kpy gen/cm5_fp.py; & $kpy gen/hr911130a_fp.py --compare; python gen/g2423s_fp.py; & $kpy gen/m2_fp.py }
Step 'schematic'     { python gen/board.py }
Step 'ERC'           { & $cli sch erc --severity-all --exit-code-violations -o erc.rpt cm5.kicad_sch | Out-Null }
Step 'netlist'       { & $cli sch export netlist --format kicadsexpr -o net.txt cm5.kicad_sch | Out-Null }
Step 'netlist check' { & $kpy "$Lib\check_netlist.py" . }
Step 'review'        { & $kpy "$Lib\review.py" . }
# Placement only (not routed yet): pads vs netlist, courtyards and outline are checked by gen/pcb.py;
# DRC may report unconnected pads and nothing else.
Step 'PCB'           { & $kpy gen/pcb.py }
Step 'DRC'           { & $cli pcb drc --severity-error --schematic-parity -o drc.rpt cm5.kicad_pcb | Out-Null }
$other = Select-String drc.rpt -Pattern '^\[' | Where-Object { $_.Line -notmatch '^\[unconnected_items\]' }
if ($other) { $other | ForEach-Object { $_.Line }; throw 'DRC errors other than unconnected pads' }
Select-String drc.rpt -Pattern '^\*\* Found' | ForEach-Object { '  ' + $_.Line }
Write-Host '== done'
