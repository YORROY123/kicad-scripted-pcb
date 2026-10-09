"""ESP32-C3 八路继电器板:每路 SRD 继电器切市电(NO / COM / NC 端子),ULN2803 驱动。

⚠ 继电器触点接市电(110/220VAC)。原理图与 DRC 通过 ≠ 电气安全;送厂、通电前必须由懂
电气安全的人审查,并装在外壳里使用。

电源(为什么这样分):
  - DC_IN:5V DC 插座(≥2A)直接供 8 个线圈(全吸合约 8 × 72mA ≈ 0.6A)+ 100µF 储能
  - 5V_SYS:DC_IN 与 USB VBUS 各经一颗 SS34 并联 → AP2112K-3.3 → +3V3
      只插 USB:MCU 能烧录、能跑,但线圈没电,继电器不动作 —— 刻意的,USB 不会被线圈拉垮
      二极管同时防止 DC 电源倒灌进电脑的 USB 口
驱动:ULN2803A(达林顿阵列,内建续流二极管 COM 接线圈电源;输入内建下拉,开机不乱跳)
引脚:K1–K8 ← IO0、IO1、IO3、IO4、IO5、IO6、IO7、IO10(避开 USB 18/19、UART 20/21、
      strapping 2/8/9)
指示:每路一颗红色 LED 与线圈并联(DC_IN → 1k → LED → ULN 输出),吸合时亮

继电器引脚(KiCad Relay:SANYOU_SRD_Form_C,符号引脚无名称,依符号图形与封装确认):
  2、5 = 线圈;1 = COM;3 = NO(常开);4 = NC(常闭)
  —— 符号里开关臂静止时靠在 4 脚 → 4 = NC。厂商 datasheet 的引脚图没能取得核对,
     拿到实物后必须用三用电表确认:不通电时 COM 与 NC 导通。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from netlabel import NetLabeler  # noqa: E402
from schgen import Schematic  # noqa: E402

s = Schematic(paper="A3", title="ESP32-C3 8-channel mains relay board")
n = NetLabeler(s)
add, flag = n.add, n.flag

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0805 = "LED_SMD:LED_0805_2012Metric"
BUTTON = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"

# ── USB-C(烧录 / 调试 / 只给 MCU 供电)───────────────────────────────────
add("J1", "Connector", "USB_C_Receptacle_USB2.0_16P", 25, 60, "USB-C",
    "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
        "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
        "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "SH": "GND",
        "A5": "CC1", "B5": "CC2",
        "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
        "A8": None, "B8": None,
    })
add("R1", "Device", "R", 55, 45, "5.1k", R0402, {"1": "CC1", "2": "GND"})
add("R2", "Device", "R", 63, 45, "5.1k", R0402, {"1": "CC2", "2": "GND"})
add("D1", "Power_Protection", "USBLC6-2P6", 60, 85, "USBLC6-2P6",
    "Package_TO_SOT_SMD:SOT-23-6", {
        "1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN",
        "5": "VBUS", "2": "GND",
    })
flag("VBUS", 15, 25)
flag("GND", 22, 25)

# ── 5V DC 输入(继电器线圈电源)与 5V_SYS ────────────────────────────────
add("J3", "Connector", "Barrel_Jack", 20, 125, "5V DC 2A",
    "Connector_BarrelJack:BarrelJack_Horizontal", {"1": "DC_IN", "2": "GND"})
flag("DC_IN", 12, 112)
add("C5", "Device", "C_Polarized", 40, 128, "100uF", "Capacitor_SMD:CP_Elec_6.3x7.7",
    {"1": "DC_IN", "2": "GND"})
# SS34:1 = K、2 = A
add("D4", "Diode", "SS34", 60, 118, "SS34", "Diode_SMD:D_SMA", {"2": "DC_IN", "1": "5V_SYS"})
add("D5", "Diode", "SS34", 60, 135, "SS34", "Diode_SMD:D_SMA", {"2": "VBUS", "1": "5V_SYS"})
# 5V_SYS 只经二极管(passive)进来,ERC 会判「电源输入未被驱动」;这里确实是电源入口
flag("5V_SYS", 72, 112)

# ── 3.3V LDO ───────────────────────────────────────────────────────────
add("U2", "Regulator_Linear", "AP2112K-3.3", 100, 30, "AP2112K-3.3",
    "Package_TO_SOT_SMD:SOT-23-5", {"1": "5V_SYS", "3": "5V_SYS", "2": "GND", "5": "+3V3", "4": None})
add("C1", "Device", "C", 84, 30, "1uF", C0402, {"1": "5V_SYS", "2": "GND"})
add("C2", "Device", "C", 116, 30, "10uF", C0805, {"1": "+3V3", "2": "GND"})
add("C3", "Device", "C", 124, 30, "100nF", C0402, {"1": "+3V3", "2": "GND"})
add("R8", "Device", "R", 100, 60, "1k", R0402, {"1": "+3V3", "2": "LED_PWR_A"})
add("D3", "Device", "LED", 100, 74, "GREEN", LED0805, {"2": "LED_PWR_A", "1": "GND"})

# ── 复位、启动、strapping ───────────────────────────────────────────────
add("R3", "Device", "R", 88, 95, "10k", R0402, {"1": "+3V3", "2": "EN"})
add("C4", "Device", "C", 96, 95, "1uF", C0402, {"1": "EN", "2": "GND"})
add("SW1", "Switch", "SW_Push", 92, 110, "RESET", BUTTON, {"1": "EN", "2": "GND"})
add("R4", "Device", "R", 88, 125, "10k", R0402, {"1": "+3V3", "2": "IO9"})
add("SW2", "Switch", "SW_Push", 92, 140, "BOOT", BUTTON, {"1": "IO9", "2": "GND"})
add("R5", "Device", "R", 110, 95, "10k", R0402, {"1": "+3V3", "2": "IO8"})
add("R6", "Device", "R", 118, 95, "10k", R0402, {"1": "+3V3", "2": "IO2"})
add("J2", "Connector_Generic", "Conn_01x04", 115, 125, "UART",
    "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    {"1": "+3V3", "2": "GND", "3": "TXD", "4": "RXD"})

# ── ESP32-C3 模块 ──────────────────────────────────────────────────────
GPIO_PIN = {  # 继电器通道 → 模块引脚号(ESP32-C3-WROOM-02)
    1: "18",  # IO0
    2: "17",  # IO1
    3: "15",  # IO3
    4: "3",   # IO4
    5: "4",   # IO5
    6: "5",   # IO6
    7: "6",   # IO7
    8: "10",  # IO10
}
module_pins = {
    "1": "+3V3", "9": "GND", "19": "GND",
    "2": "EN", "8": "IO9", "7": "IO8", "16": "IO2",
    "13": "USB_DN", "14": "USB_DP",
    "11": "RXD", "12": "TXD",
}
module_pins.update({pin: f"IN{ch}" for ch, pin in GPIO_PIN.items()})
add("U1", "RF_Module", "ESP32-C3-WROOM-02", 165, 80, "ESP32-C3-WROOM-02-N4",
    "RF_Module:ESP32-C3-WROOM-02", module_pins)

# ── ULN2803A ───────────────────────────────────────────────────────────
uln = {str(ch): f"IN{ch}" for ch in range(1, 9)}               # I1..I8 = 1..8
uln.update({str(19 - ch): f"RLY{ch}" for ch in range(1, 9)})   # O1..O8 = 18..11
uln.update({"9": "GND", "10": "DC_IN"})                        # COM 接线圈电源:续流箝位
add("U3", "Transistor_Array", "ULN2803A", 215, 80, "ULN2803A",
    "Package_SO:SOIC-18W_7.5x11.6mm_P1.27mm", uln)

# ── 8 个通道:继电器 + 端子 + 指示灯 ─────────────────────────────────────
for ch in range(1, 9):
    col, row = (ch - 1) % 2, (ch - 1) // 2
    x0, y0 = 255 + 45 * col, 35 + 50 * row
    add(f"K{ch}", "Relay", "SANYOU_SRD_Form_C", x0, y0 + 12, "SRD-05VDC-SL-C",
        "Relay_THT:Relay_SPDT_SANYOU_SRD_Series_Form_C", {
            "5": "DC_IN", "2": f"RLY{ch}",        # 线圈
            "1": f"RL{ch}_COM", "3": f"RL{ch}_NO", "4": f"RL{ch}_NC",
        })
    # 端子顺序 NO / COM / NC,与板上丝印一致
    add(f"J{10 + ch}", "Connector", "Screw_Terminal_01x03", x0 + 26, y0 + 12, f"CH{ch}",
        "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal", {
            "1": f"RL{ch}_NO", "2": f"RL{ch}_COM", "3": f"RL{ch}_NC",
        })
    add(f"R{10 + ch}", "Device", "R", x0 - 16, y0 + 4, "1k", R0402,
        {"1": "DC_IN", "2": f"LED{ch}_A"})
    add(f"D{10 + ch}", "Device", "LED", x0 - 16, y0 + 18, "RED", LED0805,
        {"2": f"LED{ch}_A", "1": f"RLY{ch}"})

n.write(HERE.parent / "relay8.kicad_sch")
