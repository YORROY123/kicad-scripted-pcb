"""八路继电器板的摆放与市电处理。必须用 KiCad 自带的 python.exe 跑。

    pcb.py place    网表 → 放件 → 开槽 → 市电走线 → 低压布线禁止区 → DRC 规则文件
    (freerouting 布低压线;lib/route.py ses 导入并铺 GND —— 它会删掉所有 zone,包括禁止区)
    pcb.py finish   补回市电走线 → GND 铺铜禁止区 → 重新填充

板子 150 × 95 mm,y 向下。上半部是市电区(端子台贴上缘、继电器触点朝上),
y ≈ 35 以下是低压区;ESP32 天线朝下缘、远离继电器与市电。
"""
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from pcbgen import BoardSpec, build  # noqa: E402

import mains  # noqa: E402

PCB = ROOT / "relay8.kicad_pcb"

TERM_Y = 5.64      # 端子台焊盘行:转 180° 后 courtyard 上沿离板缘约 0.5mm
RELAY_Y = 30.3     # 继电器 COM 焊盘:继电器 courtyard 上沿刚好在端子台 courtyard 下方
PITCH = 18.0       # 每路栏宽


def xc(ch: int) -> float:
    return 12.0 + PITCH * (ch - 1)


place = {}
for ch in range(1, 9):
    place[f"J{10 + ch}"] = (xc(ch) + 5.08, TERM_Y, 180)   # 端子台,接线口朝上缘
    place[f"K{ch}"] = (xc(ch), RELAY_Y, 90)               # 继电器,触点朝上
    place[f"R{10 + ch}"] = (xc(ch) - 4.5, 38.0, 90)        # 指示灯限流
    place[f"D{10 + ch}"] = (xc(ch) + 4.5, 38.0, 90)        # 指示灯

# ESP32 模块转 180°:天线朝下缘。原本左排的引脚(3V3、EN、IO8、IO9)转到右侧。
MX, MY = 128.0, 95.0 - 18.64


def module_pin_y(n: int) -> float:
    """原左排第 n 脚(转 180° 后在右侧)的 y。"""
    return MY + 6.0 - 1.5 * (n - 1)


place.update({
    "U3": (75.0, 46.0, 90),            # ULN2803:输出朝上(O1 在左对 K1),输入朝下
    "U1": (MX, MY, 180),
    # 模块右侧(x > 137.74):去耦、EN 的 RC、IO8/IO9 上拉
    "C3": (140.0, module_pin_y(1) - 0.4, 90),
    "R3": (140.0, module_pin_y(2) - 1.0, 90),
    "C4": (143.0, module_pin_y(2) - 1.0, 90),
    "R5": (140.0, module_pin_y(7), 90),
    "R4": (143.0, module_pin_y(8), 90),
    "R6": (116.0, MY + 3.0, 90),       # IO2(原右排第 16 脚,转 180° 后在左侧)
    # USB-C 在左缘(开口朝左),ESD 紧贴
    "J1": (4.2, 62.0, -90),
    "R1": (11.0, 55.5, 90),
    "R2": (11.0, 68.5, 90),
    "D1": (14.0, 62.0, 0),
    # 5V DC 插座在左下缘(开口朝左)、储能电容、OR 二极管
    "J3": (13.8, 84.0, 0),
    "C5": (22.0, 88.0, 0),
    "D4": (27.0, 80.0, 0),
    "D5": (27.0, 74.0, 0),
    # LDO 一组与电源 LED
    "U2": (38.0, 74.0, 0),
    "C1": (38.0, 70.0, 0),
    "C2": (43.0, 74.0, 90),
    "R8": (48.0, 70.0, 0),
    "D3": (48.0, 73.5, 0),
    # 按键与 UART 排针
    "SW1": (60.0, 88.0, 0),
    "SW2": (75.0, 88.0, 0),
    "J2": (95.0, 78.0, 0),
})

RELAY8 = BoardSpec(
    name="relay8",
    width=150.0,
    height=95.0,
    place=place,
    power_nets=("GND", "VBUS", "+3V3", "DC_IN", "5V_SYS"),
    overhang=("J1", "J3"),
    min_hole=0.2,
    fab_ref_libs=("Resistor_SMD", "Capacitor_SMD"),
    # 市电网:RL1_COM … RL8_NC。通配符写成 RL?_* —— RL* 会把低压的线圈驱动网 RLY1… 也吞进来
    netclasses=(("Mains", mains.MAINS_W, 2.4, "RL?_*"),),
)


def stage_place() -> None:
    build(RELAY8, ROOT / "net.txt", PCB)
    board = pcbnew.LoadBoard(str(PCB))
    slots = mains.add_slots(board)
    tracks = mains.add_mains_tracks(board)
    mains.add_routing_keepouts(board)
    board.Save(str(PCB))
    (ROOT / "relay8.kicad_dru").write_text(mains.DRU, encoding="utf-8", newline="\n")
    print(f"mains: {tracks} tracks, {slots} slots, routing keepouts on 8 channels; wrote relay8.kicad_dru")


def stage_finish() -> None:
    board = pcbnew.LoadBoard(str(PCB))
    tracks = mains.add_mains_tracks(board)
    mains.add_fill_keepouts(board)
    # USB-C 外壳脚实心接地:热焊盘在板边只接得上 1 条引线(starved_thermal),外壳本就该牢接地
    for pad in board.FindFootprintByReference("J1").Pads():
        if pad.GetNumber() == "SH":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(str(PCB))
    print(f"mains: re-added {tracks} tracks, GND fill keepouts on 8 channels, zones refilled")


if __name__ == "__main__":
    {"place": stage_place, "finish": stage_finish}[sys.argv[1]]()
