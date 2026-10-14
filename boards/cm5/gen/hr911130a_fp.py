"""Hanrun HR911130A(1000Base-T、內建變壓器與 2 顆 LED 的 RJ45)封裝。

    <KiCad python> hr911130a_fp.py [--compare]
        → 寫 ../footprints/CM5.pretty/RJ45_Hanrun_HR911130A_Horizontal.kicad_mod
        --compare:和 KiCad 內建的同系列 HR911105A 比對共用的孔(定位柱、LED 腳、屏蔽卡腳)

KiCad 10 沒有 HR911130A;JLC 有 C54408(庫存 2 萬以上)。尺寸取自 Hanrun 規格書
(LCSC C54408,第 2 頁 Mounting Pattern;PDF 是向量圖,在樹莓派上用 pdftoppm 轉圖讀出)。

座標(元件面看,原點 = 兩個 Ø3.25 定位柱的中點,y 向後;前面 = RJ45 開口在 −y):
  - Ø3.25 定位柱 ×2(NPTH):x ±5.715
  - Ø0.89 訊號腳 ×10:奇數腳 y +8.89、偶數腳 y +6.35,相鄰腳 x 差 1.27,第 1 腳 x +5.715
  - Ø1.02 LED 腳 ×4:y −4.90;14 / 13 / 12 / 11 在 x −6.625 / −4.085 / +4.085 / +6.625
    規格書標註 13.25(14 ↔ 11),但圖畫成約 12.7,只有這一個尺寸沒照比例。
    KiCad 的 HR911105A(同系列、同外殼)LED 腳正好是 13.25 → 採用標註值,--compare 會核對。
  - Ø1.63 屏蔽卡腳 ×2:x ±7.745、y +3.05(焊盤號 SH,接 GND)
其餘 10 支訊號腳由程式自動在圖上做 Hough 圓偵測核對過(誤差 ≤ 0.02 mm)。

腳位(規格書第 1 頁):1 晶片側中心抽頭、2/3 MDI0±、4/7 MDI1±、5/6 MDI2±、8/9 MDI3±、
10 經內部 1000pF/2kV 與 4 × 75Ω 接到纜線側中心抽頭(Bob Smith 終端)、
11 = 綠 LED 陽極、12 = 綠 LED 陰極、14 = 黃 LED 陽極、13 = 黃 LED 陰極。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FP_NAME = "RJ45_Hanrun_HR911130A_Horizontal"
OUT = HERE.parent / "footprints" / "CM5.pretty" / f"{FP_NAME}.kicad_mod"

P = 1.27
SIGNAL = {n: (round(5.715 - (n - 1) * P, 4), 8.89 if n % 2 else 6.35) for n in range(1, 11)}
LED = {14: (-6.625, -4.90), 13: (-4.085, -4.90), 12: (4.085, -4.90), 11: (6.625, -4.90)}
NPTH = [(-5.715, 0.0), (5.715, 0.0)]
SHIELD = [(-7.745, 3.05), (7.745, 3.05)]
BODY = (-8.05, -10.92, 8.05, 10.38)          # 外殼:寬 16.10,前緣在定位柱前 10.92,深 21.30


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def pad(num: str, kind: str, shape: str, xy, size: float, drill: float) -> str:
    layers = '"*.Cu" "*.Mask"'
    return (f'\t(pad "{num}" {kind} {shape}\n\t\t(at {f(xy[0])} {f(xy[1])})\n\t\t(size {size} {size})\n'
            f'\t\t(drill {drill})\n\t\t(layers {layers})'
            + ("\n\t\t(roundrect_rratio 0.2)" if shape == "roundrect" else "") + "\n\t)\n")


def rect(layer: str, x0, y0, x1, y1, w) -> str:
    return (f'\t(fp_rect\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "{layer}")\n\t)\n')


def line(layer: str, x0, y0, x1, y1, w) -> str:
    return (f'\t(fp_line\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "{layer}")\n\t)\n')


def text(key: str, val: str, y: float, layer: str, hide: bool = False) -> str:
    h = "\n\t\t(hide yes)" if hide else ""
    return (f'\t(property "{key}" "{val}"\n\t\t(at 0 {f(y)} 0)\n\t\t(layer "{layer}"){h}\n'
            '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def footprint() -> str:
    x0, y0, x1, y1 = BODY
    out = [f'(footprint "{FP_NAME}"\n\t(version 20240108)\n\t(generator "kicad-scripted-pcb")\n\t(layer "F.Cu")\n'
           '\t(descr "Hanrun HR911130A, 1 port RJ45, 1000Base-T magnetics, 2 LEDs, tab up, through hole '
           '(LCSC C54408 datasheet)")\n\t(tags "RJ45 magjack gigabit")\n']
    out.append(text("Reference", "REF**", y1 + 1.5, "F.SilkS"))
    out.append(text("Value", FP_NAME, 0, "F.Fab"))
    out.append(text("Datasheet", "", 0, "F.Fab", True))
    out.append(text("Description", "", 0, "F.Fab", True))
    out.append("\t(attr through_hole)\n")
    out.append(rect("F.Fab", x0, y0, x1, y1, 0.1))
    # 絲印外框:側邊在屏蔽卡腳(焊盤 Ø2.5)處斷開,留 0.2mm 間隙
    sx0, sy0, sx1, sy1 = x0 - 0.11, y0 - 0.11, x1 + 0.11, y1 + 0.11
    gap0, gap1 = SHIELD[0][1] - 1.25 - 0.26, SHIELD[0][1] + 1.25 + 0.26
    for seg in ((sx0, sy0, sx1, sy0), (sx0, sy1, sx1, sy1),
                (sx0, sy0, sx0, gap0), (sx0, gap1, sx0, sy1), (sx1, sy0, sx1, gap0), (sx1, gap1, sx1, sy1)):
        out.append(line("F.SilkS", *seg, 0.12))
    out.append(rect("F.CrtYd", x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, 0.05))
    for n, xy in SIGNAL.items():
        out.append(pad(str(n), "thru_hole", "roundrect" if n == 1 else "circle", xy, 1.5, 0.89))
    for n, xy in LED.items():
        out.append(pad(str(n), "thru_hole", "circle", xy, 1.6, 1.02))
    for xy in SHIELD:
        out.append(pad("SH", "thru_hole", "circle", xy, 2.5, 1.63))
    for xy in NPTH:
        out.append(pad("", "np_thru_hole", "circle", xy, 3.25, 3.25))
    out.append(")\n")
    return "".join(out)


def compare() -> int:
    """KiCad 內建 HR911105A:同一外殼,定位柱、LED 腳、屏蔽卡腳應與本封裝相同(平移後)。"""
    import pcbnew
    sys.path.insert(0, str(HERE.parents[2] / "lib"))
    from pcbgen import FP_DIR
    ref = pcbnew.FootprintLoad(str(FP_DIR / "Connector_RJ.pretty"), "RJ45_Hanrun_HR911105A_Horizontal")
    pads = [(p.GetNumber(), pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y),
             round(pcbnew.ToMM(p.GetDrillSize().x), 3)) for p in ref.Pads()]
    holes = sorted((x, y) for n, x, y, d in pads if n == "")
    cx, cy = (holes[0][0] + holes[1][0]) / 2, holes[0][1]
    # KiCad 那顆是轉 180° 擺的(第 1 腳在 −x、LED 在 +y):對方 (x, y) = 本封裝 (−x, −y)

    def rel(sel):
        return sorted((round(x - cx, 3), round(y - cy, 3)) for n, x, y, d in pads if sel(n, d))

    def rot(pts):
        return sorted((round(-x, 3), round(-y, 3)) for x, y in pts)
    led_ref, mine_led = rel(lambda n, d: d == 1.02), rot(LED.values())
    sh_ref, mine_sh = rel(lambda n, d: n == "SH"), rot(SHIELD)
    np_ref = sorted(round(x - cx, 3) for x, _ in holes)
    ok = True
    for name, a, b in (("LED 腳", led_ref, mine_led), ("屏蔽卡腳", sh_ref, mine_sh),
                       ("定位柱 x", np_ref, sorted(x for x, _ in NPTH))):
        same = len(a) == len(b) and all(abs(p - q) < 0.006 for u, v in zip(a, b)
                                        for p, q in zip(u if isinstance(u, tuple) else (u,),
                                                        v if isinstance(v, tuple) else (v,)))
        print(f"  {name}: HR911105A {a}\n          本封裝    {b} → {'一致' if same else '不一致'}")
        ok &= same
    print(f"compare: {'通過' if ok else '失敗'}")
    return 0 if ok else 1


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(footprint(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    return compare() if "--compare" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
