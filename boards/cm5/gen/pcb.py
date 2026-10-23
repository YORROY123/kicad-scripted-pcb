"""CM5 載板的正式擺件:網表 → cm5.kicad_pcb(板框、4 層、網路類別、固定孔、自檢)。

還沒佈線。座標與自動擺件在 gen/placement.py(3D 預覽 concept/ 也用同一份)。
必須用 KiCad 自帶的 python.exe 跑:
    <KiCad python> gen/pcb.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import pcbgen  # noqa: E402
import pcbnew  # noqa: E402
from pcbgen import BoardSpec, build  # noqa: E402
from placement import BOARD_HOLES, H, MODULE_HOLES, W, auto_place  # noqa: E402

BOARD = HERE.parent
pcbgen.EXTRA_FP_DIRS.append(str(BOARD / "footprints"))

# 接頭開口要切齊板邊,courtyard 本來就伸出板外;只查焊盤在板內
OVERHANG = ("J20", "J30", "J40", "J41", "J50", "J51", "J52", "J70", "SW51")

# 線寬 mm、間距 mm、網名。先求能佈通,阻抗控制(USB3/PCIe/HDMI 差分)與實際電流的線寬
# 在佈線那一步依疊層算過再改,見 README「PCB 待辦」。
NETCLASSES = (
    # 54 V 輸入與 PoE 輸出。IPC-2221 表 6-1 的 51–100 V:外層有防焊(B4)0.13 mm、無塗層(B2)0.6 mm。
    # 板子有防焊,取 0.25 mm 留餘量。0.6 mm 做不到:RJ45 腳之間只有 0.53、IP804AR(QFN 0.5)0.25。
    ("HV54", 0.5, 0.25, "+54V", "POE*", "SW"),
    # 5 V / 12 A 主電源與 3.3 V / 8 A:之後改用鋪銅,這裡先給最寬的走線
    ("Rail", 0.8, 0.2, "+5V", "+3V3", "SW3"),
)
POWER = ("GND", "CM5_3V3", "IP_3V3", "LAN0_1V2", "LAN1_1V2", "LAN0_2V5", "LAN1_2V5",
         "USBA0_VBUS", "USBA1_VBUS", "USBC_VBUS")


def placement(net_path: Path) -> dict:
    comps, pad_net = pcbgen.read_netlist(net_path)
    fps = {}
    for ref, info in comps.items():
        lib, name = info["footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(pcbgen.fp_lib_dir(lib)), name)
        if fp is None:
            raise SystemExit(f"{ref}: 载入封装失败 {info['footprint']}")
        fps[ref] = fp
    return auto_place(fps, pad_net)


def spec(place: dict) -> BoardSpec:
    holes = list(BOARD_HOLES) + [(x, y, "MountingHole:MountingHole_2.7mm_M2.5") for x, y in MODULE_HOLES]
    return BoardSpec(
        name="cm5",
        width=W,
        height=H,
        place=place,
        power_nets=POWER,
        netclasses=NETCLASSES,
        overhang=OVERHANG,
        fab_ref_libs=("Resistor_SMD", "Capacitor_SMD"),
        mounting_holes=tuple(holes),
        copper_layers=4,
    )


# 同一顆零件的焊盤之間照原廠焊盤圖,不套網路類別間距:FSUSB42(MSOP-10 0.5 mm)焊盤間只有
# 0.15 mm。0.1 mm 仍高於 JLCPCB 4 層板最小線距 0.09 mm。走線、過孔照網路類別。
DRU = """(version 1)
(rule "pads within one footprint"
  (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.Parent == B.Parent")
  (constraint clearance (min 0.1mm)))
"""


if __name__ == "__main__":
    net = BOARD / "net.txt"
    (BOARD / "cm5.kicad_dru").write_text(DRU, encoding="utf-8")
    build(spec(placement(net)), net, BOARD / "cm5.kicad_pcb")
