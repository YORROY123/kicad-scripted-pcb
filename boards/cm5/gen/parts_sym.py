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

PARTS = [LM5146, HR911130A]


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
