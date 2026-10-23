"""CM5 載板的擺件(正式 PCB gen/pcb.py 與 3D 預覽 concept/concept.py 共用)。

座標 mm,板框左上角為原點,170 × 120。
- 大件(IC、接頭、電感、大電容)寫在 PLACE。
- 其餘件 auto_place():依網表找「共用最多小網路」的 IC/接頭當錨點,從錨點螺旋搜尋第一個
  外接框(含 0.25 mm 間隙)不和已擺件、禁區、固定孔重疊、離板邊 ≥1 mm 的位置。
  順序固定(位號排序),所以每次結果相同。
"""
import math
import re

import pcbnew
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


def auto_place(fps, pad_net):
    """fps: ref -> 已載入的 FOOTPRINT。擺好所有件(會改 fps 的位置與角度),回傳 ref -> (x, y, rot)。"""
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

    anchors = set(PLACE) - {"J1", "J2"}
    for ref in sorted(set(fps) - set(PLACE), key=_ref_key):
        small = {n for n in by_ref.get(ref, ()) if net_size[n] <= 20}
        best, score = None, 0
        for a in sorted(anchors | {"J1", "J2"}):
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
