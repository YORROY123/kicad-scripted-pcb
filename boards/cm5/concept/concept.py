"""CM5 載板「概念擺位」→ 3D 組合預覽。

只擺件、不佈線,不是正式 PCB(正式版要照 BoardSpec + 自檢 + 佈線走 build.ps1)。
  <KiCad python> concept.py  → cm5-concept.kicad_pcb + models/*.wrl

- 大件(IC、接頭、電感、大電容)手動擺;其餘被動件依網表找「共用最多小網路」的 IC/接頭,
  從它旁邊螺旋搜尋第一個不重疊的位置。
- KiCad 庫缺 3D 模型的:先找近似檔名,找不到就依 F.Fab 外框產生方塊 VRML。
- CM5 模組、NVMe 2280 SSD 是示意外型(尺寸對、細節不對)。
"""
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
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

W, H = 170.0, 120.0
CM5_C = (110.0, 48.0)          # 模組中心;轉 90°,55 × 40 橫放
M2 = (8.0, 15.0)               # M.2 插座定位孔中點;卡往 +x

# ── 手動擺放:ref -> (x, y, rot) ──────────────────────────────────────
EDGE = H


def rj_bottom(cx, xmax):        # 開口在局部 +x 的接頭,轉 270 → 開口朝板下緣
    return (cx, EDGE - xmax + 0.6, 270)


PLACE = {
    # 板下緣 I/O
    # RJHSE5380 的開口在局部 −y(F.Fab 前緣 y=−8.0;單顆渲染 rjsides.png 的 back 面才看得到孔)
    # → 轉 180 開口朝板下緣、前緣切齊板邊。前兩版用 90(開口朝左,板邊只看到側面)。
    # 本體 x 在 −4.7..11.8(原點是 1 腳),轉 180 後 courtyard 在 cx−13.3..cx+6.2
    "J40": (14, EDGE - 8.0, 180), "J41": (34, EDGE - 8.0, 180),
    "J30": (50, EDGE - 10.92, 180),
    "J70": rj_bottom(69, 8.57),
    "J51": rj_bottom(88, 9.93), "J52": rj_bottom(105, 9.93),
    "J50": (121, EDGE - 4.2 + 0.6, 0),
    "SW51": (134, EDGE - 2.0, 180), "SW50": (144, EDGE - 4.0, 0),
    # 右緣:54V 輸入與電源
    "J20": (166.5, 52, 90),
    "C10": (150, 22, 0), "F1": (158, 34, 90), "D20": (164, 36, 90),
    "Q10": (148, 44, 0), "Q11": (148, 54, 0), "U10": (158, 47, 0),
    "L10": (154, 66, 0),
    "U20": (149, 84, 0), "L20": (159, 84, 0),
    # 上緣
    "J60": (M2[0], M2[1], 90),
    "J80": (98, 6, 90), "J81": (154, 6, 180),   # 風扇座讓出右上角固定孔
    # CM5 與周邊
    "BT50": (22, 47, 0),
    # 網路 / PoE(左下)
    "T40": (12, 86, 0), "T41": (31, 86, 0),     # 與 J40/J41 之間留固定孔 H3
    "U50": (21, 70, 0), "C83": (9, 64, 0),
    "U40": (46, 62, 0), "U41": (46, 78, 0),
    "U30": (46, 95, 0), "U31": (54, 95, 0),
    # USB / HDMI
    "U61": (90, 80, 0), "U60": (104, 76, 0),
    "U62": (86, 95, 0), "U63": (103, 95, 0),
    "U70": (69, 92, 0),
}
# 只接大電源網(+5V/+3V3)的去耦件:依位號區段放到所屬區塊旁(由大到小比對)
GROUP = [(230, "J80"), (220, "L20"), (200, "U61"), (130, "U41"), (100, "U40"), (90, "T40"),
         (70, "U50"), (60, "J30"), (50, "J70"), (40, "L20"), (30, "L10"), (0, "U10")]
CM5_HOLES = [(16.5, 24), (-16.5, 24), (16.5, -24), (-16.5, -24)]  # 模組座標(長軸 y)
CM5_J = {"J1": (-17, 2.5), "J2": (17, 2.5)}


