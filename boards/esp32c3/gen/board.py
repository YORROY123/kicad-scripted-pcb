"""ESP32-C3 最小系统板:USB-C 供电 + 原生 USB 下载/调试 + 3.3V LDO + 按键 + LED + 排针。

依据 Espressif《ESP32-C3 硬件设计指南》与 ESP32-C3-WROOM-02 规格书:
  - USB D-/D+ 直连 GPIO18/GPIO19(芯片内置 USB Serial/JTAG,不需要 USB 转串口芯片)
  - EN:10k 上拉 + 1µF 对地(上电复位延时),RESET 键把 EN 拉低
  - GPIO9 是启动模式脚:上拉 = 从 flash 启动;按住 BOOT 键(拉低)上电 = 下载模式
  - GPIO2、GPIO8 是 strapping 脚,上电时须为高,各 10k 上拉
  - 用户 LED 接 GPIO10(不是 strapping 脚,接 LED 不影响启动)

电源吸取 usbc-ldo 那块板子的模拟教训(见 AGENTS.md):
  - 不串二极管、LDO 用 LP38693MP-3.3(壓差 ~330mV @0.5A;輸入耐壓 12V,扛得住熱插拔過衝)
  - 插入浪湧:模組內部還有約 12.3µF,直接接 VBUS 會灌進約 79µC(> USB 2.0 的 50µC)
    → 加 P-MOSFET 軟啟動(Q1,見下方與 sim/softstart_sim.py)

画法:网络标签式。每个引脚沿「离开器件」的方向拉 2.54mm 短线挂一个全局标签,
电路本身就是下面那张「引脚 → 网络」对照表,审查时逐行对 datasheet 即可。
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE.parents[2] / "lib"
sys.path.insert(0, str(SHARED))
from schgen import Part, Schematic  # noqa: E402

G = 1.27
STUB = 2 * G


def g(n: float) -> float:
    return round(n * G, 4)


s = Schematic(title="ESP32-C3 minimal board (USB-C, native USB)")


def outward(part: Part, pin: str) -> tuple[float, float]:
    """引脚「离开器件」的单位方向(图纸坐标,y 向下)。

    符号库里引脚的 angle 指向器件本体;反过来就是向外。还要套上器件的旋转。
    """
    part.pin_xy(pin)                       # 确保 _pins 已载入
    a = math.radians(part._pins[pin]["angle"] + 180)
    vx, vy = math.cos(a), -math.sin(a)     # 符号库 y 向上 → 图纸 y 向下
    r = math.radians(part.rotation)
    rx = vx * math.cos(r) - vy * math.sin(r)
    ry = vx * math.sin(r) + vy * math.cos(r)
    return round(rx), round(ry)


# 标签朝向:文字顺着短线方向往外长,不压在器件上
LABEL_ROT = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}

# 设计意图:每个引脚应接到哪个网(None = 刻意不接)。写成 JSON 交给 check_netlist.py
# 和 kicad-cli 导出的网表逐脚比对 —— ERC 默认不报「全局标签只出现一次」,
# 标签名打错字会变成一个孤立的网,只有比对网表才抓得到。
EXPECTED: dict = {}


def attach(part: Part, pins: dict) -> Part:
    """按「引脚 → 网络」接线;网络为 None 表示刻意不接(打 NC 记号)。

    同一坐标上的堆叠引脚(USB-C 的 A4/A9/B4/B9 等)只挂一次标签。
    """
    seen = set()
    for pin, net in pins.items():
        if not part.ref.startswith("#"):
            EXPECTED[f"{part.ref}.{pin}"] = net
        xy = part.pin_xy(pin)
        if xy in seen:
            continue
        seen.add(xy)
        if net is None:
            s.no_connect(part, pin)
            continue
        ox, oy = outward(part, pin)
        s.label(net, part, pin, dx=ox * STUB, dy=oy * STUB, rotation=LABEL_ROT[(ox, oy)])
    return part


def add(ref, lib, name, x, y, value, footprint, pins, rot=0.0):
    p = s.add(Part(ref, lib, name, g(x), g(y), value=value, footprint=footprint, rotation=rot))
    return attach(p, pins)


def flag(net: str, x: float, y: float) -> None:
    """PWR_FLAG:告诉 ERC 这个网确实由外部供电(USB 进来的 VBUS、以及 GND)。"""
    p = s.add(Part(f"#FLG{len(s.parts):02d}", "power", "PWR_FLAG", g(x), g(y),
                   value="PWR_FLAG", fields_hidden=True))
    attach(p, {"1": net})


R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0805 = "LED_SMD:LED_0805_2012Metric"
BUTTON = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"

# ── USB-C 输入 ──────────────────────────────────────────────────────────
add("J1", "Connector", "USB_C_Receptacle_USB2.0_16P", 30, 60, "USB-C",
    "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
        "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
        "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "SH": "GND",
        "A5": "CC1", "B5": "CC2",
        # USB-C 正反插:A、B 两面的 D+/D- 在这里并到同一个网
        "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
        "A8": None, "B8": None,          # SBU 本设计不用
    })
# CC 各 5.1k 下拉:告诉 USB-C 供电端「我是设备,给我 5V」
add("R1", "Device", "R", 60, 50, "5.1k", R0402, {"1": "CC1", "2": "GND"})
add("R2", "Device", "R", 68, 50, "5.1k", R0402, {"1": "CC2", "2": "GND"})
# ESD:USBLC6 的 1/6、3/4 是同一条线的两端(穿过式),VBUS 脚做钳位参考
add("D1", "Power_Protection", "USBLC6-2P6", 64, 80, "USBLC6-2P6",
    "Package_TO_SOT_SMD:SOT-23-6", {
        "1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN",
        "5": "VBUS", "2": "GND",
    })
flag("VBUS", 20, 30)
flag("GND", 28, 30)

# ── 3.3V LDO ───────────────────────────────────────────────────────────
# LP38693MP-3.3(TI SNVS321O):輸入絕對最大 12V、壓差 330mV @0.5A、額定 500mA。
# 原本用 AP2112K(絕對最大 6.5V),但 VBUS 只有 1µF 時熱插拔過衝模擬到 8.6V
# (sim/power_sim.py)。500mA 剛好滿足模組規格書「外部電源 ≥0.5A」。
add("U2", "Regulator_Linear", "LP38693MP-3.3", 100, 30, "LP38693MP-3.3",
    "Package_TO_SOT_SMD:SOT-223-5", {
        "4": "VSW", "1": "VSW",          # EN 接 IN:軟啟動後的電源一到就輸出(折返限流此時有效)
        "5": "GND", "3": "+3V3", "2": None,
    })
add("C1", "Device", "C", 82, 30, "1uF", C0402, {"1": "VBUS", "2": "GND"})
add("C2", "Device", "C", 118, 30, "10uF", C0805, {"1": "+3V3", "2": "GND"})
add("C3", "Device", "C", 126, 30, "100nF", C0402, {"1": "+3V3", "2": "GND"})

# ── VBUS 軟啟動(sim/softstart_sim.py)───────────────────────────────────
# 模組內部約 12.3µF + C2 10µF 掛在 LDO 後面,直接接 VBUS 插入時灌進約 79µC,
# 超過 USB 2.0 的 50µC(10µF 等效)。P-MOSFET 串在 VBUS 與 LDO 之間:
#   插入瞬間 C6 把閘極綁在源極 → 先關著;R9 慢慢把閘極拉向地 → 逐漸導通;
#   C7(閘-汲)讓輸出等斜率爬升:爬升段電流 80–97mA(Vth −0.5…−1.3V),3V3 1.3–3.7ms 就緒。
# AO3401A(AOS Rev 3.1):VDS −30V、VGS ±12V、RDS(on) <60mΩ @ −4.5V。
# 限制:拔掉後 C6 經 R9 放電(時間常數 10ms),拔插間隔太短時軟啟動不完整。
add("Q1", "Transistor_FET", "AO3401A", 100, 10, "AO3401A",
    "Package_TO_SOT_SMD:SOT-23", {"1": "SS_G", "2": "VBUS", "3": "VSW"})
add("R9", "Device", "R", 140, 10, "100k", R0402, {"1": "SS_G", "2": "GND"})
add("C6", "Device", "C", 148, 10, "100nF", C0402, {"1": "SS_G", "2": "VBUS"})
add("C7", "Device", "C", 156, 10, "10nF", C0402, {"1": "SS_G", "2": "VSW"})
add("C5", "Device", "C", 164, 10, "1uF", C0402, {"1": "VSW", "2": "GND"})
# VSW 只經 MOSFET(passive)進來,ERC 會判 LDO 的 power_in 未被驅動;這裡確實是電源入口
flag("VSW", 172, 10)

# ── ESP32-C3 模块 ──────────────────────────────────────────────────────
add("U1", "RF_Module", "ESP32-C3-WROOM-02", 170, 80, "ESP32-C3-WROOM-02-N4",
    "RF_Module:ESP32-C3-WROOM-02", {
        "1": "+3V3", "9": "GND", "19": "GND",
        "2": "EN",
        "8": "IO9",                      # BOOT
        "7": "IO8", "16": "IO2",         # strapping,上拉
        "13": "USB_DN", "14": "USB_DP",  # GPIO18 = D-,GPIO19 = D+
        "11": "RXD", "12": "TXD",
        "10": "LED_USER",
        "3": "IO4", "4": "IO5", "5": "IO6", "6": "IO7",
        "18": None, "17": None, "15": None,   # IO0 / IO1 / IO3 未引出
    })

# ── 复位与启动 ──────────────────────────────────────────────────────────
add("R3", "Device", "R", 110, 70, "10k", R0402, {"1": "+3V3", "2": "EN"})
add("C4", "Device", "C", 118, 70, "1uF", C0402, {"1": "EN", "2": "GND"})
add("SW1", "Switch", "SW_Push", 112, 88, "RESET", BUTTON, {"1": "EN", "2": "GND"})
add("R4", "Device", "R", 110, 110, "10k", R0402, {"1": "+3V3", "2": "IO9"})
add("SW2", "Switch", "SW_Push", 112, 128, "BOOT", BUTTON, {"1": "IO9", "2": "GND"})
add("R5", "Device", "R", 226, 50, "10k", R0402, {"1": "+3V3", "2": "IO8"})
add("R6", "Device", "R", 234, 50, "10k", R0402, {"1": "+3V3", "2": "IO2"})

# ── LED ────────────────────────────────────────────────────────────────
# Device:LED 是 1 = K(阴极)、2 = A(阳极)—— usbc-ldo 那块第一版就接反过,这里写死脚名
add("R7", "Device", "R", 226, 110, "1k", R0402, {"1": "LED_USER", "2": "LED_USER_A"})
add("D2", "Device", "LED", 226, 128, "BLUE", LED0805, {"2": "LED_USER_A", "1": "GND"})
add("R8", "Device", "R", 82, 110, "1k", R0402, {"1": "+3V3", "2": "LED_PWR_A"})
add("D3", "Device", "LED", 82, 128, "GREEN", LED0805, {"2": "LED_PWR_A", "1": "GND"})

# ── 排针 ───────────────────────────────────────────────────────────────
add("J2", "Connector_Generic", "Conn_01x08", 250, 90, "IO",
    "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical", {
        "1": "+3V3", "2": "GND", "3": "TXD", "4": "RXD",
        "5": "IO4", "6": "IO5", "7": "IO6", "8": "IO7",
    })

# ── 写出前自检 ─────────────────────────────────────────────────────────
bad = s.crossing_pins() + s.overlapping_wires()
if bad:
    print(f"!! 自检失败 {len(bad)} 项,拒绝写出:")
    for b in bad:
        print("   ", b)
    raise SystemExit(1)

(HERE.parent / "expected_nets.json").write_text(
    json.dumps(EXPECTED, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
out = HERE.parent / "esp32c3.kicad_sch"
out.write_text(s.render(), encoding="utf-8", newline="\n")
print(f"wrote {out.name}: {len(s.parts)} parts, {len(s.labels)} labels")
