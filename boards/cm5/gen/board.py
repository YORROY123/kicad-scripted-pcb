"""CM5 載板原理圖(進行中)。網路標籤式:本檔就是「引腳 → 網路」對照表,同時寫出 expected_nets.json。

目前完成的區塊
  1. 54V 輸入與 5V 主電源(LM5146)
  2. 5V → 3.3V / 8A(TPS568230)
  3. CM5 連接器:電源腳、GPIO_VREF、RTC 電池、電源鍵、nRPIBOOT、電源/活動燈

──────────────── 1. 54V 輸入 → 5V / 12A ────────────────
J20 54V 輸入 → F1(4A)→ +54V。D20(SM6T68A,VRM 58.1V)跨在 +54V 對地:
  - 過壓:PoE 用的 54V 電源上限 57V(802.3at),TVS 58.1V 才開始導通,箝位 ≤ 93.6V < MOSFET/LM5146 的 100V
  - 反接:TVS 順偏導通、F1 燒斷(撬棍式)。⚠ 電源若能供很大短路電流,TVS 要撐到保險絲斷 —— 待審
+54V 同時供 PoE(IP804AR,之後的區塊),所以保險絲與 TVS 在分流之前。

LM5146 照 TI 規格書 ZHCSLJ7A 9.2.1 Design 1(48V → 5V / 12A、300kHz)改:
  - RT 33.2k → 自由振盪 300kHz(式 3;不接外部同步)
  - UVLO:R10 402k / R11 12.4k → 開 40.1V、關 36.1V(式 1、2:IHYS 10µA、VEN 1.2V)
    —— 54V 系統掉到 36V 以下就關,避免 PoE 端電壓不足時還在跑
  - FB:R14 23.2k / R15 4.42k → 0.8 ×(1 + 23.2/4.42)= 5.00V
  - 補償照原設計:R16 7.5k + C22 6.8nF、C23 150pF、R17 150Ω + C24 820pF(type III)
    ⚠ 輸出電容改 10V(原設計 6.3V),直流偏壓降容較少、實際電容較大 → 交越頻率略低,待模擬確認
  - SS:C18 47nF → 3.8ms(式 5)
  - 限流(RDS(on) 模式):Q11 BSC070N10NS5 RDS(on) 取 6.5mΩ(VGS 7.5V 估計)、ΔIL ≈ 4.6A(54V)
    → 谷值 15 − 2.3 = 12.7A,R13 = 12.7 × 6.5m / 200µA = 412Ω;C19 15pF(R × C ≈ 6ns)
  - SYNCIN 接地 = 輕載二極體模擬(DCM),CM5 待機時效率較好
  - MOSFET 用 Infineon(原設計的 onsemi 兩顆 JLC 都沒庫存):高側 BSC160N10NS3G、低側 BSC070N10NS5
  - 電感 TDK SPM10065VT-3R3M-D(原設計列的同系列),3.3µH
  - PGOOD 拉到 +5V,之後給 3.3V 降壓當致能

──────────────── 2. 5V → 3.3V / 8A ────────────────
CM5 的 CM5_3.3V 輸出每腳 300mA、共 600mA,不夠 → 另做 3.3V。負載估計:M.2 NVMe 2.5A(M.2 規範)
+ LAN7800 ×2 + USB2514B ≈ 3.5A,TPS568230(8A,TI 規格書 ZHCSIY3C)餘量足。
  - FB:R21 91k / R22 20k → 0.6 ×(1 + 91/20)= 3.33V(式 4;表 3 用 90k/20k,90k 不是標準值)
  - 表 3:3.3V @ 600kHz → L 1.5µH、COUT 66–500µF、CFF 47–330pF
    → L20 Vishay IHLP4040DZER1R5M01(1.5µH,KiCad 有封裝)、C40–C43 47µF ×4、C44 CFF 100pF
    漣波 (5 − 3.3) × 0.66 / (600k × 1.5µ) ≈ 1.25A,峰值 8.6A(8A 滿載)
  - MODE:R23 330k(VCC → MODE)/ R24 5.1k → Eco-mode、600kHz(表 1)
  - 輸入:TI 建議 VIN 40µF → C45、C46 47µF + C47 100nF;VCC 1µF(C48);BST 100nF(C49)
  - SS 空接 → 內建約 1.3ms
  - EN 由 LM5146 的 PGOOD(開汲極)經 R18 10k 拉到 CM5_3V3 驅動 →「5V 正常 且 CM5 開機」才啟動。
    CM5 規格書 3.1:5V 出現前任何腳都不能有電;關機(PMIC_Enable 拉低或軟體關機)時 CM5_3.3V
    會掉,+3V3 跟著關,掛在 +3V3 上的周邊就不會倒灌進模組(規格書第 6 章的 back-feeding 檢查)。
    官方 CM5 IO 板也是讓 CM5 控制周邊電源(M.2 的 3.3V 由 PCIE_PWR_EN 開)。
    EN 絕對最大 4V:CM5_3.3V 最高 3.465V,可直接接;VENH 最大 1.4V。
  - PGOOD 拉到 +3V3(R25 100k),之後可給 CM5 或 LAN7800 當重置條件
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import ksym  # noqa: E402

ksym.EXTRA_DIRS.append(HERE.parent / "symbols")
from netlabel import NetLabeler  # noqa: E402
from schgen import Schematic  # noqa: E402

s = Schematic(paper="A1", title="Raspberry Pi CM5 carrier")
n = NetLabeler(s)
add, flag = n.add, n.flag

R0402 = "Resistor_SMD:R_0402_1005Metric"
R0805 = "Resistor_SMD:R_0805_2012Metric"     # 150V:跨 54V 的電阻不能用 0402(50V)
# 電容值只寫容值(review.py 要能解析);耐壓由 lcsc.json 的料號決定,cap-voltage 規則會核對:
# +54V 上 100V、+5V 上 10V、VCC 16V
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"

# ── 1. 54V 輸入 ────────────────────────────────────────────────────────
add("J20", "Connector", "Screw_Terminal_01x02", 20, 20, "54V IN",
    "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    {"1": "VIN_RAW", "2": "GND"})
flag("VIN_RAW", 20, 10)
flag("GND", 26, 10)
flag("+54V", 44, 10)      # 經 F1(被動元件)才到 LM5146 的 VIN,ERC 需要知道它有供電
add("F1", "Device", "Fuse", 40, 20, "4A 63V", "Fuse:Fuse_1206_3216Metric",
    {"1": "VIN_RAW", "2": "+54V"})
# SM6T68A:1 號腳是陰極(review.py CATHODE_PIN 同系列)
add("D20", "Diode", "SM6T68A", 56, 24, "SM6T68A", "Diode_SMD:D_SMB",
    {"1": "+54V", "2": "GND"}, rot=90)
add("C10", "Device", "C_Polarized", 68, 24, "100uF", "Capacitor_THT:CP_Radial_D12.5mm_P5.00mm",
    {"1": "+54V", "2": "GND"})
for i in range(6):
    add(f"C{11 + i}", "Device", "C", 78 + 8 * i, 24, "4.7uF", C1210, {"1": "+54V", "2": "GND"})

# ── 1. LM5146 ──────────────────────────────────────────────────────────
add("U10", "CM5_Parts", "LM5146", 80, 70, "LM5146RGYR",
    "Package_DFN_QFN:Texas_RGY_R-PVQFN-N20_EP2.05x3.05mm", {
        "20": "+54V", "1": "EN_UVLO", "2": "RT", "3": "SS", "4": "COMP", "5": "FB",
        "8": "GND", "7": None, "9": None, "16": None,
        "17": "BST", "18": "HO", "19": "SW", "13": "LO", "11": "ILIM", "14": "VCC", "10": "PG_5V",
        "6": "GND", "12": "GND", "15": "GND", "21": "GND",
    })
add("C17", "Device", "C", 44, 50, "100nF", C0603, {"1": "+54V", "2": "GND"})
add("R10", "Device", "R", 36, 60, "402k", R0805, {"1": "+54V", "2": "EN_UVLO"})
add("R11", "Device", "R", 36, 76, "12.4k", R0402, {"1": "EN_UVLO", "2": "GND"})
add("R12", "Device", "R", 44, 76, "33.2k", R0402, {"1": "RT", "2": "GND"})
add("C18", "Device", "C", 52, 76, "47nF", C0402, {"1": "SS", "2": "GND"})
# 補償(type III):COMP–FB 之間 R16+C22 串聯、C23 並聯;R17+C24 跨在 RFB 上端
add("R16", "Device", "R", 36, 96, "7.5k", R0402, {"1": "COMP", "2": "COMP_RC"})
add("C22", "Device", "C", 36, 108, "6.8nF", C0402, {"1": "COMP_RC", "2": "FB"})
add("C23", "Device", "C", 46, 102, "150pF", C0402, {"1": "COMP", "2": "FB"})
add("R14", "Device", "R", 56, 96, "23.2k", R0402, {"1": "+5V", "2": "FB"})
add("R15", "Device", "R", 56, 110, "4.42k", R0402, {"1": "FB", "2": "GND"})
add("R17", "Device", "R", 66, 96, "150", R0402, {"1": "+5V", "2": "FB_FF"})
add("C24", "Device", "C", 66, 108, "820pF", C0402, {"1": "FB_FF", "2": "FB"})

add("C21", "Device", "C", 120, 52, "100nF", C0402, {"1": "BST", "2": "SW"})
add("C20", "Device", "C", 120, 92, "2.2uF", C0603, {"1": "VCC", "2": "GND"})
add("R13", "Device", "R", 130, 80, "412", R0805, {"1": "ILIM", "2": "SW"})
add("C19", "Device", "C", 138, 92, "15pF", C0402, {"1": "ILIM", "2": "GND"})
add("R18", "Device", "R", 130, 100, "10k", R0402, {"1": "CM5_3V3", "2": "PG_5V"})

# 功率級:Q10 高側(D = +54V、S = SW)、Q11 低側(D = SW、S = GND)
add("Q10", "Transistor_FET", "BSC160N10NS3G", 156, 56, "BSC160N10NS3G",
    "Package_TO_SOT_SMD:TDSON-8-1", {"5": "+54V", "4": "HO", "1": "SW", "2": "SW", "3": "SW"})
add("Q11", "Transistor_FET", "BSC070N10NS5", 156, 84, "BSC070N10NS5",
    "Package_TO_SOT_SMD:TDSON-8-1", {"5": "SW", "4": "LO", "1": "GND", "2": "GND", "3": "GND"})
add("L10", "Device", "L", 180, 70, "3.3uH SPM10065VT", "Inductor_SMD:L_Bourns_SRP1050WA",
    {"1": "SW", "2": "+5V"}, rot=90)
flag("+5V", 196, 60)      # 由電感(被動)輸出,ERC 需要知道它有供電
for i in range(5):
    add(f"C{30 + i}", "Device", "C", 200 + 8 * i, 76, "47uF", C1210, {"1": "+5V", "2": "GND"})

# ── 2. 3.3V ───────────────────────────────────────────────────────────
add("U20", "Regulator_Switching", "TPS568230", 80, 170, "TPS568230RJER",
    "Package_DFN_QFN:Texas_RJE0020A_VQFN-20-1EP_3x3mm_P0.45mm_EP0.675x0.76mm", {
        "2": "+5V", "3": "+5V", "4": "+5V", "5": "+5V",
        "1": "BST3", "6": "SW3", "19": "SW3", "20": "SW3",
        "7": "GND", "8": "GND", "18": "GND", "21": "GND", "13": "GND",
        "9": "PG_3V3", "10": None, "16": None, "11": None,
        "12": "PG_5V", "14": "FB3", "15": "MODE3", "17": "VCC3",
    })
for i, ref in enumerate(("C45", "C46")):
    add(ref, "Device", "C", 30 + 8 * i, 160, "47uF", C1210, {"1": "+5V", "2": "GND"})
add("C47", "Device", "C", 46, 160, "100nF", C0402, {"1": "+5V", "2": "GND"})
add("C48", "Device", "C", 120, 190, "1uF", C0402, {"1": "VCC3", "2": "GND"})
add("R23", "Device", "R", 130, 176, "330k", R0402, {"1": "VCC3", "2": "MODE3"})
add("R24", "Device", "R", 130, 192, "5.1k", R0402, {"1": "MODE3", "2": "GND"})
add("C49", "Device", "C", 120, 150, "100nF", C0402, {"1": "BST3", "2": "SW3"})
add("L20", "Device", "L", 160, 166, "1.5uH IHLP4040", "Inductor_SMD:L_Vishay_IHLP-4040",
    {"1": "SW3", "2": "+3V3"})
add("R21", "Device", "R", 180, 180, "91k", R0402, {"1": "+3V3", "2": "FB3"})
add("C44", "Device", "C", 190, 180, "100pF", C0402, {"1": "+3V3", "2": "FB3"})
add("R22", "Device", "R", 180, 196, "20k", R0402, {"1": "FB3", "2": "GND"})
for i in range(4):
    add(f"C{40 + i}", "Device", "C", 200 + 8 * i, 172, "47uF", C1210, {"1": "+3V3", "2": "GND"})
add("R25", "Device", "R", 140, 150, "100k", R0402, {"1": "+3V3", "2": "PG_3V3"})

# ── 3. CM5 連接器 ─────────────────────────────────────────────────────
# 腳名照 cm5_sym.NAME(規格書 4.2,--verify 200/200)。J1 = CM5 腳 1–100,J2 的焊盤 n = CM5 腳 100+n。
# 這一區只接電源與基本控制;其餘腳先打 NC,之後各區塊(網路、USB、PCIe、HDMI、40-pin)再接上。
#   CM5 規格書 4.3:GPIO_VREF 不能浮接 → CM5_3V3(GPIO 用 3.3V);EEPROM_nWP、PMIC_Enable、
#   WL/BT_nDisable 有內部上拉,不用就浮接;CM5 有 eMMC,SD 介面與 SD_PWR_ON / SD_VDD_OVERRIDE 不接;
#   CC1/CC2 是給 USB-C 供電協商用,本板 5V 來自 54V 降壓 → 不接。
#   LED 照官方 CM5 IO 板:陽極接 CM5_3.3V、經 1k 接模組的 LED 腳(LED_nPWR 規格書說要緩衝,
#   官方仍直接帶 1k,電流 ≈ 1mA)。
#   RTC:CR2032 + Keystone 3034(與官方 IO 板同款,JLC C5213768)。CM5 可對 VBAT 涓流充電,
#   預設關閉;CR2032 不可充電 → config.txt 不要設 dtparam=rtc_bbat_vchg(寫進韌體交接)。
sys.path.insert(0, str(HERE))
from cm5_sym import NAME  # noqa: E402

RAIL = {"GND": "GND", "5V": "+5V", "CM5_3.3V": "CM5_3V3", "CM5_1.8V": "CM5_1V8"}
CM5_PINS = {
    76: "VBAT", 78: "CM5_3V3",               # GPIO_VREF
    92: "PWR_BUT", 93: "nRPIBOOT", 95: "LED_nPWR", 21: "LED_nACT",
}


def cm5_map(first: int) -> dict:
    out = {}
    for pad in range(1, 101):
        pin = first + pad - 1
        out[str(pad)] = RAIL.get(NAME[pin], CM5_PINS.get(pin))
    return out


add("J1", "CM5", "CM5_J1", 300, 110, "CM5 pins 1-100", "CM5:Amphenol_10164227-1001A1RLF_2x50_P0.4mm", cm5_map(1))
add("J2", "CM5", "CM5_J2", 420, 110, "CM5 pins 101-200", "CM5:Amphenol_10164227-1001A1RLF_2x50_P0.4mm", cm5_map(101))
add("C50", "Device", "C", 280, 220, "47uF", C1210, {"1": "+5V", "2": "GND"})
add("C51", "Device", "C", 290, 220, "100nF", C0402, {"1": "+5V", "2": "GND"})
flag("VBAT", 304, 210)     # 電池是被動元件,ERC 需要知道 VBAT 有電源
add("BT50", "Device", "Battery_Cell", 304, 220, "CR2032", "Battery:BatteryHolder_Keystone_3034_1x20mm",
    {"1": "VBAT", "2": "GND"})
BUTTON = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
add("SW50", "Switch", "SW_Push", 320, 220, "POWER", BUTTON, {"1": "PWR_BUT", "2": "GND"})
add("SW51", "Switch", "SW_Push", 336, 220, "RPIBOOT", BUTTON, {"1": "nRPIBOOT", "2": "GND"})
LED0805 = "LED_SMD:LED_0805_2012Metric"
# Device:LED 是 1 = K、2 = A
add("D50", "Device", "LED", 356, 214, "RED", LED0805, {"2": "CM5_3V3", "1": "LED_PWR_K"})
add("R50", "Device", "R", 356, 228, "1k", R0402, {"1": "LED_PWR_K", "2": "LED_nPWR"})
add("D51", "Device", "LED", 372, 214, "GREEN", LED0805, {"2": "CM5_3V3", "1": "LED_ACT_K"})
add("R51", "Device", "R", 372, 228, "1k", R0402, {"1": "LED_ACT_K", "2": "LED_nACT"})

n.write(HERE.parent / "cm5.kicad_sch")
