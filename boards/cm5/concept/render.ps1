# cm5-concept.kicad_pcb → 4 張 3D 圖,輸出到 render(先跑 concept.py)
$K = "$env:LOCALAPPDATA\Programs\KiCad\10.0\bin\kicad-cli.exe"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force render | Out-Null
& $K pcb render --side top --quality high --width 2400 --height 1700 --rotate '-50,0,25' --perspective -o render\cm5-3d.png cm5-concept.kicad_pcb
& $K pcb render --side top --quality high --width 2400 --height 1400 --rotate '-75,0,0' --zoom 1.3 -o render\cm5-3d-ports.png cm5-concept.kicad_pcb
& $K pcb render --side top --quality high --width 2400 --height 1700 --rotate '-50,0,200' --perspective -o render\cm5-3d-rear.png cm5-concept.kicad_pcb
& $K pcb render --side top --quality high --width 2400 --height 1700 -o render\cm5-3d-top.png cm5-concept.kicad_pcb
