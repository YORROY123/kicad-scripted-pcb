"""CM5 載板的擺件(正式 PCB gen/pcb.py 與 3D 預覽 concept/concept.py 共用)。

座標 mm,板框左上角為原點,170 × 120。
- 大件(IC、接頭、電感、大電容)寫在 PLACE。
- 其餘件 auto_place():依網表找共用小網路的 IC/接頭當錨點(越小的網越算數:1 / 網的焊盤數),
  從錨點上「那條網的焊盤」螺旋搜尋第一個外接框(含 0.25 mm 間隙)不和已擺件、禁區、固定孔
  重疊、離板邊 ≥1 mm 的位置 —— 去耦電容因此貼著它服務的那支腳,不是 IC 中心。
  分數相同、或只接大電源網(+5V/+3V3/+54V)時,選原理圖上離它最近的錨點(電容畫在它的 IC 旁)。
  順序固定(位號排序),所以每次結果相同。
"""
import math
import re

import pcbnew
import power_stage
from pcbgen import ORIGIN, at

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
    # SW_SPDT_PCM12:撥桿在局部 +y(本體前緣 y=1.6、撥桿到 3.15)→ 0°;固定腳到 y=1.83、銅到板邊要 ≥0.5 mm,所以本體前緣退到板邊內 0.75 mm,撥桿伸出約 0.8 mm。
    # 先前用 180°,撥桿朝板內、腳在板外。
    "SW51": (134, EDGE - 2.35, 0), "SW50": (144, EDGE - 4.0, 0),
    # 右緣:54V 輸入與兩級降壓。功率件照規格書佈局建議手擺(LM5146 SNVSBV0A §11.1、
    # TPS568230 SLVSEY5C §10.1),鋪銅與過孔在 gen/pcb.py 的 POUR_ZONES / VIAS。
    "J20": (166.5, 24, 90),
    "F1": (158, 24, 180), "C10": (149, 22, 180), "D20": (148.5, 31.5, 180),  # + 端都朝右,接 +54V 帶子
    # LM5146:Q10 轉 180、Q11 不轉,上下疊 → 開關節點(Q10 源極、Q11 汲極)在右側一直線、
    # 熱迴路(輸入電容 → Q10 汲極 … Q11 源極 → 電容)在左側;兩支閘極在外側角落
    "Q10": (154, 44, 180), "Q11": (154, 50.2, 0),
    "U10": (155.5, 36.5, 270),  # 閘極驅動腳朝下:HO / SW 正對 Q10 閘極與源極
    # 閘極驅動迴路(§11.1.2):VCC 電容、自舉電容放在 U10 與 Q10 之間,貼著 VCC / BST、SW 腳
    "C20": (154.3, 39.93, 0), "C21": (157.2, 39.93, 0),
    # 輸入電容:熱迴路那排 +54V 在上(貼 Q10 汲極)、GND 在下(貼 Q11 源極);上排轉 90,
    # +54V 在下,和熱迴路那排的 +54V 連成一條,GND 在上
    "C11": (148.4, 47, 270), "C13": (144.85, 47, 270), "C16": (141.3, 47, 270),
    "C12": (141.6, 38.5, 90), "C14": (145.15, 38.5, 90), "C15": (148.7, 38.5, 90),
    "C17": (160.3, 37.4, 90),   # U10 VIN 去耦
    "L10": (155, 61, 270),      # 1 腳(SW)朝上接 Q11 汲極
    # 輸出電容一直排:+ 端全在左(+5V 鋪銅)、− 端全在右(GND 鋪銅)
    "C30": (163.4, 56.6, 0), "C31": (163.4, 60.2, 0), "C32": (163.4, 63.8, 0), "C33": (163.4, 67.4, 0),
    "C34": (163.4, 71.0, 0),
    # TPS568230 轉 180:VIN(2–5 腳)朝右接輸入電容、SW(19/20 腳)朝下接 L20。
    # 整級跨在 In2 的分界上:輸入在 +5V 平面、L20 的 2 腳在 +3V3 平面(y ≥ 72.25)
    "U20": (142, 62, 180), "C45": (147.6, 60.8, 90), "C46": (147.6, 55.5, 90), "C47": (143, 58.9, 180),
    # 自舉電容在 BST 腳旁(SW3 端朝下接 L20 的鋪銅)、VCC 電容在左下角(右邊和下面都沒空位)
    "C49": (145.4, 63.95, 0), "C48": (138.8, 63.1, 90),
    "L20": (143.3, 71.2, 270),
    "C40": (151.6, 74.6, 0), "C41": (151.6, 78.2, 0), "C42": (151.6, 81.8, 0), "C43": (151.6, 85.4, 0),
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

# CM5 模組的 4 個 M2.5 孔(畫面座標)
MODULE_HOLES = [(CM5_C[0] + rot_xy(hx, hy, 90)[0], CM5_C[1] + rot_xy(hx, hy, 90)[1])
                for hx, hy in CM5_HOLES]


def rect_of(fp):
    """courtyard 外接框(沒有 courtyard 就用整體外框),板座標 mm。"""
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False)
    return [pcbnew.ToMM(v) - ORIGIN[i % 2] for i, v in
            enumerate((bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))]


def overlap(a, b, gap=0.25):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _ref_key(r):
    return (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r)))