def rot_xy(lx, ly, deg):
    """封裝局部座標 → 畫面座標偏移(KiCad:畫面逆時針、y 向下)。"""
    r = math.radians(deg)
    return (lx * math.cos(r) + ly * math.sin(r), -lx * math.sin(r) + ly * math.cos(r))


for ref, (mx, my) in CM5_J.items():
    dx, dy = rot_xy(mx, my, 90)
    PLACE[ref] = (CM5_C[0] + dx, CM5_C[1] + dy, 90)

# 板上 M3 固定孔。左上被 M.2 插座、左下被 PoE 口 J40 佔住 → 這兩顆內移
BOARD_HOLES = [(4, 31), (W - 4, 4), (4, 99.5), (W - 4, H - 4)]

# 自動擺放的禁區(x0, y0, x1, y1):CM5 模組底下、SSD 底下
KEEPOUT = [
    (CM5_C[0] - 27.5, CM5_C[1] - 20, CM5_C[0] + 27.5, CM5_C[1] + 20),
    (M2[0], M2[1] - 11, M2[0] + 82, M2[1] + 11),
]


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


def rect_of(fp):
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False)
    return [pcbnew.ToMM(v) - pcbgen.ORIGIN[i % 2] for i, v in
            enumerate((bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))]


def overlap(a, b, gap=0.25):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


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
    net_size = {}
    for n in pad_net.values():
        net_size[n] = net_size.get(n, 0) + 1
    by_ref = {}
    for (ref, _), n in pad_net.items():
        by_ref.setdefault(ref, set()).add(n)

    board = pcbnew.BOARD()
    board.GetDesignSettings().SetCopperLayerCount(4)
    nets = {}
    for name in sorted(set(pad_net.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    report, occupied, fps = [], [], {}
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

    for ref, (x, y, rot) in PLACE.items():
        fp = fps[ref]
        fp.SetPosition(at(x, y))
        fp.SetOrientationDegrees(rot)
        occupied.append(rect_of(fp))
    occupied += [list(k) for k in KEEPOUT[1:]]  # SSD 底下禁區(CM5 底下的連接器已在 occupied)
    occupied += [[x - 3.5, y - 3.5, x + 3.5, y + 3.5] for x, y in BOARD_HOLES]  # M3 孔 courtyard
    occupied.append(list(KEEPOUT[0]))

    # 依網表把其餘件擺到相關 IC/接頭旁
    anchors = set(PLACE) - {"J1", "J2"}
    for ref in sorted(set(comps) - set(PLACE), key=lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r)))):
        small = {n for n in by_ref.get(ref, ()) if net_size[n] <= 20}
        best, score = None, 0
        for a in anchors | {"J1", "J2"}:
            s = len(small & by_ref.get(a, set()))
            if s > score:
                best, score = a, s
        if best in ("J1", "J2"):  # CM5 腳的周邊件放模組外側(下緣)
            ax, ay = CM5_C[0], CM5_C[1] + 22
        elif best:
            ax, ay = PLACE[best][0], PLACE[best][1]
        else:
            num = int(re.sub(r"\D", "", ref))
            grp = next(a for lo, a in GROUP if num >= lo)
            ax, ay = PLACE[grp][0], PLACE[grp][1]
        fp = fps[ref]
        placed = False
        for step in range(0, 4000):
            ang = step * 0.5
            rad = 0.35 * ang
            x = round((ax + rad * math.cos(ang)) * 2) / 2
            y = round((ay + rad * math.sin(ang)) * 2) / 2
            fp.SetPosition(at(x, y))
            r = rect_of(fp)
            if r[0] < 1 or r[1] < 1 or r[2] > W - 1 or r[3] > H - 1:
                continue
            if any(overlap(r, o) for o in occupied):
                continue
            occupied.append(r)
            placed = True
            break
        if not placed:
            raise SystemExit(f"{ref}: 找不到空位")

    # 固定孔:板四角 + CM5 四孔 + SSD 固定柱
    holes = list(BOARD_HOLES)
    for hx, hy in CM5_HOLES:
        dx, dy = rot_xy(hx, hy, 90)
        holes.append((CM5_C[0] + dx, CM5_C[1] + dy))
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
