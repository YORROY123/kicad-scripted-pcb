"""CM5 載板用到、KiCad 10 內建庫沒有的 IC 符號 → ../symbols/CM5_Parts.kicad_sym

    python parts_sym.py

每顆 IC 的腳位表照抄規格書的 Pin Functions 表(出處寫在各表旁邊)。腳號 = 封裝焊盤號;
裸露焊盤另給一個腳號(KiCad 封裝的 EP 焊盤號),否則 PCB 上 EP 不會接地。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "symbols" / "CM5_Parts.kicad_sym"
P = 2.54

# (腳號, 腳名, 電氣類型, 邊 L/R/B, 該邊第幾格)
# TI LM5146 規格書 ZHCSLJ7A 表 6-1(VQFN-20 RGY)。21 = 封裝 Texas_RGY_R-PVQFN-N20 的 EP 焊盤
LM5146 = dict(
    name="LM5146", ref="U", half_w=12.7, rows=8,
    footprint="Package_DFN_QFN:Texas_RGY_R-PVQFN-N20_EP2.05x3.05mm",
    datasheet="https://www.ti.com/lit/ds/symlink/lm5146.pdf",
    desc="100V synchronous buck controller, external MOSFETs, VQFN-20",
    pins=[
        ("20", "VIN", "power_in", "L", 0),
        ("1", "EN/UVLO", "input", "L", 1),
        ("2", "RT", "passive", "L", 2),
        ("3", "SS/TRK", "passive", "L", 3),
        ("4", "COMP", "output", "L", 4),
        ("5", "FB", "input", "L", 5),
        ("8", "SYNCIN", "input", "L", 6),
        ("7", "SYNCOUT", "output", "L", 7),
        ("17", "BST", "passive", "R", 0),
        ("18", "HO", "output", "R", 1),
        ("19", "SW", "passive", "R", 2),
        ("13", "LO", "output", "R", 3),
        ("11", "ILIM", "passive", "R", 4),
        ("14", "VCC", "power_out", "R", 5),
        ("10", "PGOOD", "open_collector", "R", 6),
        ("6", "AGND", "power_in", "B", 0),
        ("12", "PGND", "power_in", "B", 1),
        ("15", "EP", "passive", "B", 2),
        ("21", "EP", "passive", "B", 3),
        ("9", "NC", "no_connect", "B", 4),
        ("16", "NC", "no_connect", "B", 5),
    ],
)

# Hanrun HR911130A 規格書(LCSC C54408)第 1 頁 Schematics;SH = 兩支屏蔽卡腳(封裝焊盤號 SH)
HR911130A = dict(
    name="HR911130A", ref="J", half_w=10.16, rows=9,
    footprint="CM5:RJ45_Hanrun_HR911130A_Horizontal",
    datasheet="https://www.lcsc.com/product-detail/C54408.html",
    desc="RJ45 with 1000Base-T magnetics and green/yellow LEDs",
    pins=[
        ("2", "MDI0+", "passive", "L", 0),
        ("3", "MDI0-", "passive", "L", 1),
        ("4", "MDI1+", "passive", "L", 2),
        ("7", "MDI1-", "passive", "L", 3),
        ("5", "MDI2+", "passive", "L", 4),
        ("6", "MDI2-", "passive", "L", 5),
        ("8", "MDI3+", "passive", "L", 6),
        ("9", "MDI3-", "passive", "L", 7),
        ("1", "CT", "passive", "L", 8),
        ("11", "LEDG_A", "passive", "R", 0),
        ("12", "LEDG_K", "passive", "R", 1),
        ("14", "LEDY_A", "passive", "R", 3),
        ("13", "LEDY_K", "passive", "R", 4),
        ("10", "CHS", "passive", "B", 0),
        ("SH", "SHIELD", "passive", "B", 1),
    ],
)

# Microchip LAN7800 規格書 DS00001992H 圖 3-1(48-SQFN 7×7,Y9X)。49 = 封裝 EP(VSS)
# LED0/LED1 與 EEPROM 共用腳(EEDO/EECLK);本板不接 EEPROM(MAC 存 OTP),兩腳當 LED。
# LED 腳預設低電位有效、開汲極(9.3 LED Interface)→ open_collector,review.py 才算得出電流。
LAN7800 = dict(
    name="LAN7800", ref="U", half_w=15.24, rows=27,
    footprint="Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm",
    datasheet="https://ww1.microchip.com/downloads/aemDocuments/documents/UNG/ProductDocuments/DataSheets/LAN7800-Data-Sheet-DS00001992H.pdf",
    desc="USB 3.1 Gen 1 to 10/100/1000 Ethernet bridge, 48-SQFN 7x7",
    pins=[
        ("46", "VDD33_REG_IN", "power_in", "L", 0),
        ("14", "VDD_SW_IN", "power_in", "L", 1),
        ("38", "VDD33A", "power_in", "L", 2),
        ("20", "VDDVARIO", "power_in", "L", 3),
        ("36", "VDDVARIO", "power_in", "L", 4),
        ("39", "VDDVARIO", "power_in", "L", 5),
        ("45", "VDD25_REG_OUT", "power_out", "L", 7),
        ("3", "VDD25A", "power_in", "L", 8),
        ("6", "VDD25A", "power_in", "L", 9),
        ("9", "VDD25A", "power_in", "L", 10),
        ("12", "VDD25A", "power_in", "L", 11),
        ("13", "VDD12_SW_OUT", "passive", "L", 13),
        ("15", "VDD12_SW_FB", "passive", "L", 14),
        ("21", "VDD12CORE", "power_in", "L", 15),
        ("42", "VDD12CORE", "power_in", "L", 16),
        ("25", "VDD12A", "power_in", "L", 17),
        ("30", "VDD12A", "power_in", "L", 18),
        ("44", "VDD12A", "power_in", "L", 19),
        ("47", "REF_REXT", "passive", "L", 21),
        ("48", "REF_FILT", "passive", "L", 22),
        ("37", "USBRBIAS", "passive", "L", 23),
        ("40", "XI", "passive", "L", 25),
        ("41", "XO", "passive", "L", 26),
        ("1", "TR0P", "passive", "R", 0),
        ("2", "TR0N", "passive", "R", 1),
        ("4", "TR1P", "passive", "R", 2),
        ("5", "TR1N", "passive", "R", 3),
        ("7", "TR2P", "passive", "R", 4),
        ("8", "TR2N", "passive", "R", 5),
        ("10", "TR3P", "passive", "R", 6),
        ("11", "TR3N", "passive", "R", 7),
        ("26", "USB2_DP", "passive", "R", 9),
        ("27", "USB2_DM", "passive", "R", 10),
        ("28", "USB3_TXDP", "passive", "R", 11),
        ("29", "USB3_TXDM", "passive", "R", 12),
        ("31", "USB3_RXDP", "passive", "R", 13),
        ("32", "USB3_RXDM", "passive", "R", 14),
        ("23", "VBUS_DET", "input", "R", 16),
        ("35", "RESET_N/PME_CLEAR", "input", "R", 17),
        ("34", "TEST", "input", "R", 18),
        ("16", "EECS/GPIO0", "passive", "R", 19),
        ("17", "EEDI/GPIO1", "passive", "R", 20),
        ("18", "EEDO/LED0/GPIO2", "open_collector", "R", 21),
        ("19", "EECLK/LED1/GPIO3", "open_collector", "R", 22),
        ("24", "SUSPEND_N/LED2/GPIO5", "passive", "R", 23),
        ("33", "LED3/GPIO6", "passive", "R", 24),
        ("22", "PME_N/GPIO4", "passive", "R", 25),
        ("43", "PME_MODE/GPIO7", "passive", "R", 26),
        ("49", "VSS", "power_in", "B", 0),
    ],
)

# IC Plus IP804AR 規格書 IP804AR-DS-R02 表 1(QFN-48 7×7)。49 = 封裝 EP(接 AGND)
IP804AR = dict(
    name="IP804AR", ref="U", half_w=15.24, rows=26,
    footprint="Package_DFN_QFN:QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm",
    datasheet="https://www.lcsc.com/product-detail/C19626921.html",
    desc="4-port IEEE 802.3af/at PSE controller, integrated MOSFETs and 0.1R sense, QFN-48 7x7",
    pins=[
        ("17", "V54", "power_in", "L", 0),
        ("19", "V5", "power_out", "L", 2),
        ("22", "VPP", "power_in", "L", 3),
        ("20", "V3P3", "power_out", "L", 4),
        ("44", "DV3P3", "power_in", "L", 5),
        ("21", "V1P8", "power_out", "L", 6),
        ("24", "EnB_Reg", "input", "L", 7),
        ("45", "RstN", "input", "L", 9),
        ("13", "SCAN0", "input", "L", 10),
        ("14", "SCAN1", "input", "L", 11),
        ("28", "ALT_A/B", "input", "L", 12),
        ("29", "24V_En", "input", "L", 13),
        ("30", "4Pair_En", "input", "L", 14),
        ("23", "In_Top", "input", "L", 15),
        ("46", "AD2", "input", "L", 17),
        ("47", "AD1", "input", "L", 18),
        ("48", "AD0", "input", "L", 19),
        ("39", "SCL/EE_CLK", "bidirectional", "L", 21),
        ("41", "SDAI/EE_DAT", "bidirectional", "L", 22),
        ("40", "SDAO", "open_collector", "L", 23),
        ("42", "INTB", "open_collector", "L", 24),
        ("15", "Vrext", "no_connect", "L", 25),
        ("3", "PortN0", "passive", "R", 0),
        ("5", "PortN1", "passive", "R", 1),
        ("8", "PortN2", "passive", "R", 2),
        ("10", "PortN3", "passive", "R", 3),
        ("32", "P0", "output", "R", 5),
        ("33", "P1", "output", "R", 6),
        ("34", "P2", "output", "R", 7),
        ("35", "P3", "output", "R", 8),
        ("36", "Overload", "output", "R", 9),
        ("37", "LED_CLK", "open_collector", "R", 11),
        ("38", "LED_DAT", "open_collector", "R", 12),
        ("1", "AGND", "power_in", "B", 0),
        ("6", "AGND", "passive", "B", 1),
        ("11", "AGND", "passive", "B", 2),
        ("12", "AGND", "passive", "B", 3),
        ("25", "AGND", "passive", "B", 4),
        ("26", "AGND", "passive", "B", 5),
        ("27", "AGND", "passive", "B", 6),
        ("31", "AGND", "passive", "B", 7),
        ("43", "DGND", "passive", "B", 8),
        ("49", "EPAD", "passive", "B", 9),
        ("2", "NC", "no_connect", "B", 10),
        ("4", "NC", "no_connect", "B", 11),
        ("7", "NC", "no_connect", "B", 12),
        ("9", "NC", "no_connect", "B", 13),
        ("16", "NC", "no_connect", "B", 14),
        ("18", "NC", "no_connect", "B", 15),
    ],
)

# CND-tek G2423S 規格書(LCSC C5122139)接線圖:4 組 1CT:1CT,TD = 晶片側、MX / MCT = 纜線側
G2423S = dict(
    name="G2423S", ref="T", half_w=12.7, rows=15,
    footprint="CM5:Transformer_CNDtek_G2423S",
    datasheet="https://www.lcsc.com/product-detail/C5122139.html",
    desc="PoE+ (802.3at, 720 mA/port) 1000Base-T single port transformer, 24 pin SMD",
    pins=[(td_p, f"TD{k}+", "passive", "L", 4 * (k - 1)) for k, td_p in ((1, "23"), (2, "20"), (3, "17"), (4, "14"))]
         + [(td_n, f"TD{k}-", "passive", "L", 4 * (k - 1) + 1) for k, td_n in ((1, "22"), (2, "19"), (3, "16"), (4, "13"))]
         + [(ct, f"TCT{k}", "passive", "L", 4 * (k - 1) + 2) for k, ct in ((1, "24"), (2, "21"), (3, "18"), (4, "15"))]
         + [(mp, f"MX{k}+", "passive", "R", 4 * (k - 1)) for k, mp in ((1, "2"), (2, "5"), (3, "8"), (4, "11"))]
         + [(mn, f"MX{k}-", "passive", "R", 4 * (k - 1) + 1) for k, mn in ((1, "3"), (2, "6"), (3, "9"), (4, "12"))]
         + [(mc, f"MCT{k}", "passive", "R", 4 * (k - 1) + 2) for k, mc in ((1, "1"), (2, "4"), (3, "7"), (4, "10"))],
)

PARTS = [LM5146, HR911130A, LAN7800, IP804AR, G2423S]


def font() -> str:
    return "(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)"


def prop(key: str, val: str, x: float, y: float, hide: bool) -> str:
    h = "\n\t\t\t(hide yes)" if hide else ""
    return (f'\t\t(property "{key}" "{val}"\n\t\t\t(at {x} {y} 0)\n\t\t\t(show_name no)\n'
            f'\t\t\t(do_not_autoplace no){h}\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t)\n\t\t\t\t(justify left)\n\t\t\t)\n\t\t)\n')


def symbol(d: dict) -> str:
    hw, rows = d["half_w"], d["rows"]
    top = round((rows - 1) / 2 * P, 2)
    bot = round(-top - P, 2)                       # 本體下緣
    nums = [p[0] for p in d["pins"]]
    if len(set(nums)) != len(nums):
        raise SystemExit(f"{d['name']}: 腳號重複")
    out = [f'\t(symbol "{d["name"]}"\n\t\t(pin_names\n\t\t\t(offset 0.762)\n\t\t)\n'
           "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n"
           "\t\t(duplicate_pin_numbers_are_jumpers no)\n"]
    out.append(prop("Reference", d["ref"], -hw, round(top + 2 * P, 2), False))
    out.append(prop("Value", d["name"], -hw, round(top + P, 2), False))
    out.append(prop("Footprint", d["footprint"], 0, 0, True))
    out.append(prop("Datasheet", d["datasheet"], 0, 0, True))
    out.append(prop("Description", d["desc"], 0, 0, True))
    out.append(f'\t\t(symbol "{d["name"]}_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start {-hw} {round(top + P, 2)})\n'
               f"\t\t\t\t(end {hw} {bot})\n\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n"
               "\t\t\t\t\t(type default)\n\t\t\t\t)\n\t\t\t\t(fill\n\t\t\t\t\t(type background)\n"
               "\t\t\t\t)\n\t\t\t)\n\t\t)\n")
    out.append(f'\t\t(symbol "{d["name"]}_1_1"\n')
    nb = sum(1 for p in d["pins"] if p[3] == "B")
    for num, name, etype, side, slot in d["pins"]:
        if side == "L":
            x, y, ang = -(hw + P), round(top - slot * P, 2), 0
        elif side == "R":
            x, y, ang = hw + P, round(top - slot * P, 2), 180
        else:
            x, y, ang = round((slot - (nb - 1) / 2) * P, 2), round(bot - P, 2), 90
        hide = "\n\t\t\t\t(hide yes)" if etype == "no_connect" else ""
        out.append(f"\t\t\t(pin {etype} line\n\t\t\t\t(at {x} {y} {ang})\n\t\t\t\t(length {P}){hide}\n"
                   f'\t\t\t\t(name "{name}"\n\t\t\t\t\t{font()}\n\t\t\t\t)\n'
                   f'\t\t\t\t(number "{num}"\n\t\t\t\t\t{font()}\n\t\t\t\t)\n\t\t\t)\n')
    out.append("\t\t)\n\t\t(embedded_fonts no)\n\t)\n")
    return "".join(out)


def main() -> int:
    text = ("(kicad_symbol_lib\n\t(version 20251024)\n\t(generator \"kicad-scripted-pcb\")\n"
            + "".join(symbol(d) for d in PARTS) + ")\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name}: {', '.join(d['name'] for d in PARTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