def sch_positions(sch_path) -> dict:
    """原理圖每個器件的位置:ref -> (x, y) mm(多單元器件取第一個單元)。"""
    text = sch_path.read_text(encoding="utf-8")
    pos = {}
    for m in re.finditer(r'\(symbol\s*\(lib_id "[^"]*"\)\s*\(at ([-\d.]+) ([-\d.]+)[^)]*\)'
                         r'(?:(?!\(symbol\s*\(lib_id).)*?\(property "Reference" "([^"]+)"', text, re.S):
        pos.setdefault(m.group(3), (float(m.group(1)), float(m.group(2))))
    return pos


def pad_xy(fp, ref, nets, pad_net):
    """fp 上接到 nets 的焊盤中心(板座標 mm),依焊盤編號排序。

    擺件時封裝還沒掛網路,網名從網表 pad_net[(ref, 焊盤編號)] 查。"""
    out = []
    for p in sorted(fp.Pads(), key=lambda p: (len(p.GetNumber()), p.GetNumber())):
        if pad_net.get((ref, p.GetNumber())) in nets:
            c = p.GetPosition()
            out.append((pcbnew.ToMM(c.x) - ORIGIN[0], pcbnew.ToMM(c.y) - ORIGIN[1]))
    return out


def auto_place(fps, pad_net, sch_xy=None):
    """fps: ref -> 已載入的 FOOTPRINT。擺好所有件(會改 fps 的位置與角度),回傳 ref -> (x, y, rot)。

    sch_xy:sch_positions() 的結果;沒有就照舊用位號區段(GROUP)與錨點名稱排序。"""
    net_size, by_ref = {}, {}
    for (ref, _), n in pad_net.items():
        net_size[n] = net_size.get(n, 0) + 1
        by_ref.setdefault(ref, set()).add(n)

    place, occupied = {}, []
    for ref, (x, y, rot) in PLACE.items():
        fps[ref].SetPosition(at(x, y))
        fps[ref].SetOrientationDegrees(rot)
        occupied.append(rect_of(fps[ref]))
        place[ref] = (x, y, rot)
    occupied += [list(k) for k in KEEPOUT]  # CM5 模組底下(堆疊 1.5 mm)、SSD 底下
    occupied += [[x - 3.5, y - 3.5, x + 3.5, y + 3.5] for x, y in BOARD_HOLES]  # M3 孔 courtyard
    occupied += [list(k) for k in power_stage.keepouts()]  # 電源級的鋪銅與過孔

    # 手擺的大電容(C10、C83…)不當錨點:去耦電容要靠 IC 的腳,不是靠另一顆電容
    anchors = {r for r in PLACE if not r.startswith("C")} - {"J1", "J2"}
    used = {}  # (錨點, 網) -> 已分出幾個:同一顆 IC 的多個去耦電容輪流分到它的各支腳
    for ref in sorted(set(fps) - set(PLACE), key=_ref_key):
        mine = by_ref.get(ref, set()) - {"GND"}
        small = {n for n in mine if net_size[n] <= 20}
        def sch_dist(a):
            if not sch_xy or ref not in sch_xy or a not in sch_xy:
                return 0.0
            return math.dist(sch_xy[ref], sch_xy[a])

        cands = sorted(anchors | {"J1", "J2"})
        scores = {a: sum(1 / net_size[n] for n in small & by_ref.get(a, set())) for a in cands}
        top = max(scores.values())
        # 小網路只接到已擺好的被動件(例:R17 只和 C24 共用 FB_FF):擺在那顆旁邊,
        # 不然會退回「只接大電源網」那條規則,被拉到原理圖上最近的另一顆 IC
        buddies = [r for r in place if r not in PLACE and small & by_ref.get(r, set())]
        if top == 0 and buddies:
            best = min(buddies, key=lambda a: (sch_dist(a), a))
        elif top > 0:
            best = min((a for a in cands if scores[a] > top - 1e-9), key=lambda a: (sch_dist(a), a))
        elif sch_xy and ref in sch_xy:  # 只接大電源網:原理圖上最近、也接這條網的錨點
            near = [a for a in cands if mine & by_ref.get(a, set())]
            best = min(near, key=lambda a: (sch_dist(a), a)) if near else None
        else:
            best = None
        if best is None:  # 依位號區段找所屬區塊
            num = int(re.sub(r"\D", "", ref))
            best = next(a for lo, a in GROUP if num >= lo)
        shared = sorted(mine & by_ref.get(best, set()), key=lambda n: (net_size[n], n))
        spots = pad_xy(fps[best], best, {shared[0]}, pad_net) if shared else []
        if best in ("J1", "J2"):  # CM5 腳的周邊件放模組外側(下緣)
            ax, ay = CM5_C[0], CM5_C[1] + 22
        elif spots:
            k = (best, shared[0])
            ax, ay = spots[used.get(k, 0) % len(spots)]
            used[k] = used.get(k, 0) + 1
        else:
            ax, ay = PLACE[best][0], PLACE[best][1]
        fp = fps[ref]
        for step in range(4000):
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
            place[ref] = (x, y, fp.GetOrientationDegrees())
            break
        else:
            raise SystemExit(f"{ref}: 找不到空位")
    return place
