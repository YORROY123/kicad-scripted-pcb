"""八路继电器板(v2,一条市电线供全部)的摆放与市电处理。必须用 KiCad 自带的 python.exe 跑。

    pcb.py place    网表 → 放件 → 开槽 → 市电铜(汇流排、COM/N 竖线、NO/NC、输入区)
                    → 低压布线禁止区 → 端子丝印 → DRC 规则文件
    (freerouting 只布低压线;lib/route.py ses 导入并铺 GND —— 它会删掉所有 zone,包括禁止区)
    pcb.py finish   补回市电铜 → GND 铺铜禁止区 → 重新填充

板子 232 × 110 mm,y 向下。上缘:J20 市电输入 + 8 个输出端子(NO · N · NC);其下两条
B.Cu 汇流排(N、L);再下面继电器(触点朝上)。左侧:F1 → F2 → PS1(HLK-10M05,AC 脚在上,
DC 脚在 42.5mm 下方的低压区)。y ≈ 50 以下、x > 40 是低压区;ESP32 天线朝下缘。
几何细节与间距依据见 mains.py。
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
W, H = 232.0, 110.0

# 继电器 COM 焊盘:触点焊盘(COM 上方 14.2)离 L 汇流排下沿 ≥ 2.4mm(市电 ↔ 市电)
RELAY_Y = 44.0
LED_Y = RELAY_Y + 7.7   # 指示灯一排,紧贴继电器与槽的下方
LABEL_BELOW = 7.0       # 端子标签在焊盘下方多少 mm(端子 courtyard 下沿在焊盘下 5mm)
PITCH = 24.0            # 每路栏宽:3 位 7.5mm 端子宽 23.6mm


def xc(ch: int) -> float:
    return 50.0 + PITCH * (ch - 1)


place = {}
for ch in range(1, 9):
    place[f"J{10 + ch}"] = (xc(ch) + 7.5, mains.TERM_Y, 180)   # NO @ +7.5、N @ 0、NC @ −7.5
    place[f"K{ch}"] = (xc(ch), RELAY_Y, 90)                     # 触点朝上
    place[f"R{10 + ch}"] = (xc(ch) - 4.5, LED_Y, 90)             # 指示灯限流
    place[f"D{10 + ch}"] = (xc(ch) + 4.5, LED_Y, 90)             # 指示灯

# ESP32 模块转 180°:天线朝下缘。原本左排的引脚(3V3、EN、IO8、IO9)转到右侧。
MX, MY = 200.0, H - 18.64


def module_pin_y(n: int) -> float:
    """原左排第 n 脚(转 180° 后在右侧)的 y。"""
    return MY + 6.0 - 1.5 * (n - 1)


place.update({
    # 市电输入区(左上):J20 → F1(竖)→ F2 → PS1(竖,AC 在上)
    "J20": (21.5, mains.TERM_Y, 180),   # L @ 21.5、N @ 14.0
    "F1": (21.5, 31.0, -90),            # 夹子:L_IN @ y 31 / 37.8,L_BUS @ y 47.4 / 54.1
    "RV1": (34.0, mains.L_BUS_Y, 90),   # 1 脚压在 L 汇流排上,2 脚压在 N 汇流排上
    "F2": (30.5, 48.5, -90),            # L_BUS @ y 48.5 → L_PS @ y 53.6
    "PS1": (21.0, 61.0, -90),           # AC/L (21, 61)、AC/N (13.2, 61);DC 在 y 103.5
    "C5": (38.0, 100.0, 90),            # 5V_PS 储能,紧贴 PS1 的 DC 端
    "D4": (48.0, 104.0, 0),             # 5V_PS → 5V_SYS
    "D5": (48.0, 98.0, 0),              # VBUS → 5V_SYS
    # LDO
    "U2": (58.0, 101.0, 0),
    "C1": (58.0, 97.0, 0),
    "C2": (63.0, 101.0, 90),
    # USB-C 在下缘(开口朝下),CC 电阻与 ESD 紧贴
    "J1": (75.0, H - 4.2, 0),
    "R1": (71.0, 97.5, 0),
    "R2": (79.0, 97.5, 0),
    "D1": (84.0, 100.0, 0),
    # 电源 LED、按键、UART 排针
    "R8": (92.0, 104.5, 0),
    "D3": (92.0, 107.5, 0),
    "SW1": (105.0, 104.0, 0),
    "SW2": (120.0, 104.0, 0),
    "J2": (135.0, 92.0, 0),
    # ULN2803:输出朝上(O1 在左对 K1),输入朝下
    "U3": (134.0, 62.0, 90),
    # ESP32 与它右侧(x > 209.74)的去耦、EN 的 RC、IO8/IO9 上拉
    "U1": (MX, MY, 180),
    "C3": (212.0, module_pin_y(1) - 0.4, 90),
    "R3": (212.0, module_pin_y(2) - 1.0, 90),
    "C4": (215.0, module_pin_y(2) - 1.0, 90),
    "R5": (212.0, module_pin_y(7), 90),
    "R4": (215.0, module_pin_y(8), 90),
    "R6": (188.0, MY + 3.0, 90),        # IO2(原右排第 16 脚,转 180° 后在左侧)
})

RELAY8 = BoardSpec(
    name="relay8",
    width=W,
    height=H,
    place=place,
    power_nets=("GND", "VBUS", "+3V3", "5V_PS", "5V_SYS"),
    overhang=("J1",),
    min_hole=0.2,
    fab_ref_libs=("Resistor_SMD", "Capacitor_SMD"),
    # 市电网:RL1_NO … RL8_NC、L_IN / L_BUS / L_PS、N_BUS。
    # RL?_* 不能写成 RL*:后者会把低压的线圈驱动网 RLY1… 也吞进来。
    netclasses=(("Mains", mains.SWITCH_W, 2.4, "RL?_*", "L_*", "N_BUS"),),
)


def stage_place() -> None:
    build(RELAY8, ROOT / "net.txt", PCB)
    board = pcbnew.LoadBoard(str(PCB))
    slots = mains.add_slots(board)
    tracks = mains.add_mains_tracks(board)
    mains.add_routing_keepouts(board, W)
    labels = mains.add_terminal_labels(board, LABEL_BELOW)
    board.Save(str(PCB))
    (ROOT / "relay8.kicad_dru").write_text(mains.DRU, encoding="utf-8", newline="\n")
    print(f"mains: {tracks} segments, {slots} slots, {labels} terminal labels, routing keepouts; "
          f"wrote relay8.kicad_dru")


def stage_finish() -> None:
    board = pcbnew.LoadBoard(str(PCB))
    tracks = mains.add_mains_tracks(board)
    mains.add_fill_keepouts(board, W)
    # USB-C 外壳脚实心接地:热焊盘在板边只接得上 1 条引线(starved_thermal),外壳本就该牢接地
    for pad in board.FindFootprintByReference("J1").Pads():
        if pad.GetNumber() == "SH":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(str(PCB))
    print(f"mains: re-added {tracks} segments, GND fill keepouts, zones refilled")


if __name__ == "__main__":
    {"place": stage_place, "finish": stage_finish}[sys.argv[1]]()
