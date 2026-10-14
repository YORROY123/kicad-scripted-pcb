"""CM5 載板原理圖(進行中)。網路標籤式:本檔就是「引腳 → 網路」對照表,同時寫出 expected_nets.json。

目前完成的區塊
  1. 54V 輸入與 5V 主電源(LM5146)
  2. 5V → 3.3V / 8A(TPS568230)
  3. CM5 連接器:電源腳、GPIO_VREF、RTC 電池、電源鍵、nRPIBOOT、電源/活動燈
  4. CM5 原生 Gigabit 網口(BCM54210PE → HR911130A MagJack)
  5. USB3 → Gigabit ×2(LAN7800)
  6. 802.3at PoE ×2(IP804AR + G2423S 變壓器 + RJHSE5380 RJ45)
  7. USB 2.0:FSUSB42 切換 Hub(USB2514B → USB-A ×2)/ USB-C 燒錄口
  8. M.2 M-key(PCIe Gen2 ×1,NVMe 2230–2280)
  9. HDMI0(Type A)

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

s = Schematic(paper="A0", title="Raspberry Pi CM5 carrier")
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
    # 4. 網口(規格書 4.2:Pair0–3 直接接變壓器或 MagJack)
    12: "ETH0_P", 10: "ETH0_N", 4: "ETH1_P", 6: "ETH1_N",
    11: "ETH2_P", 9: "ETH2_N", 3: "ETH3_P", 5: "ETH3_N",
    15: "ETH_nACT", 17: "ETH_nSPD",
    # 5. USB3-0 → LAN7800 #0、USB3-1 → LAN7800 #1(CM5 的 TX 已含耦合電容,規格書 4.2)
    130: "CM5U0_RX_P", 128: "CM5U0_RX_N", 142: "LAN0_RX_P", 140: "LAN0_RX_N", 134: "LAN0_DP", 136: "LAN0_DM",
    101: "USB_OTG_ID", 103: "CM5_USB_N", 105: "CM5_USB_P",   # 7. USB 2.0
    # 9. HDMI0(HDMI1 不用,打 NC)
    170: "HDMI0_D2_P", 172: "HDMI0_D2_N", 176: "HDMI0_D1_P", 178: "HDMI0_D1_N",
    182: "HDMI0_D0_P", 184: "HDMI0_D0_N", 188: "HDMI0_CK_P", 190: "HDMI0_CK_N",
    199: "HDMI0_SDA", 200: "HDMI0_SCL", 151: "HDMI0_CEC", 153: "HDMI0_HPD",
    # 8. PCIe(PCIE_PWR_EN 不用:M.2 的 3.3V 直接取 +3V3,見區塊 8)
    102: "PCIE_nCLKREQ", 104: "PCIE_nWAKE", 109: "PCIE_nRST", 110: "PCIE_CLK_P", 112: "PCIE_CLK_N",
    116: "PCIE_RX_P", 118: "PCIE_RX_N", 122: "PCIE_TX_P", 124: "PCIE_TX_N",
    159: "CM5U1_RX_P", 157: "CM5U1_RX_N", 171: "LAN1_RX_P", 169: "LAN1_RX_N", 163: "LAN1_DP", 165: "LAN1_DM",
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
# SW51 滑動開關(區塊 7):共點 B 接地;A = FLASH(nRPIBOOT 拉低)、C = RUN(USB_OTG_ID 接地 = CM5 當 host)
add("SW51", "Switch", "SW_SPDT", 336, 220, "FLASH/RUN", "Button_Switch_SMD:SW_SPDT_PCM12",
    {"2": "GND", "1": "nRPIBOOT", "3": "USB_OTG_ID"})
LED0805 = "LED_SMD:LED_0805_2012Metric"
# Device:LED 是 1 = K、2 = A
add("D50", "Device", "LED", 356, 214, "RED", LED0805, {"2": "CM5_3V3", "1": "LED_PWR_K"})
add("R50", "Device", "R", 356, 228, "1k", R0402, {"1": "LED_PWR_K", "2": "LED_nPWR"})
add("D51", "Device", "LED", 372, 214, "GREEN", LED0805, {"2": "CM5_3V3", "1": "LED_ACT_K"})
add("R51", "Device", "R", 372, 228, "1k", R0402, {"1": "LED_ACT_K", "2": "LED_nACT"})

# ── 4. 原生 Gigabit 網口 ───────────────────────────────────────────────
# 照官方 CM5 IO 板(rev 2 KiCad 檔):Pair0–3 直接接 MagJack,每兩對一顆 TPD4EUSB30 ESD
# (直通式:1↔10、2↔9、4↔7、5↔6 接同一條線,走線從腳下穿過);晶片側中心抽頭 100nF 對地。
# MagJack:Hanrun HR911130A(JLC C54408)。10 腳經內部 1000pF/2kV 接纜線側 75Ω 終端 → 接 GND;
# 屏蔽卡腳也接 GND(本板不另分機殼地)。
# LED(規格書 4.2):nLED3 = 活動燈(綠)、nLED2 = 速度燈(黃,1G / 100M 連線時亮),
# 開汲極 IOL 8mA @ VOL < 0.4V;照官方 IO 板 470Ω,陽極接 CM5_3V3(約 2mA)。
add("J30", "CM5_Parts", "HR911130A", 560, 110, "HR911130A", "CM5:RJ45_Hanrun_HR911130A_Horizontal", {
    "2": "ETH0_P", "3": "ETH0_N", "4": "ETH1_P", "7": "ETH1_N",
    "5": "ETH2_P", "6": "ETH2_N", "8": "ETH3_P", "9": "ETH3_N",
    "1": "ETH_CT", "10": "GND", "SH": "GND",
    "11": "CM5_3V3", "12": "ETH_LEDG_K", "14": "CM5_3V3", "13": "ETH_LEDY_K",
})
add("C60", "Device", "C", 530, 150, "100nF", C0402, {"1": "ETH_CT", "2": "GND"})
for ref, x, (a_p, a_n), (b_p, b_n) in (("U30", 520, ("ETH1_P", "ETH1_N"), ("ETH0_N", "ETH0_P")),
                                      ("U31", 520, ("ETH3_P", "ETH3_N"), ("ETH2_N", "ETH2_P"))):
    add(ref, "Power_Protection", "TPD4EUSB30", x, 80 if ref == "U30" else 120, "TPD4EUSB30",
        "Package_SON:USON-10_2.5x1.0mm_P0.5mm", {
            "1": a_p, "10": a_p, "2": a_n, "9": a_n, "4": b_p, "7": b_p, "5": b_n, "6": b_n,
            "3": "GND", "8": "GND"})
add("R60", "Device", "R", 600, 100, "470", R0402, {"1": "ETH_LEDG_K", "2": "ETH_nACT"})
add("R61", "Device", "R", 600, 116, "470", R0402, {"1": "ETH_LEDY_K", "2": "ETH_nSPD"})

# ── 5. USB3 → Gigabit ×2(LAN7800)──────────────────────────────────────
# Microchip LAN7800 規格書 DS00001992H(以下簡稱規格書):
#   - 電源(第 4 章圖 4-1):3.3V 腳全接 +3V3(VDDVARIO 也用 3.3V,I/O 為 3.3V);
#     內建 1.2V 降壓:VDD12_SW_OUT → 3.3µH → 1.2V 網,VDD12_SW_FB 接 1.2V 網,10µF;
#     內建 2.5V LDO:VDD25_REG_OUT 1µF,供四支 VDD25A。工作範圍 16.2:3.3V 腳 2.97–3.63V。
#     每顆約 256mA(16.4,最大工作模式),兩顆約 0.5A,由 +3V3(8A)供。
#   - REF_REXT 2k 1%、REF_FILT 1µF、USBRBIAS 12k 1%(表 3-2)。
#   - 25MHz 晶振(16.7):總誤差 ±45ppm 內 → Yangxing X322525MSB4SI(C13740,±10 + ±20ppm、
#     ESR 50Ω、CL 20pF);負載電容 2 ×(20 − 雜散約 5)≈ 30pF → 27pF。實物要量頻率。
#   - USB3:LAN7800 的 TX 要加 100nF 耦合電容(USB 3 規範 75–265nF,放在發送端);
#     CM5 的 TX 已含電容,直接接 LAN7800 RX。USB2(DP/DM)也要接,USB3 列舉要靠它。
#   - VBUS_DET 接 3.3V(表 3-2:bus-powered 接 VDD33A);RESET_N 接 PG_3V3(+3V3 正常才放開);
#     TEST 接地;不接 EEPROM:MAC 寫進晶片 OTP(Linux lan78xx 可用 ethtool -E 寫),
#     EEDI 10k 下拉讓 EEPROM 偵測讀到 00(不是 A5h);PME_MODE 10k 下拉;其餘 GPIO 不接。
#   - LED0 / LED1(與 EECLK/EEDO 共用)預設低電位有效 → 綠 / 黃燈經 470Ω,陽極接 +3V3。
#     ⚠ 沒有 EEPROM/OTP 設定時 LED 腳是否預設啟用,要看 lan78xx 驅動(寫進待確認)。
#   - 庫存風險:LAN7800/Y9X(C633489)JLC 只剩 89 顆,打樣足夠;量產前要另找料源。
flag("+3V3", 40, 260)      # 由電感(被動)輸出,LAN7800 的 3.3V 電源腳需要 ERC 知道它有供電
C0805 = "Capacitor_SMD:C_0805_2012Metric"


def lan7800(i: int, x: float, y: float) -> None:
    u, ref = f"LAN{i}", lambda base: base + 30 * i   # LAN0 用 1xx–121、LAN1 用 130–151
    add(f"U{40 + i}", "CM5_Parts", "LAN7800", x, y, "LAN7800/Y9X",
        "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm", {
            "46": "+3V3", "14": "+3V3", "38": "+3V3", "20": "+3V3", "36": "+3V3", "39": "+3V3",
            "45": f"{u}_2V5", "3": f"{u}_2V5", "6": f"{u}_2V5", "9": f"{u}_2V5", "12": f"{u}_2V5",
            "13": f"{u}_SW", "15": f"{u}_1V2", "21": f"{u}_1V2", "42": f"{u}_1V2",
            "25": f"{u}_1V2", "30": f"{u}_1V2", "44": f"{u}_1V2",
            "47": f"{u}_REXT", "48": f"{u}_FILT", "37": f"{u}_RBIAS", "40": f"{u}_XI", "41": f"{u}_XO",
            # MDI → 區塊 6 的 PoE 變壓器
            "1": f"{u}_TR0P", "2": f"{u}_TR0N", "4": f"{u}_TR1P", "5": f"{u}_TR1N",
            "7": f"{u}_TR2P", "8": f"{u}_TR2N", "10": f"{u}_TR3P", "11": f"{u}_TR3N",
            "26": f"{u}_DP", "27": f"{u}_DM", "28": f"{u}_TX_P", "29": f"{u}_TX_N",
            "31": f"{u}_RX_P", "32": f"{u}_RX_N",
            "23": "+3V3", "35": "PG_3V3", "34": "GND", "16": None, "17": f"{u}_EEDI",
            "18": f"{u}_LEDG_K", "19": f"{u}_LEDY_K", "24": None, "33": None, "22": None,
            "43": f"{u}_PMEMODE", "49": "GND",
        })
    flag(f"{u}_1V2", x - 40, y + 10)          # 1.2V 由電感輸出
    cx = x - 60
    for k, (net, val, fp) in enumerate([("+3V3", "10uF", C0805)] + [("+3V3", "100nF", C0402)] * 4
                                       + [(f"{u}_2V5", "1uF", C0402)] + [(f"{u}_2V5", "100nF", C0402)] * 4
                                       + [(f"{u}_1V2", "10uF", C0805)] + [(f"{u}_1V2", "100nF", C0402)] * 5):
        add(f"C{ref(100) + k}", "Device", "C", cx + 7 * (k % 8), y - 40 + 14 * (k // 8), val, fp,
            {"1": net, "2": "GND"})
    add(f"L{40 + i}", "Device", "L", cx, y + 30, "3.3uH", "Inductor_SMD:L_1008_2520Metric",
        {"1": f"{u}_SW", "2": f"{u}_1V2"})
    add(f"R{ref(100)}", "Device", "R", cx + 10, y + 30, "2k", R0402, {"1": f"{u}_REXT", "2": "GND"})
    add(f"C{ref(117)}", "Device", "C", cx + 18, y + 30, "1uF", C0402, {"1": f"{u}_FILT", "2": "GND"})
    add(f"R{ref(101)}", "Device", "R", cx + 26, y + 30, "12k", R0402, {"1": f"{u}_RBIAS", "2": "GND"})
    add(f"Y{40 + i}", "Device", "Crystal_GND24", cx + 10, y + 46, "25MHz",
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        {"1": f"{u}_XI", "3": f"{u}_XO", "2": "GND", "4": "GND"})
    add(f"C{ref(118)}", "Device", "C", cx, y + 56, "27pF", C0402, {"1": f"{u}_XI", "2": "GND"})
    add(f"C{ref(119)}", "Device", "C", cx + 20, y + 56, "27pF", C0402, {"1": f"{u}_XO", "2": "GND"})
    add(f"R{ref(102)}", "Device", "R", x + 40, y + 20, "10k", R0402, {"1": f"{u}_EEDI", "2": "GND"})
    add(f"R{ref(103)}", "Device", "R", x + 48, y + 20, "10k", R0402, {"1": f"{u}_PMEMODE", "2": "GND"})
    add(f"C{ref(120)}", "Device", "C", x + 40, y - 6, "100nF", C0402, {"1": f"{u}_TX_P", "2": f"CM5U{i}_RX_P"})
    add(f"C{ref(121)}", "Device", "C", x + 48, y - 6, "100nF", C0402, {"1": f"{u}_TX_N", "2": f"CM5U{i}_RX_N"})
    add(f"D{40 + 2 * i}", "Device", "LED", x + 60, y + 14, "GREEN", LED0805, {"2": "+3V3", "1": f"{u}_LEDG_K2"})
    add(f"R{ref(104)}", "Device", "R", x + 60, y + 28, "470", R0402, {"1": f"{u}_LEDG_K2", "2": f"{u}_LEDG_K"})
    add(f"D{41 + 2 * i}", "Device", "LED", x + 78, y + 14, "YELLOW", LED0805, {"2": "+3V3", "1": f"{u}_LEDY_K2"})
    add(f"R{ref(105)}", "Device", "R", x + 78, y + 28, "470", R0402, {"1": f"{u}_LEDY_K2", "2": f"{u}_LEDY_K"})


lan7800(0, 140, 290)
lan7800(1, 140, 400)

# ── 6. 802.3at PoE ×2 ─────────────────────────────────────────────────
# IC Plus IP804AR(規格書 IP804AR-DS-R02,JLC C19626921):4 埠 PSE,MOSFET 與 0.1Ω 取樣內建。
#   V54 是各埠共同的正端,PortNx 是開關後的負端(第 2 章應用圖:V54 → 保險絲 → 變壓器中心抽頭,
#   PortNx → 另一組中心抽頭,埠上並 TVS 與電容)。本板用 Port0、Port1,Port2/3 不接。
#   - 自動模式、不帶 MCU:SCAN0/SCAN1 = 0(表 2);LED 序列輸出關閉:LED_CLK / LED_DAT 下拉,
#     AD2 不論(表 2 LED Disable 欄);AD0–AD2 接地。沒有 EEPROM:SCL / SDAI 上拉,讀到的
#     第 0 位元組不是 0x5A → 用預設值(5.4);預設每埠 at 模式(0x25 = 0xF)。
#   - ALT_A/B = 0(Alternative A)、24V_En = 0、4Pair_En = 0,開機鎖存(表 1)。
#   - 電源:V54 1µF + 47µF/100V;V5、V3P3、V1P8、DV3P3 各 4.7µF;VPP 接 V5;EnB_Reg 接地
#     (用內建 3.3V);V3P3 與 DV3P3 相接;In_Top 接地;RstN 10k 上拉 + 100nF。
#   - V54 at 模式要 50–57V(7.2)→ 宣告在 rails.json,review.py 檢查。
#     ⚠ LM5146 的 UVLO 是 40V:輸入在 40–50V 時 CM5 照常開機,但 PoE 可能不供電(或只能 af)。
# 埠的接法(Alternative A、MDI-X 極性,IEEE 802.3 表 33-2):RJ45 3/6 = 正(V54)、1/2 = 負(PortN)。
#   PD 端有整流橋,兩種極性都可以;⚠ 極性與 Alternative 選擇要由懂 PoE 的人審。
#   G2423S(JLC C5122139,每埠 720mA ≥ IP804AR at 的 Icut 640mA):第 k 組 TDk 接 LAN7800 TR(k−1),
#   MXk 接 RJ45 的第 k 對(1/2、3/6、4/5、7/8)。MCT1 → PortN、MCT2 → 保險絲 → V54;
#   不供電的 MCT3、MCT4 各經 75Ω 到共用點、1000pF/2kV 對地(Bob Smith 終端)。
#   晶片側中心抽頭 TCT 各 100nF 對地(LAN7800 規格書:中心抽頭不加電壓)。
#   每埠:保險絲 1.5A(Ilim 最大 920mA)、TVS SM6T68A(VRM 58.1V)與 100nF/100V 跨在埠的正負之間。
#     ⚠ SM6T68A 箝位最高約 92V,超過 IP804AR 絕對最大 75V —— TI 等 PSE 參考設計也用 58V 級 TVS,待審。
#   RJ45:Amphenol RJHSE5380(屏蔽、無變壓器、無燈,JLC C464586),屏蔽接 GND。
C1206 = "Capacitor_SMD:C_1206_3216Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
add("U50", "CM5_Parts", "IP804AR", 360, 300, "IP804AR", "Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm", {
    "17": "+54V", "19": "IP_5V", "22": "IP_5V", "20": "IP_3V3", "44": "IP_3V3", "21": "IP_1V8",
    "24": "GND", "45": "IP_RSTN", "13": "GND", "14": "GND", "28": "GND", "29": "GND", "30": "GND",
    "23": "GND", "46": "GND", "47": "GND", "48": "GND",
    "39": "IP_SCL", "41": "IP_SDA", "40": None, "42": None, "15": None,
    "3": "POE0_N", "5": "POE1_N", "8": None, "10": None,
    "32": None, "33": None, "34": None, "35": None, "36": None,
    "37": "IP_LEDCLK", "38": "IP_LEDDAT",
    "1": "GND", "6": "GND", "11": "GND", "12": "GND", "25": "GND", "26": "GND", "27": "GND", "31": "GND",
    "43": "GND", "49": "GND", "2": None, "4": None, "7": None, "9": None, "16": None, "18": None,
})
for k, (ref, net, val, fp) in enumerate([("C82", "+54V", "1uF", C1206), ("C83", "+54V", "47uF", "Capacitor_SMD:CP_Elec_10x10"),
                                         ("C84", "IP_5V", "4.7uF", C0603), ("C85", "IP_3V3", "4.7uF", C0603),
                                         ("C86", "IP_3V3", "4.7uF", C0603), ("C87", "IP_1V8", "4.7uF", C0603),
                                         ("C88", "IP_RSTN", "100nF", C0402)]):
    add(ref, "Device", "C_Polarized" if ref == "C83" else "C", 300 + 9 * k, 370, val, fp, {"1": net, "2": "GND"})
for k, (ref, a, b) in enumerate([("R74", "IP_3V3", "IP_RSTN"), ("R75", "IP_3V3", "IP_SCL"), ("R76", "IP_3V3", "IP_SDA"),
                                 ("R77", "IP_LEDCLK", "GND"), ("R78", "IP_LEDDAT", "GND")]):
    add(ref, "Device", "R", 300 + 9 * k, 395, "10k", R0402, {"1": a, "2": b})


def poe_port(i: int, x: float, y: float) -> None:
    u, p = f"LAN{i}", f"POE{i}"
    add(f"T4{i}", "CM5_Parts", "G2423S", x, y, "G2423S", "CM5:Transformer_CNDtek_G2423S", {
        "23": f"{u}_TR0P", "22": f"{u}_TR0N", "24": f"{p}_TCT1",
        "20": f"{u}_TR1P", "19": f"{u}_TR1N", "21": f"{p}_TCT2",
        "17": f"{u}_TR2P", "16": f"{u}_TR2N", "18": f"{p}_TCT3",
        "14": f"{u}_TR3P", "13": f"{u}_TR3N", "15": f"{p}_TCT4",
        "2": f"{p}_A_P", "3": f"{p}_A_N", "1": f"{p}_N",           # RJ45 1/2:負
        "5": f"{p}_B_P", "6": f"{p}_B_N", "4": f"{p}_P",           # RJ45 3/6:正
        "8": f"{p}_C_P", "9": f"{p}_C_N", "7": f"{p}_CT3",         # RJ45 4/5:不供電
        "11": f"{p}_D_P", "12": f"{p}_D_N", "10": f"{p}_CT4",      # RJ45 7/8:不供電
    })
    add(f"J4{i}", "Connector", "RJ45_Shielded", x + 60, y, f"POE{i}", "Connector_RJ:RJ45_Amphenol_RJHSE5380", {
        "1": f"{p}_A_P", "2": f"{p}_A_N", "3": f"{p}_B_P", "6": f"{p}_B_N",
        "4": f"{p}_C_P", "5": f"{p}_C_N", "7": f"{p}_D_P", "8": f"{p}_D_N", "SH": "GND",
    })
    for k in range(4):
        add(f"C{70 + 4 * i + k}", "Device", "C", x - 50 + 8 * k, y + 40, "100nF", C0402,
            {"1": f"{p}_TCT{k + 1}", "2": "GND"})
    add(f"R{80 + 2 * i}", "Device", "R", x + 20, y + 40, "75", R0603, {"1": f"{p}_CT3", "2": f"{p}_BOB"})
    add(f"R{81 + 2 * i}", "Device", "R", x + 28, y + 40, "75", R0603, {"1": f"{p}_CT4", "2": f"{p}_BOB"})
    add(f"C{90 + i}", "Device", "C", x + 36, y + 40, "1nF 2kV", C1206, {"1": f"{p}_BOB", "2": "GND"})
    add(f"F4{i}", "Device", "Fuse", x + 30, y - 40, "1.5A", "Fuse:Fuse_1206_3216Metric", {"1": "+54V", "2": f"{p}_P"})
    # SM6T68A:1 號腳是陰極(review.py CATHODE_PIN)
    add(f"D6{i}", "Diode", "SM6T68A", x + 44, y - 30, "SM6T68A", "Diode_SMD:D_SMB", {"1": f"{p}_P", "2": f"{p}_N"}, rot=90)
    add(f"C{92 + i}", "Device", "C", x + 54, y - 30, "100nF", "Capacitor_SMD:C_0805_2012Metric",
        {"1": f"{p}_P", "2": f"{p}_N"})


poe_port(0, 500, 300)
poe_port(1, 500, 420)

# ── 7. USB 2.0:Hub ×2 埠 / USB-C 燒錄口 ────────────────────────────────
# CM5 規格書 4.2:USB_P/USB_N(105/103)是唯一的 USB 2.0;USB_OTG_ID(101)內部上拉 = device,
#   接地 = host(OS 也要設定:config.txt dtoverlay=dwc2,dr_mode=host,寫進韌體交接)。
# 切換:SW51 一顆滑動開關同時決定兩件事,不會有「按鈕放開就切回 Hub」的問題:
#   FLASH:nRPIBOOT 低 → CM5 進 rpiboot(上電 2ms 內要低,滑動開關一直保持);OTG_ID 浮接 = device;
#          FSUSB42 Sel = nRPIBOOT = 低 → D± 接 HSD1 = USB-C 燒錄口
#   RUN:  nRPIBOOT 由 CM5 內部 10k 拉到 CM5_3.3V = 高 → Sel 高 → HSD2 = Hub 上行;OTG_ID 接地 = host
#   FSUSB42(Fairchild 規格書真值表:/OE 低導通,Sel 低 HSD1、高 HSD2)電源接 CM5_3V3:與 nRPIBOOT
#   同電源域,CM5 未開機時兩者都 0V,不會倒灌。/OE 接地。JLC C11355。
# USB-C 燒錄口:CC1/CC2 各 5.1k 下拉(device);VBUS 來自電腦,只接 ESD 的參考腳,不進本板 5V。
#   CM5 的 CC1/CC2(94/96,給 USB-C 供電協商用)不接:本板 5V 來自 54V。
# Hub:Microchip USB2514B(規格書 USB251xB/xBi Rev 2.2,JLC C16251)
#   - CFG_SEL[1:0] = 00(表 5.1:預設設定、自供電、各埠獨立電源開關與過流偵測)→ 兩腳 100k 下拉;
#     NON_REM1(SDA)100k 下拉,NON_REM0(SUSP_IND)用內部下拉 → 全部埠可拔除。
#   - 只用 DN1、DN2;DN3、DN4 的 DP/DM 各 10k 上拉 3.3V = 埠停用(3.3 節)。
#   - VBUS_DET:永久連接 host 的自供電 hub 接 3.3V(3.3 節)→ +3V3;RESET_N 接 PG_3V3。
#   - RBIAS 12k 1%;CRFILT / PLLFILT 各 100nF(上限 0.1µF);24MHz 晶振 C15643 + 1M 並聯 + 27pF ×2(7.1)。
#   - PRTPWRx(高 = 開)→ AP2171W EN(1A,JLC C110466);FLG(開汲極)→ OCS_Nx,10k 上拉。
#     BC_EN strap 用內部下拉 = 不支援充電協議。每埠 VBUS 100µF + 100nF(USB 2.0 下游 ≥ 120µF/hub)。
#   - 每個 USB 接頭一顆 USBLC6-2SC6(穿過式,VBUS 參考腳接該埠 VBUS)。
add("U60", "Interface_USB", "FSUSB42MUX", 500, 205, "FSUSB42MUX", "Package_SO:MSOP-10_3x3mm_P0.5mm", {
    "1": "CM5_3V3", "5": "GND", "10": "GND", "2": "nRPIBOOT",
    "3": "CM5_USB_P", "4": "CM5_USB_N",
    "7": "USBC_DP", "6": "USBC_DN", "9": "HUB_UP_DP", "8": "HUB_UP_DN",
})
add("C200", "Device", "C", 486, 190, "100nF", C0402, {"1": "CM5_3V3", "2": "GND"})
add("J50", "Connector", "USB_C_Receptacle_USB2.0_16P", 455, 225, "USB-C FLASH",
    "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
        "A4": "USBC_VBUS", "A9": "USBC_VBUS", "B4": "USBC_VBUS", "B9": "USBC_VBUS",
        "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "SH": "GND",
        "A5": "USBC_CC1", "B5": "USBC_CC2",
        "A6": "USBC_DP", "B6": "USBC_DP", "A7": "USBC_DN", "B7": "USBC_DN",
        "A8": None, "B8": None,
    })
add("R200", "Device", "R", 478, 246, "5.1k", R0402, {"1": "USBC_CC1", "2": "GND"})
add("R201", "Device", "R", 486, 246, "5.1k", R0402, {"1": "USBC_CC2", "2": "GND"})
USBLC6 = ("Power_Protection", "USBLC6-2SC6")


def usblc6(ref, x, y, dp, dn, vbus):
    add(ref, *USBLC6, x, y, "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
        {"1": dp, "6": dp, "3": dn, "4": dn, "5": vbus, "2": "GND"})


usblc6("D70", 470, 175, "USBC_DP", "USBC_DN", "USBC_VBUS")
add("U61", "Interface_USB", "USB2514B_Bi", 560, 205, "USB2514B", "Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP3.7x3.7mm", {
    "30": "HUB_UP_DN", "31": "HUB_UP_DP",
    "1": "USBA0_DN", "2": "USBA0_DP", "3": "USBA1_DN", "4": "USBA1_DP",
    "6": "HUB_DIS3", "7": "HUB_DIS3", "8": "HUB_DIS4", "9": "HUB_DIS4",
    "5": "+3V3", "10": "+3V3", "29": "+3V3", "36": "+3V3", "15": "+3V3", "23": "+3V3",
    "11": "GND", "37": "GND",
    "12": "USBA0_EN", "13": "USBA0_OCN", "16": "USBA1_EN", "17": "USBA1_OCN",
    "18": None, "19": "HUB_OCN34", "20": None, "21": "HUB_OCN34",
    "14": "HUB_CRFILT", "34": "HUB_PLLFILT", "35": "HUB_RBIAS",
    "33": "HUB_XI", "32": "HUB_XO",
    "22": "HUB_NONREM1", "24": "HUB_CFG0", "25": "HUB_CFG1",
    "26": "PG_3V3", "27": "+3V3", "28": None,
})
for k, (ref, a, b, val) in enumerate([
        ("R202", "HUB_CFG0", "GND", "100k"), ("R203", "HUB_CFG1", "GND", "100k"), ("R204", "HUB_NONREM1", "GND", "100k"),
        ("R205", "+3V3", "HUB_DIS3", "10k"), ("R206", "+3V3", "HUB_DIS4", "10k"), ("R207", "+3V3", "HUB_OCN34", "10k"),
        ("R208", "+3V3", "USBA0_OCN", "10k"), ("R209", "+3V3", "USBA1_OCN", "10k"), ("R210", "HUB_RBIAS", "GND", "12k"),
        ("R211", "HUB_XI", "HUB_XO", "1M")]):
    add(ref, "Device", "R", 520 + 8 * k, 244, val, R0402, {"1": a, "2": b})
for k, (ref, net, val, fp) in enumerate([
        ("C201", "+3V3", "4.7uF", C0603), ("C202", "+3V3", "100nF", C0402), ("C203", "+3V3", "100nF", C0402),
        ("C204", "+3V3", "100nF", C0402), ("C205", "+3V3", "100nF", C0402), ("C206", "HUB_CRFILT", "100nF", C0402),
        ("C207", "HUB_PLLFILT", "100nF", C0402), ("C208", "HUB_XI", "27pF", C0402), ("C209", "HUB_XO", "27pF", C0402)]):
    add(ref, "Device", "C", 520 + 8 * k, 257, val, fp, {"1": net, "2": "GND"})
add("Y60", "Device", "Crystal_GND24", 625, 245, "24MHz", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    {"1": "HUB_XI", "3": "HUB_XO", "2": "GND", "4": "GND"})


def usb_a(i, y):
    v = f"USBA{i}_VBUS"
    add(f"U{62 + i}", "Power_Management", "AP2171W", 600, y, "AP2171W", "Package_TO_SOT_SMD:SOT-23-5",
        {"5": "+5V", "2": "GND", "4": f"USBA{i}_EN", "3": f"USBA{i}_OCN", "1": v})
    add(f"C{210 + 3 * i}", "Device", "C", 588, y + 14, "1uF", C0402, {"1": "+5V", "2": "GND"})
    add(f"C{211 + 3 * i}", "Device", "C_Polarized", 614, y + 14, "100uF", "Capacitor_SMD:CP_Elec_6.3x7.7",
        {"1": v, "2": "GND"})
    add(f"C{212 + 3 * i}", "Device", "C", 622, y + 14, "100nF", C0402, {"1": v, "2": "GND"})
    add(f"J{51 + i}", "Connector", "USB_A", 640, y, f"USB-A {i + 1}", "Connector_USB:USB_A_Molex_48037-2200_Horizontal",
        {"1": v, "2": f"USBA{i}_DN", "3": f"USBA{i}_DP", "4": "GND", "SH": "GND"})
    usblc6(f"D{71 + i}", 628, y - 14, f"USBA{i}_DP", f"USBA{i}_DN", v)


usb_a(0, 180)
usb_a(1, 218)

# ── 8. M.2 M-key ──────────────────────────────────────────────────────
# CM5 規格書 2.3:PCIe Gen2 ×1;CM5 的 TX 已含耦合電容,NVMe 卡的 TX 也自帶(規格書明寫),
#   接插座時不用交換 TX/RX(訊號以 host 角度命名),對內 P/N 可對調。CLKREQ#、WAKE# 在 CM5 內部上拉。
# 腳位照官方 CM5 IO 板(rev 2)逐腳:41/43 → CM5 RX_P/RX_N、47/49 → TX_P/TX_N(兩者都對調了 P/N,
#   官方實際可用;PCIe 鏈結訓練會自動處理極性)、55/53 → REFCLK P/N(時脈不可對調,官方也沒對調)、
#   50 PERST#、52 CLKREQ#、54 PEWAKE#。只用 lane 0;SUSCLK、PEDET、DEVSLP、LED1# 不接。
# 3.3V:官方用一顆獨立降壓、由 PCIE_PWR_EN 開關;本板 +3V3 有 8A 且已跟著 CM5 開關機
#   → 直接接 +3V3(NVMe 最多約 2.5A),少一顆 IC;代價是 OS 不能單獨重啟 SSD 電源。
#   去耦:2 × 47µF + 100nF(M.2 規範建議靠近插座)。
# 插座:TE 1-2199230-6(M key,JLC C4710843)。⚠ 2199230-4(不帶 1-)是 E key,不能用。
add("J60", "Connector", "Bus_M.2_Socket_M", 720, 120, "M.2 M-key", "CM5:M.2_Socket_M_TE_1-2199230-6", {
    **{p: "+3V3" for p in ("2", "4", "12", "14", "16", "18", "70", "72", "74")},
    **{p: "GND" for p in ("1", "3", "9", "15", "21", "27", "33", "39", "45", "51", "57", "71", "73", "75")},
    "41": "PCIE_RX_P", "43": "PCIE_RX_N", "47": "PCIE_TX_P", "49": "PCIE_TX_N",
    "55": "PCIE_CLK_P", "53": "PCIE_CLK_N",
    "50": "PCIE_nRST", "52": "PCIE_nCLKREQ", "54": "PCIE_nWAKE",
    **{p: None for p in ("5", "7", "11", "13", "17", "19", "23", "25", "29", "31", "35", "37",
                         "10", "38", "68", "69",
                         # 插座本身的 NC 腳(M.2 規範保留)
                         "6", "8", "20", "22", "24", "26", "28", "30", "32", "34", "36", "40", "42",
                         "44", "46", "48", "56", "58", "67")},
})
for k, (ref, val, fp) in enumerate([("C220", "47uF", C1210), ("C221", "47uF", C1210), ("C222", "100nF", C0402)]):
    add(ref, "Device", "C", 690 + 8 * k, 60, val, fp, {"1": "+3V3", "2": "GND"})

# ── 9. HDMI0 ──────────────────────────────────────────────────────────
# 照官方 CM5 IO 板(rev 2):TMDS 四對、DDC(SCL/SDA)、CEC、HPD 直接接 HDMI 座,不另加 ESD 或上拉
#   (DDC 上拉與位準轉換在 CM5 內);各對的屏蔽腳(D2S/D1S/D0S/CKS)與外殼接 GND,UTILITY 不接。
# 18 腳 +5V:HDMI 規範要求 source 供 ≥ 55mA、限流 ≤ 0.5A。官方用 RT9742SNGV(固定致能);
#   本板用 TPS2051C(KiCad 有符號、JLC C129581,限流約 0.5–0.9A),EN 接 CM5_3V3 → CM5 關機時
#   不對顯示器送 5V。⚠ TPS2051C 的限流上限略高於 0.5A,實務上常見,但要確認可接受。
# 座子:Molex 208658-1001(JLC C916313)。
add("J70", "Connector", "HDMI_A", 720, 235, "HDMI", "Connector_Video:HDMI_A_Molex_208658-1001_Horizontal", {
    "1": "HDMI0_D2_P", "3": "HDMI0_D2_N", "4": "HDMI0_D1_P", "6": "HDMI0_D1_N",
    "7": "HDMI0_D0_P", "9": "HDMI0_D0_N", "10": "HDMI0_CK_P", "12": "HDMI0_CK_N",
    "2": "GND", "5": "GND", "8": "GND", "11": "GND", "17": "GND", "SH": "GND",
    "13": "HDMI0_CEC", "14": None, "15": "HDMI0_SCL", "16": "HDMI0_SDA", "18": "HDMI_5V", "19": "HDMI0_HPD",
})
add("U70", "Power_Management", "TPS2051CDBV", 670, 215, "TPS2051CDBV", "Package_TO_SOT_SMD:SOT-23-5",
    {"5": "+5V", "2": "GND", "4": "CM5_3V3", "3": None, "1": "HDMI_5V"})
add("C230", "Device", "C", 655, 232, "100nF", C0402, {"1": "+5V", "2": "GND"})
add("C231", "Device", "C", 688, 232, "100nF", C0402, {"1": "HDMI_5V", "2": "GND"})

n.write(HERE.parent / "cm5.kicad_sch")
