"""Raspberry Pi Compute Module 5 的符號:兩顆 100 腳 DF40 各一個符號(CM5_J1、CM5_J2)。

KiCad 10 的 MCU_Module 只到 CM3,CM4/CM5 都沒有,所以自己畫。

腳位表照抄《Raspberry Pi Compute Module 5 datasheet》4.2 Pinout(cm5-datasheet.pdf)。
`--verify <datasheet 文字檔>` 會從 pdftotext -layout 的輸出重新解析一次,逐腳比對;
規格書不放進 repo(版權),所以預設不跑,改腳位表時一定要跑。

焊盤編號:CM5 的 1–100 腳在第一顆連接器、101–200 在第二顆。符號腳號就是焊盤號
(1–100),CM5_J2 的焊盤 n = CM5 第 100+n 腳。腳名保留規格書原名,J2 另外在名稱後面
不加註 —— 要看 CM5 腳號就 +100。
⚠ 焊盤 1 在連接器哪一端、與 CM5 腳 1 是否同一端,要對照 DF40 與 CM5 機構圖確認,
  還沒做(見 boards/cm5/README.md 的待查清單)。

用法: python cm5_sym.py [--verify cm5.txt]  → 寫 ../symbols/CM5.kicad_sym
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "symbols" / "CM5.kicad_sym"

# CM5 腳 1..200 的名稱,照規格書順序,每列 10 腳
PINOUT = """
GND GND Ethernet_Pair3_P Ethernet_Pair1_P Ethernet_Pair3_N Ethernet_Pair1_N GND GND Ethernet_Pair2_N Ethernet_Pair0_N
Ethernet_Pair2_P Ethernet_Pair0_P GND GND Ethernet_nLED3 Fan_Tacho Ethernet_nLED2 Ethernet_SYNC_OUT Fan_PWM EEPROM_nWP
LED_nACT GND GND GPIO26 GPIO21 GPIO19 GPIO20 GPIO13 GPIO16 GPIO6
GPIO12 GND GND GPIO5 ID_SC ID_SD GPIO7 GPIO11 GPIO8 GPIO9
GPIO25 GND GND GPIO10 GPIO24 GPIO22 GPIO23 GPIO27 GPIO18 GPIO17
GPIO15 GND GND GPIO4 GPIO14 GPIO3 SD_CLK GPIO2 GND GND
SD_DAT3 SD_CMD SD_DAT0 SD_DAT5 GND GND SD_DAT1 SD_DAT4 SD_DAT2 SD_DAT7
GND SD_DAT6 SD_VDD_OVERRIDE GND SD_PWR_ON VBAT 5V GPIO_VREF 5V SCL0
5V SDA0 5V CM5_3.3V 5V CM5_3.3V 5V CM5_1.8V WL_nDisable CM5_1.8V
BT_nDisable PWR_Button nRPIBOOT CC1 LED_nPWR CC2 CAM_GPIO0 GND PMIC_Enable CAM_GPIO1
USB_OTG_ID PCIe_CLK_nREQ USB_N PCIE_nWAKE USB_P PCIE_PWR_EN GND GND PCIe_nRST PCIe_CLK_P
VBUS_EN PCIe_CLK_N GND GND MIPI0_D0_N PCIe_RX_P MIPI0_D0_P PCIe_RX_N GND GND
MIPI0_D1_N PCIe_TX_P MIPI0_D1_P PCIe_TX_N GND GND MIPI0_C_N USB3-0-RX_N MIPI0_C_P USB3-0-RX_P
GND GND MIPI0_D2_N USB3-0-DP MIPI0_D2_P USB3-0-DM GND GND MIPI0_D3_N USB3-0-TX_N
MIPI0_D3_P USB3-0-TX_P HDMI1_HOTPLUG GND HDMI1_SDA HDMI1_TX2_P HDMI1_SCL HDMI1_TX2_N HDMI1_CEC GND
HDMI0_CEC HDMI1_TX1_P HDMI0_HOTPLUG HDMI1_TX1_N GND GND USB3-1-RX_N HDMI1_TX0_P USB3-1-RX_P HDMI1_TX0_N
GND GND USB3-1-DP HDMI1_CLK_P USB3-1-DM HDMI1_CLK_N GND GND USB3-1-TX_N HDMI0_TX2_P
USB3-1-TX_P HDMI0_TX2_N GND GND MIPI1_D0_N HDMI0_TX1_P MIPI1_D0_P HDMI0_TX1_N GND GND
MIPI1_D1_N HDMI0_TX0_P MIPI1_D1_P HDMI0_TX0_N GND GND MIPI1_C_N HDMI0_CLK_P MIPI1_C_P HDMI0_CLK_N
GND GND MIPI1_D2_N MIPI1_D3_N MIPI1_D2_P MIPI1_D3_P GND GND HDMI0_SDA HDMI0_SCL
""".split()
assert len(PINOUT) == 200, len(PINOUT)
NAME = {i + 1: n for i, n in enumerate(PINOUT)}


def etype(name: str) -> str:
    """ERC 用的電氣類型。電源腳照方向給,其餘一律 passive(避免 input 沒驅動的假警告)。"""
    if name in ("GND", "5V", "GPIO_VREF", "VBAT"):
        return "power_in"
    if name in ("CM5_3.3V", "CM5_1.8V"):
        return "power_out"
    return "passive"


def verify(txt: Path) -> int:
    """從規格書文字檔(pdftotext -layout -enc UTF-8)的 4.2 Pinout 重新解析,逐腳比對。"""
    lines = txt.read_text(encoding="utf-8").splitlines()
    start = next(i for i, s in enumerate(lines) if re.match(r"^\s*4\.2\. Pinout\s*$", s))
    got: dict[int, str] = {}
    for s in lines[start:start + 600]:
        m = re.match(r"^\s*(\d{1,3})\s+(\S+)\s", s + " ")
        if m and 1 <= int(m.group(1)) <= 200 and int(m.group(1)) not in got:
            got[int(m.group(1))] = m.group(2)
    bad = [n for n in range(1, 201) if got.get(n) != NAME[n]]
    for n in bad:
        print(f"  腳 {n}: 表={NAME[n]} 規格書={got.get(n)}")
    print(f"verify: {200 - len(bad)}/200 一致")
    return 1 if bad else 0


def font() -> str:
    return "(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)"


def prop(key: str, val: str, x: float, y: float, hide: bool) -> str:
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{key}" "{val}"\n\t\t\t(at {x} {y} 0)\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no){h}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t)\n\t\t\t\t(justify left)\n\t\t\t)\n\t\t)\n')


P = 2.54
HALF_W = 25.4          # 本體半寬:兩側腳名最長 17 字,約 17 mm,中間留空
ROWS = 50


def symbol(sym: str, first: int, desc: str) -> str:
    top = (ROWS - 1) / 2 * P            # 第一列 y
    body_h = top + P
    out = [f'\t(symbol "{sym}"\n\t\t(pin_names\n\t\t\t(offset 0.762)\n\t\t)\n'
           "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n"
           "\t\t(duplicate_pin_numbers_are_jumpers no)\n"]
    out.append(prop("Reference", "J", -HALF_W, round(body_h + P, 2), False))
    out.append(prop("Value", sym, 0, round(body_h + P, 2), False))
    out.append(prop("Footprint", "Connector_Hirose_DF40:Hirose_DF40C-100DS-0.4V_2x50_P0.4mm", 0, 0, True))
    out.append(prop("Datasheet", "https://datasheets.raspberrypi.com/cm5/cm5-datasheet.pdf", 0, 0, True))
    out.append(prop("Description", desc, 0, 0, True))
    out.append(f'\t\t(symbol "{sym}_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start {-HALF_W} {body_h})\n'
               f"\t\t\t\t(end {HALF_W} {-body_h})\n\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n"
               "\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n\t\t\t\t\t(type background)\n"
               "\t\t\t\t)\n\t\t\t)\n\t\t)\n")
    out.append(f'\t\t(symbol "{sym}_1_1"\n')
    for pad in range(1, 101):
        name = NAME[first + pad - 1]
        row = (pad - 1) // 2
        y = round(top - row * P, 2)
        x, ang = (-(HALF_W + P), 0) if pad % 2 else (HALF_W + P, 180)
        out.append(f"\t\t\t(pin {etype(name)} line\n\t\t\t\t(at {x} {y} {ang})\n\t\t\t\t(length {P})\n"
                   f'\t\t\t\t(name "{name}"\n\t\t\t\t\t{font()}\n\t\t\t\t)\n'
                   f'\t\t\t\t(number "{pad}"\n\t\t\t\t\t{font()}\n\t\t\t\t)\n\t\t\t)\n')
    out.append("\t\t)\n\t\t(embedded_fonts no)\n\t)\n")
    return "".join(out)


def main() -> int:
    if "--verify" in sys.argv:
        rc = verify(Path(sys.argv[sys.argv.index("--verify") + 1]))
        if rc:
            return rc
    text = ("(kicad_symbol_lib\n\t(version 20251024)\n\t(generator \"kicad-scripted-pcb\")\n"
            + symbol("CM5_J1", 1, "Raspberry Pi CM5, connector 1 (CM5 pins 1-100)")
            + symbol("CM5_J2", 101, "Raspberry Pi CM5, connector 2 (pad n = CM5 pin 100+n)")
            + ")\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
