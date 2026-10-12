"""CM5 載板連接器的封裝與模組幾何。

    python cm5_fp.py                       → 寫 ../footprints/CM5.pretty/<FP_NAME>.kicad_mod
    <KiCad python> cm5_fp.py --compare <官方 Raspberry-Pi-5-Compute-Module.kicad_mod>
                                           → 把兩顆連接器與 4 個孔照 MODULE 組回去,逐焊盤比對

CM5 用兩顆 Amphenol 10164227-1001A1RLF(100 腳、0.4 mm、1.5 mm 堆疊)。一顆連接器一個封裝:
實體上是兩顆料,JLC 的 BOM / 座標檔要逐顆列出。兩顆的相對位置不靠封裝綁死,而是由
MODULE(以模組中心為原點)給出,pcb.py 擺件時從這裡算。

尺寸來源:CM5 datasheet 4.1.1 圖 4(連接器中心線離模組邊 3 mm、中心離固定孔 21.5 mm,
孔內縮 3.5 mm);焊盤 0.2 × 0.7 mm 與逐焊盤座標以官方 CM5 IO Board rev 2 的 KiCad 檔
(https://rpltd.co/cm5io-design-files,RP-008099-DD-1)為準。官方檔沒有授權條款
(只有 Copyright Raspberry Pi Ltd.),所以不放進 repo,只用 --compare 比對。

座標方向與官方封裝相同:連接器沿 y 排列,腳 1 在 −y 端,奇數腳在 −x 側。
J1 = CM5 腳 1–100;J2 的焊盤 n = CM5 腳 100 + n(與 symbols/CM5.kicad_sym 一致)。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = "CM5"
FP_NAME = "Amphenol_10164227-1001A1RLF_2x50_P0.4mm"
OUT = HERE.parent / "footprints" / f"{LIB}.pretty" / f"{FP_NAME}.kicad_mod"

PITCH = 0.4
ROWS = 50
ROW_X = 1.54              # 奇數腳 x = −1.54、偶數腳 x = +1.54(相對連接器中心)
PAD_W, PAD_L = 0.2, 0.7   # 沿排列方向 0.2、橫向 0.7
CRT_X, CRT_Y = 1.85, 11.4  # 連接器 courtyard 半寬 / 半長

# 模組幾何,原點 = 模組中心,單位 mm。官方封裝原點在一個固定孔,換算:x − 16.5、y + 24
MODULE = {
    "size": (40.0, 55.0),                       # x × y
    "J1": (-17.0, 2.5),                         # CM5 腳 1–100
    "J2": (17.0, 2.5),                          # CM5 腳 101–200
    "holes": [(-16.5, -24.0), (16.5, -24.0), (-16.5, 24.0), (16.5, 24.0)],
    "hole_d": 2.7,                              # M2.5,NPTH
}


def pad_xy(n: int) -> tuple[float, float]:
    """焊盤 n(1–100)相對連接器中心的座標。"""
    row = (n - 1) // 2
    x = -ROW_X if n % 2 else ROW_X
    y = round(-(ROWS - 1) / 2 * PITCH + row * PITCH, 4)
    return x, y


def f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def rect(layer: str, x0: float, y0: float, x1: float, y1: float, w: float) -> str:
    return (f'\t(fp_rect\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(stroke\n\t\t\t(width {w})\n\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n'
            f'\t\t(layer "{layer}")\n\t)\n')


def text_prop(key: str, val: str, y: float, layer: str, hide: bool) -> str:
    h = "\n\t\t(hide yes)" if hide else ""
    return (f'\t(property "{key}" "{val}"\n\t\t(at 0 {f(y)} 90)\n\t\t(layer "{layer}"){h}\n'
            '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')


def footprint() -> str:
    out = [f'(footprint "{FP_NAME}"\n\t(version 20240108)\n\t(generator "kicad-scripted-pcb")\n'
           '\t(layer "F.Cu")\n'
           '\t(descr "Amphenol 10164227-1001A1RLF, 100-pin 0.4 mm board-to-board receptacle, '
           '1.5 mm stacking (Raspberry Pi CM5 carrier)")\n'
           '\t(tags "Raspberry Pi CM5 Amphenol 10164227")\n']
    out.append(text_prop("Reference", "REF**", -CRT_Y - 1.2, "F.SilkS", False))
    out.append(text_prop("Value", FP_NAME, 0, "F.Fab", False))
    out.append(text_prop("Datasheet", "", 0, "F.Fab", True))
    out.append(text_prop("Description", "", 0, "F.Fab", True))
    out.append("\t(attr smd)\n")
    out.append(rect("F.CrtYd", -CRT_X, -CRT_Y, CRT_X, CRT_Y, 0.05))
    out.append(rect("F.Fab", -1.5, -11.0, 1.5, 11.0, 0.1))
    x1, y1 = pad_xy(1)
    # 腳 1 標記:絲印圓點在焊盤 1 外側(焊盤外緣 x −1.89,圓點外緣 −2.2,間隙 0.31)
    out.append(f'\t(fp_circle\n\t\t(center {f(x1 - 0.76)} {f(y1 - 0.6)})\n\t\t(end {f(x1 - 0.66)} {f(y1 - 0.6)})\n'
               '\t\t(stroke\n\t\t\t(width 0.2)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t)\n')
    out.append(f'\t(fp_line\n\t\t(start -1.5 {f(y1 - 0.5)})\n\t\t(end -0.9 {f(y1 - 1.1)})\n'
               '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type solid)\n\t\t)\n\t\t(layer "F.Fab")\n\t)\n')
    for n in range(1, 2 * ROWS + 1):
        x, y = pad_xy(n)
        out.append(f'\t(pad "{n}" smd rect\n\t\t(at {f(x)} {f(y)})\n\t\t(size {PAD_L} {PAD_W})\n'
                   '\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n\t)\n')
    out.append(")\n")
    return "".join(out)


def compare(official: Path) -> int:
    """官方封裝 vs 我們的連接器 ×2 + 孔,全部換到模組中心座標後逐項比對。"""
    import pcbnew

    def load(path: Path):
        fp = pcbnew.FootprintLoad(str(path.parent), path.stem)
        if fp is None:
            raise SystemExit(f"載入失敗:{path}")
        return fp

    def geom(pad, dx: float, dy: float) -> tuple:
        p = pad.GetPosition()
        bb = pad.GetBoundingBox()
        return (round(pcbnew.ToMM(p.x) + dx, 3), round(pcbnew.ToMM(p.y) + dy, 3),
                round(pcbnew.ToMM(bb.GetWidth()), 3), round(pcbnew.ToMM(bb.GetHeight()), 3),
                pad.GetShape(), pad.GetAttribute(), round(pcbnew.ToMM(pad.GetDrillSize().x), 3),
                tuple(sorted(pad.GetLayerSet().CuStack())), pad.IsOnLayer(pcbnew.F_Paste),
                pad.IsOnLayer(pcbnew.F_Mask))

    ref = load(official)
    want: dict = {}
    holes_ref = []
    for pad in ref.Pads():
        g = geom(pad, -16.5, 24.0)
        if pad.GetNumber():
            want[int(pad.GetNumber())] = g
        else:
            holes_ref.append(g[:2] + (g[2],))

    ours = load(OUT)
    got: dict = {}
    for conn, base in (("J1", 0), ("J2", 100)):
        cx, cy = MODULE[conn]
        for pad in ours.Pads():
            got[base + int(pad.GetNumber())] = geom(pad, cx, cy)

    bad = [n for n in range(1, 201) if want.get(n) != got.get(n)]
    for n in bad[:10]:
        print(f"  腳 {n}: 官方 {want.get(n)}\n         我們 {got.get(n)}")
    hole_ok = sorted(h[:2] for h in holes_ref) == sorted(MODULE["holes"]) and \
        all(h[2] == MODULE["hole_d"] for h in holes_ref)
    if not hole_ok:
        print(f"  孔:官方 {sorted(holes_ref)},MODULE {MODULE['holes']} Ø{MODULE['hole_d']}")
    extra = set(want) ^ set(range(1, 201))
    if extra:
        print(f"  官方焊盤編號不是剛好 1–200:{sorted(extra)[:10]}")
    print(f"compare: 焊盤 {200 - len(bad)}/200 一致(位置、尺寸、形狀、類型、銅層、錫膏、阻焊);"
          f"孔 {'4/4 一致' if hole_ok else '不一致'}")
    return 1 if bad or not hole_ok or extra else 0


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(footprint(), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(HERE.parent)}")
    if "--compare" in sys.argv:
        return compare(Path(sys.argv[sys.argv.index("--compare") + 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
