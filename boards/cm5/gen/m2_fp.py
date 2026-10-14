"""M.2 M-key 插座(TE 1-2199230-6,4.2mm 高、0.5mm 腳距、67 位)封裝。

    <KiCad python> m2_fp.py [--compare <官方 CM5IO "M.2 M Key socket.kicad_mod">]
        → 寫 ../footprints/CM5.pretty/M.2_Socket_M_TE_1-2199230-6.kicad_mod

KiCad 10 只有 M.2 卡端金手指,沒有插座。尺寸取自 TE 圖面 C-2199230 rev B3(LCSC C4710843 附檔,
向量圖在樹莓派上轉圖讀出)第 3 頁 Recommended PCB Outline。
⚠ 同系列 2199230-x(不帶 1-)是 A / B / E key;JLC 搜「2199230-4」得到的是 E key,SSD 插不進去。
M key 是 1-2199230-3 … -7(第 2 頁表),本板用 -6(JLC C4710843,30µ" 金)。

座標(元件面看,原點 = 兩個定位孔連線的中點,卡往 +y 延伸):
  - 上排奇數腳:y −5.275(外緣距孔線 6.05),腳 1 在 x −9.25,每腳 +0.5 → 腳 75 在 +9.25
  - 下排偶數腳:y +2.275(外緣距孔線 3.05),腳 2 在 x −9.0 → 腳 74 在 +9.0
  - M key 拿掉 59–66(上排 34 個、下排 33 個,與圖面 34X / 33X 相符)
  - 焊墊 0.3 × 1.55;固定腳焊墊 1.2 × 2.75 在 x ±10.35、y −4.5(焊盤號 MP,接 GND)
  - 定位孔(NPTH)Ø1.1 在 x −10、Ø1.6 在 x +10
  - SSD 固定柱:2230 / 2242 / 2260 / 2280 在 y +28.25 / +40.25 / +58.25 / +78.25(卡長 − 1.75),
    Ø3.7 鍍通孔、Ø5.8 焊環(與官方 CM5 IO 板相同;用壓入式或 SMT 銅柱)
--compare 對官方 CM5 IO Board 的 M.2 封裝逐焊盤比對(官方檔無授權條款,不放進 repo)。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FP_NAME = "M.2_Socket_M_TE_1-2199230-6"
OUT = HERE.parent / "footprints" / "CM5.pretty" / f"{FP_NAME}.kicad_mod"

KEY = set(range(59, 67))
TOP_Y, BOT_Y = -5.275, 2.275
PAD = (0.3, 1.55)
PEG = [(-10.35, -4.5), (10.35, -4.5)]
PEG_SIZE = (1.2, 2.75)
NPTH = [(-10.0, 0.0, 1.1), (10.0, 0.0, 1.6)]
STANDOFF = {"2230": 28.25, "2242": 40.25, "2260": 58.25, "2280": 78.25}


def pins() -> dict[int, tuple[float, float]]:
    out = {}
    for n in range(1, 76):
        if n in KEY:
            continue
        if n % 2:
            out[n] = (round(-9.25 + (n - 1) / 2 * 0.5, 4), TOP_Y)
        else:
            out[n] = (round(-9.0 + (n - 2) / 2 * 0.5, 4), BOT_Y)
    return out


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def rect(layer, x0, y0, x1, y1, w) -> str:
    return (f'\t(fp_rect\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t)\n')


def text(key, val, y, layer, hide=False) -> str:
    h = "\n\t\t(hide yes)" if hide else ""
    return (f'\t(property "{key}" "{val}"\n\t\t(at 0 {f(y)} 0)\n\t\t(layer "{layer}"){h}\n'
            '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def smd(num, x, y, w, h) -> str:
    return (f'\t(pad "{num}" smd rect\n\t\t(at {f(x)} {f(y)})\n\t\t(size {w} {h})\n'
            '\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n\t)\n')


def footprint() -> str:
    out = [f'(footprint "{FP_NAME}"\n\t(version 20240108)\n\t(generator "kicad-scripted-pcb")\n\t(layer "F.Cu")\n'
           '\t(descr "M.2 M-key socket, TE 1-2199230-6, 0.5 mm pitch, 4.2 mm height, with 2230/2242/2260/2280 '
           'standoff holes (TE drawing C-2199230 sheet 3)")\n\t(tags "M.2 NGFF M key NVMe socket")\n']
    out.append(text("Reference", "REF**", -8.0, "F.SilkS"))
    out.append(text("Value", FP_NAME, -1.5, "F.Fab"))
    out.append(text("Datasheet", "", 0, "F.Fab", True))
    out.append(text("Description", "", 0, "F.Fab", True))
    out.append("\t(attr smd)\n")
    out.append(rect("F.Fab", -10.95, -6.6, 10.95, 3.4, 0.1))          # 外殼 21.9 寬
    out.append(rect("F.CrtYd", -11.5, -7.0, 11.5, 3.6, 0.05))
    # 卡的範圍(2280)只畫在 Fab:22 寬、卡緣從孔線往 +y 約 1.5 起算
    out.append(rect("F.Fab", -11.0, 1.5, 11.0, 81.5, 0.1))
    for n, (x, y) in pins().items():
        out.append(smd(n, x, y, *PAD))
    for x, y in PEG:
        out.append(smd("MP", x, y, *PEG_SIZE))
    for x, y, d in NPTH:
        out.append(f'\t(pad "" np_thru_hole circle\n\t\t(at {f(x)} {f(y)})\n\t\t(size {d} {d})\n\t\t(drill {d})\n'
                   '\t\t(layers "*.Cu" "*.Mask")\n\t)\n')
    for name, y in STANDOFF.items():
        out.append(f'\t(pad "MP" thru_hole circle\n\t\t(at 0 {f(y)})\n\t\t(size 5.8 5.8)\n\t\t(drill 3.7)\n'
                   '\t\t(layers "*.Cu" "*.Mask")\n\t)\n')
    out.append(")\n")
    return "".join(out)


def check() -> None:
    p = pins()
    assert sum(1 for n in p if n % 2) == 34 and sum(1 for n in p if not n % 2) == 33
    assert abs(p[75][0] - p[1][0] - 18.5) < 1e-9 and abs(p[74][0] - p[2][0] - 18.0) < 1e-9
    assert abs((-TOP_Y + PAD[1] / 2) - 6.05) < 1e-9 and abs((BOT_Y + PAD[1] / 2) - 3.05) < 1e-9


def compare(official: Path) -> int:
    import pcbnew
    fp_o = pcbnew.FootprintLoad(str(official.parent), official.stem)
    fp_m = pcbnew.FootprintLoad(str(OUT.parent), OUT.stem)

    def table(fp, holes_by_pos=False):
        d = {}
        for pad in fp.Pads():
            pos = (round(pcbnew.ToMM(pad.GetPosition().x), 3), round(pcbnew.ToMM(pad.GetPosition().y), 3))
            size = (round(pcbnew.ToMM(pad.GetSize().x), 3), round(pcbnew.ToMM(pad.GetSize().y), 3))
            num = pad.GetNumber()
            key = num if num.isdigit() else ("HOLE" if not num else "MECH") + str(pos)
            d[key] = (pos, size, pad.GetAttribute())
        return d
    a, b = table(fp_o), table(fp_m)
    sig = [k for k in a if k.isdigit()]
    bad = [k for k in sig if a[k] != b.get(k)]
    for k in bad[:8]:
        print(f"  腳 {k}: 官方 {a[k]} / 本封裝 {b.get(k)}")
    mech_a = sorted(v[0] for k, v in a.items() if not k.isdigit())
    mech_b = sorted(v[0] for k, v in b.items() if not k.isdigit())
    print(f"compare: 訊號焊盤 {len(sig) - len(bad)}/{len(sig)} 一致(位置、尺寸、類型);"
          f"機構孔 / 固定腳位置 {'一致' if mech_a == mech_b else '不一致'}"
          f"(官方定位孔 Ø1.15 / 1.65,本封裝照 TE 圖 Ø1.1 / 1.6)")
    if mech_a != mech_b:
        print("  官方", mech_a, "\n  本封裝", mech_b)
    return 1 if bad or mech_a != mech_b or len(sig) != 67 else 0


def main() -> int:
    check()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(footprint(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    if "--compare" in sys.argv:
        return compare(Path(sys.argv[sys.argv.index("--compare") + 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
