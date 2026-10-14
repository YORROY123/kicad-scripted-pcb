"""CND-tek G2423S(802.3at PoE+、1000Base-T 單埠變壓器,24 腳 SMD)封裝。

    python g2423s_fp.py  → 寫 ../footprints/CM5.pretty/Transformer_CNDtek_G2423S.kicad_mod

KiCad 10 沒有這顆;JLC C5122139。尺寸取自 CND-tek 規格書(LCSC C5122139)的
Recommended Land Pattern(向量圖,在樹莓派上用 pdftoppm 轉圖讀出):
  - 腳距 1.27、每排 12 腳,第 1 與第 12 腳中心距 13.97(= 11 × 1.27)
  - 焊墊寬 0.75;兩排焊墊內緣 12.70、外緣 16.50 → 焊墊長 1.90、兩排中心距 14.60
    (圖上另標「2.00 ± 0.25」,1.90 在公差內,採由內外緣算出的值,兩者才自洽)
  - 本體 17.80 × 12.25,引腳尖端 16.00
腳位編號(元件面看):第 1 腳在 +y 排最左(本體上有圓點),1–12 由左到右;
13–24 在 −y 排由右到左 → 第 24 腳正對第 1 腳。與規格書接線圖一致:
1/24、4/21、7/18、10/15 同相,MCT 腳(1、4、7、10)在纜線側。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FP_NAME = "Transformer_CNDtek_G2423S"
OUT = HERE.parent / "footprints" / "CM5.pretty" / f"{FP_NAME}.kicad_mod"

P = 1.27
ROW_Y = 7.30                 # (12.70 + 16.50) / 4
PAD_W, PAD_L = 0.75, 1.90
BODY = (8.90, 6.125)         # 本體半寬、半高


def pad_xy(n: int) -> tuple[float, float]:
    if 1 <= n <= 12:
        return round(-5.5 * P + (n - 1) * P, 4), ROW_Y
    if 13 <= n <= 24:
        return round(5.5 * P - (n - 13) * P, 4), -ROW_Y
    raise ValueError(n)


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def line(layer, x0, y0, x1, y1, w) -> str:
    return (f'\t(fp_line\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n\t)\n')


def rect(layer, x0, y0, x1, y1, w) -> str:
    return (f'\t(fp_rect\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t)\n')


def text(key, val, y, layer, hide=False) -> str:
    h = "\n\t\t(hide yes)" if hide else ""
    return (f'\t(property "{key}" "{val}"\n\t\t(at 0 {f(y)} 0)\n\t\t(layer "{layer}"){h}\n'
            '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def footprint() -> str:
    bx, by = BODY
    out = [f'(footprint "{FP_NAME}"\n\t(version 20240108)\n\t(generator "kicad-scripted-pcb")\n\t(layer "F.Cu")\n'
           '\t(descr "CND-tek G2423S PoE+ 1000Base-T single port transformer, 24 pin SMD, 1.27 mm '
           '(LCSC C5122139 datasheet)")\n\t(tags "transformer magnetics PoE gigabit")\n']
    out.append(text("Reference", "REF**", -ROW_Y - 2.0, "F.SilkS"))
    out.append(text("Value", FP_NAME, 0, "F.Fab"))
    out.append(text("Datasheet", "", 0, "F.Fab", True))
    out.append(text("Description", "", 0, "F.Fab", True))
    out.append("\t(attr smd)\n")
    out.append(rect("F.Fab", -bx, -by, bx, by, 0.1))
    out.append(rect("F.CrtYd", -bx - 0.5, -ROW_Y - PAD_L / 2 - 0.5, bx + 0.5, ROW_Y + PAD_L / 2 + 0.5, 0.05))
    # 絲印:本體左右兩邊(焊墊排之間)+ 第 1 腳圓點
    for sx in (-bx - 0.11, bx + 0.11):
        out.append(line("F.SilkS", sx, -by + 0.3, sx, by - 0.3, 0.12))
    x1, y1 = pad_xy(1)
    out.append(f'\t(fp_circle\n\t\t(center {f(x1 - 1.0)} {f(y1)})\n\t\t(end {f(x1 - 0.85)} {f(y1)})\n'
               '\t\t(stroke\n\t\t\t(width 0.3)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t)\n')
    out.append(f'\t(fp_circle\n\t\t(center {f(x1)} {f(by - 1.2)})\n\t\t(end {f(x1 + 0.4)} {f(by - 1.2)})\n'
               '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "F.Fab")\n\t)\n')
    for n in range(1, 25):
        x, y = pad_xy(n)
        out.append(f'\t(pad "{n}" smd {"rect" if n == 1 else "roundrect"}\n\t\t(at {f(x)} {f(y)})\n'
                   f'\t\t(size {PAD_W} {PAD_L})\n\t\t(layers "F.Cu" "F.Paste" "F.Mask")'
                   + ("" if n == 1 else "\n\t\t(roundrect_rratio 0.25)") + "\n\t)\n")
    out.append(")\n")
    return "".join(out)


def check() -> None:
    """規格書尺寸自洽:第 1–12 腳跨距 13.97、內外緣 12.70 / 16.50、24 對 1。"""
    span = pad_xy(12)[0] - pad_xy(1)[0]
    inner, outer = 2 * ROW_Y - PAD_L, 2 * ROW_Y + PAD_L
    assert abs(span - 13.97) < 1e-6, span
    assert abs(inner - 12.70) < 1e-6 and abs(outer - 16.50) < 1e-6, (inner, outer)
    for a, b in ((1, 24), (4, 21), (7, 18), (10, 15)):
        assert pad_xy(a)[0] == pad_xy(b)[0], (a, b)


def main() -> int:
    check()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(footprint(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}(跨距 13.97、內緣 12.70、外緣 16.50 核對通過)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
