"""CM5 載板「概念擺位」→ 3D 組合預覽。

只擺件、不佈線,不是正式 PCB(正式版要照 BoardSpec + 自檢 + 佈線走 build.ps1)。
  <KiCad python> concept.py  → cm5-concept.kicad_pcb + models/*.wrl

- 大件(IC、接頭、電感、大電容)手動擺;其餘被動件依網表找「共用最多小網路」的 IC/接頭,
  從它旁邊螺旋搜尋第一個不重疊的位置。
- KiCad 庫缺 3D 模型的:先找近似檔名,找不到就依 F.Fab 外框產生方塊 VRML。
- CM5 模組、NVMe 2280 SSD 是示意外型(尺寸對、細節不對)。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gen"))
import pcbgen  # noqa: E402
import pcbnew  # noqa: E402
from pcbgen import at, mm  # noqa: E402

HERE = Path(__file__).resolve().parent
BOARD_DIR = HERE.parent
pcbgen.EXTRA_FP_DIRS.append(str(BOARD_DIR / "footprints"))
MODELS = HERE / "models"
MODELS.mkdir(exist_ok=True)
KMOD = Path(pcbnew.__file__).resolve().parents[3] / "share" / "kicad" / "3dmodels"
if not KMOD.is_dir():
    KMOD = Path(sys.executable).resolve().parents[1] / "share" / "kicad" / "3dmodels"

from placement import (  # noqa: E402
    BOARD_HOLES, CM5_C, CM5_HOLES, M2, MODULE_HOLES, W, H, auto_place, overlap,
)

# ── VRML ─────────────────────────────────────────────────────────────
def vrml(path: Path, boxes):
    """boxes: (x0, y0, z0, x1, y1, z1, (r, g, b)),mm,模型座標(y 向上)。KiCad VRML 單位 = 2.54mm。"""
    out = ["#VRML V2.0 utf8"]
    for x0, y0, z0, x1, y1, z1, (r, g, b) in boxes:
        s = 1 / 2.54
        x0, y0, z0, x1, y1, z1 = (v * s for v in (x0, y0, z0, x1, y1, z1))
        pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
               (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        out.append(
            "Shape { appearance Appearance { material Material { diffuseColor %g %g %g "
            "specularColor 0.2 0.2 0.2 shininess 0.3 } }\n geometry IndexedFaceSet { solid FALSE "
            "coord Coordinate { point [ %s ] }\n coordIndex [ %s ] } }"
            % (r, g, b, ", ".join("%.4f %.4f %.4f" % p for p in pts),
               " ".join("%d,%d,%d,%d,-1" % f for f in faces)))
    path.write_text("\n".join(out), encoding="utf-8")
    return "${KIPRJMOD}/models/" + path.name  # 相對專案目錄,板檔不帶本機路徑


SILVER, BLACK, BEIGE = (0.75, 0.75, 0.77), (0.12, 0.12, 0.12), (0.85, 0.8, 0.65)
GREEN, GOLD, DGRAY = (0.05, 0.35, 0.15), (0.85, 0.65, 0.2), (0.3, 0.3, 0.32)

# 依封裝名決定方塊高度與顏色
BOX_STYLE = [
    ("USB_A", 7.0, SILVER), ("USB_C", 3.2, SILVER), ("RJ45_Hanrun", 13.5, SILVER),
    ("Transformer", 6.5, BLACK), ("M.2_Socket", 4.2, BLACK), ("Amphenol_10164227", 1.5, BEIGE),
    ("QFN", 0.9, BLACK), ("SON", 0.6, BLACK), ("SOT", 1.1, BLACK), ("MSOP", 1.0, BLACK),
]
# 庫裡沒有同名檔,改用外型相同的近似檔
SUBST = [
    (r"RJ45_Amphenol_RJHSE5380", "Connector_RJ.3dshapes/RJ45_Amphenol_RJHSE538X.step"),
    (r"QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm", "Package_DFN_QFN.3dshapes/QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm.step"),
]


def local_box(fp):
    """封裝未旋轉時 F.Fab(沒有就 courtyard)的外框,mm。"""
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() == pcbnew.F_Fab and g.GetClass() == "PCB_SHAPE":
            bb = g.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    if xs:
        return [pcbnew.ToMM(v) for v in (min(xs), min(ys), max(xs), max(ys))]
    cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    return [pcbnew.ToMM(cy.GetLeft()) + 0.25, pcbnew.ToMM(cy.GetTop()) + 0.25,
            pcbnew.ToMM(cy.GetRight()) - 0.25, pcbnew.ToMM(cy.GetBottom()) - 0.25]


def fix_models(fp, name, report):
    models = list(fp.Models())
    ok = []
    for m in models:
        f = m.m_Filename.replace("${KICAD10_3DMODEL_DIR}", str(KMOD)).replace("${KICAD9_3DMODEL_DIR}", str(KMOD))
        if Path(f).exists() or Path(f).with_suffix(".wrl").exists():
            ok.append(m)
    if ok:
        return
    for pat, rel in SUBST:
        if re.search(pat, name) and (KMOD / rel).exists():
            fp.Models().clear()
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = "${KICAD10_3DMODEL_DIR}/" + rel
            fp.Models().push_back(m)
            report.append(f"{name}: 用近似模型 {rel}")
            return
    h, col = 1.0, DGRAY
    for key, hh, cc in BOX_STYLE:
        if key in name:
            h, col = hh, cc
            break
    x0, y0, x1, y1 = local_box(fp)
    if "M.2_Socket" in name:   # F.Fab 含整張卡的外框,改用 courtyard
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (cy.GetLeft() + mm(0.3), cy.GetTop() + mm(0.3), cy.GetRight() - mm(0.3), cy.GetBottom() - mm(0.3)))
    if "Hanrun" in name:
        x0, y0, x1, y1 = -8.05, -10.92, 8.05, 10.38
    boxes = [(x0, -y1, 0, x1, -y0, h, col)]
    if "RJ45_Hanrun" in name:  # 前面的插孔 + 兩顆燈
        boxes += [(-5.9, 10.92 - 0.01, 1.5, 5.9, 10.95, 11.0, BLACK),
                  (-7.6, 10.92 - 0.01, 11.6, -4.6, 10.96, 13.0, (0.2, 0.8, 0.2)),
                  (4.6, 10.92 - 0.01, 11.6, 7.6, 10.96, 13.0, (0.9, 0.8, 0.1))]
    if "M.2_Socket" in name:   # 插槽口
        boxes = [(x0, -y1, 0, x1, -y0, h, BLACK), (x0 + 1.5, -y1 - 0.01, 1.2, x1 - 1.5, -y1 + 0.5, 3.0, (0.05, 0.05, 0.05))]
    path = vrml(MODELS / f"{name}.wrl", boxes)
    fp.Models().clear()
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    fp.Models().push_back(m)
    report.append(f"{name}: 沒有 3D 模型 → 方塊 {x1 - x0:.1f}×{y1 - y0:.1f}×{h}")


def cm5_model():
    """CM5 模組(示意):55×40,板厚 1.0、底面距載板 1.5(連接器堆疊高度)。模型座標長軸在 y。"""
    z0, z1 = 1.5, 2.5
    b = [(-20, -27.5, z0, 20, 27.5, z1, GREEN)]
    top = z1
    parts = [  # (cx, cy, w, h, t, color),模組座標 y 向上
        (2, 4, 15, 15, 1.4, SILVER),          # BCM2712(金屬蓋)
        (2, -12, 14, 10, 1.0, BLACK),         # LPDDR4X
        (-11, -11, 11.5, 13, 1.0, BLACK),     # eMMC
        (-12, 8, 8, 8, 0.9, BLACK),           # RP1
        (12, -14, 6, 6, 0.8, BLACK),          # PMIC
        (13, 16, 12, 14, 1.6, SILVER),        # 無線模組屏蔽罩
        (17, 24.5, 3, 3, 1.2, GOLD),          # U.FL
    ]
    for cx, cy, w, h, t, c in parts:
        b.append((cx - w / 2, cy - h / 2, top, cx + w / 2, cy + h / 2, top + t, c))
    for hx, hy in CM5_HOLES:  # 鍍金孔環
        b.append((hx - 1.6, hy - 1.6, top, hx + 1.6, hy + 1.6, top + 0.03, GOLD))
    return vrml(MODELS / "CM5_module.wrl", b)


def ssd_model():
    """NVMe 2280(示意):卡從 M.2 定位孔線往 +y 延伸 80mm,寬 22。模型座標:原點 = 定位孔中點。"""
    z = 3.2
    b = [(-11, -80, z, 11, 0, z + 0.8, (0.08, 0.2, 0.12))]
    b += [(-11, -3.5, z, 11, 0, z + 0.81, GOLD)]                       # 金手指
    b += [(-8, -18, z + 0.8, 8, -6, z + 1.8, BLACK)]                    # 控制器
    b += [(-9, -45, z + 0.8, 9, -25, z + 2.0, BLACK),
          (-9, -70, z + 0.8, 9, -50, z + 2.0, BLACK)]                   # NAND
    b += [(-1.5, -81, 0, 1.5, -76, z, GOLD)]                            # 固定柱(示意)
    return vrml(MODELS / "NVMe_2280.wrl", b)


def add_virtual(board, ref, x, y, rot, model, value):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = model
    fp.Models().push_back(m)
    fp.SetPosition(at(x, y))
    fp.SetOrientationDegrees(rot)
    board.Add(fp)


def check_overlaps(board):
    """所有有 courtyard 的件(含固定孔)兩兩比外接框;回傳重疊的位號對。"""
    rects = []
    for fp in board.GetFootprints():
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if bb.GetWidth() == 0:
            continue
        rects.append((fp.GetReference(), [pcbnew.ToMM(v) for v in
                      (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())]))
    return [(p, q) for i, (p, a) in enumerate(rects) for q, b in rects[i + 1:] if overlap(a, b, gap=0)]


def main():
    comps, pad_net = pcbgen.read_netlist(BOARD_DIR / "net.txt")

    board = pcbnew.BOARD()
    board.GetDesignSettings().SetCopperLayerCount(4)
    nets = {}
    for name in sorted(set(pad_net.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    report, fps = [], {}
    for ref, info in sorted(comps.items()):
        lib, name = info["footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(pcbgen.fp_lib_dir(lib)), name)
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        if lib.startswith(("Resistor", "Capacitor_SMD")) and "CP_Elec" not in name:
            fp.Reference().SetLayer(pcbnew.F_Fab)
        fix_models(fp, name, report)
        for pad in fp.Pads():
            n = pad_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(nets[n])
        board.Add(fp)
        fps[ref] = fp

    auto_place(fps, pad_net)

    # 固定孔:板四角 + CM5 四孔 + SSD 固定柱
    holes = list(BOARD_HOLES) + list(MODULE_HOLES)
    for i, (x, y) in enumerate(holes, 1):
        fp = pcbnew.FootprintLoad(str(pcbgen.fp_lib_dir("MountingHole")),
                                  "MountingHole_2.7mm_M2.5" if i > 4 else "MountingHole_3.2mm_M3")
        fp.SetReference(f"H{i}")
        fp.Reference().SetVisible(False)
        fp.SetBoardOnly(True)
        fp.SetPosition(at(x, y))
        board.Add(fp)

    add_virtual(board, "MOD1", CM5_C[0], CM5_C[1], 90, cm5_model(), "Raspberry Pi CM5")
    add_virtual(board, "MOD2", M2[0], M2[1], 90, ssd_model(), "NVMe 2280 SSD")

    corners = [(0, 0), (W, 0), (W, H), (0, H)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        s.SetStart(at(x1, y1))
        s.SetEnd(at(x2, y2))
        board.Add(s)

    bad = check_overlaps(board)
    if bad:
        raise SystemExit("courtyard 重疊,不寫檔: " + ", ".join(f"{p}-{q}" for p, q in bad))

    out = HERE / "cm5-concept.kicad_pcb"
    pcbnew.SaveBoard(str(out), board)
    print(f"wrote {out.name}: {len(comps)} 件")
    for line in dict.fromkeys(report):
        print(" ", line)


main()
