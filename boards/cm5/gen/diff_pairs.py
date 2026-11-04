"""差分線(佈線第三階段)。座標 mm,板框左上為原點。

每對用一條中心線描述,程式切 45° 角、往兩側偏移成 P、N 兩條線,兩端接到起訖零件上 P、N 網的焊盤
(gen/pcb.py add_diff_pairs)。線寬與對內間距照 README「差分阻抗」(sim/diff_impedance.py)。

- 全部走 F.Cu:正下方是 In1 整片地(阻抗模擬的假設)。
- 交叉一定要換層時用 B.Cu 短暫下穿。B.Cu 的參考面是 In2(電源),所以下穿段越短越好,
  而且不跨 In2 的 +5V / +3V3 分界(+5V:x ≥ 60.25 且 y ≤ 71.75;其餘是 +3V3)。
  換層處不放地過孔:參考面從 In1(地)換到 In2(電源),地過孔接不到 In2,幫不上回流。
- 手性:兩端 P 在行進方向的哪一側必須一致(平面上不能讓 P、N 交叉)。不一致時 gen/pcb.py 失敗,
  要在原理圖上對調(只限可以反相的介面)或改走法。本階段的處理見 README「差分線」。
- 鎖定:freerouting 不動,lib/route.py 重新匯入時留下。
"""
from __future__ import annotations

import math

CLASSES = {          # 名字: (線寬, 對內間距) mm
    "90": (0.165, 0.15),    # PCIe、USB3、USB2
    "100": (0.145, 0.20),   # HDMI、乙太網路
}
CHAMFER = 0.8        # 直角切成兩個 45°,切掉的長度
VIA_PITCH = 1.0      # 換層處一對過孔的中心距
SKEW_MAX = 0.1       # 對內長度差上限 mm(CM5 規格書 2.3.1 的 PCIe 值,其他介面一併套用)
KEEP = 0.3           # 自動擺件離差分線(含兩側)至少這麼遠

# PCIe 在 J2 頂排往北出;REFCLK / TX 一路在 F.Cu,RX 在 x≈45 從 TX 底下穿過(J2 那端由北到南是
# TX、RX、CLK,插座那端要 RX、TX、CLK),再從插座南端繞到腳後(奇數腳在靠板邊那排)。
# LAN0 那組在 PCIe 北邊往西,到 x≈66–70 往南時從 PCIe 底下穿過去;USB2(LAN0_D)留在 B.Cu
# 一路到 U40 旁,從 TX 那對底下過,才能在 U40 東側排成 RX、TX、D(腳 31/32、28/29、26/27)。
# (名字, P 網, N 網, 類別, 起點零件, 終點零件, 路徑)
# 路徑:("F.Cu" | "B.Cu", [中心線點…]) 與 ("via", (x, y)) 交錯;過孔對垂直於行進方向排。
PAIRS = (
    ("PCIe REFCLK", "PCIE_CLK_P", "PCIE_CLK_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(104.5, 28.9), (104.5, 27.4), (39.6, 27.4), (37.6, 29.4), (1.6, 29.4), (1.6, 11.0),
                  (4.4, 11.0)]),
    ]),
    ("PCIe TX", "PCIE_TX_P", "PCIE_TX_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(106.9, 28.9), (106.9, 24.6), (40.6, 24.6), (37.2, 28.0), (2.6, 28.0), (2.6, 12.5),
                  (4.4, 12.5)]),
    ]),
    ("PCIe RX", "PCIE_RX_P", "PCIE_RX_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(105.7, 28.9), (105.7, 26.0), (48.7, 26.0)]),
        ("via", (48.0, 26.0)),
        ("B.Cu", [(47.3, 26.0), (46.6, 26.0), (43.8, 23.2), (43.1, 23.2)]),
        ("via", (42.8, 23.2)),
        ("F.Cu", [(42.1, 23.2), (40.0, 23.2), (36.6, 26.6), (3.6, 26.6), (3.6, 14.0), (4.4, 14.0)]),
    ]),
    ("USB3-0 RX(CM5 端)", "CM5U0_RX_P", "CM5U0_RX_N", "90", ("J2",), ("C120", "C121"), [
        ("F.Cu", [(108.1, 28.9), (108.1, 21.6), (70.4, 21.6), (70.4, 22.7)]),
        ("via", (70.4, 23.4)),
        ("B.Cu", [(70.4, 24.1), (70.4, 27.9)]),
        ("via", (70.4, 28.6)),
        ("F.Cu", [(70.4, 29.3), (70.4, 63.0), (57.8, 63.0)]),
    ]),
    ("USB3-0 TX(LAN7800 端)", "LAN0_TX_P", "LAN0_TX_N", "90", ("C120", "C121"), ("U40",), [
        ("F.Cu", [(55.2, 63.0), (50.6, 63.0)]),
    ]),
    ("USB3-0 RX(LAN7800 端)", "LAN0_RX_P", "LAN0_RX_N", "90", ("J2",), ("U40",), [
        ("F.Cu", [(110.5, 28.9), (110.5, 19.6), (66.0, 19.6), (66.0, 22.7)]),
        ("via", (66.0, 23.4)),
        ("B.Cu", [(66.0, 24.1), (66.0, 27.9)]),
        ("via", (66.0, 28.6)),
        ("F.Cu", [(66.0, 29.3), (66.0, 61.5), (50.6, 61.5)]),
    ]),
    ("USB2 LAN0", "LAN0_DP", "LAN0_DM", "90", ("J2",), ("U40",), [
        ("F.Cu", [(109.3, 28.9), (109.3, 20.6), (68.2, 20.6), (68.2, 22.7)]),
        ("via", (68.2, 23.4)),
        ("B.Cu", [(68.2, 24.1), (68.2, 64.6), (61.7, 64.6)]),
        ("via", (61.0, 64.6)),
        ("F.Cu", [(60.3, 64.6), (52.0, 64.6), (51.4, 64.0), (50.6, 64.0)]),
    ]),
)

# 差分線旁邊的其他手佈件:(網, 層, 線寬, [點…]) 與過孔 (網, x, y)
EXTRA_TRACKS = (
    # U40 的 30 腳(LAN0_1V2)夾在 RX、TX 兩對之間,25 腳在 D 對南邊:各拉一小段打過孔,
    # 其餘(到去耦電容)交給 freerouting
    ("LAN0_1V2", "F.Cu", 0.2, [(49.6, 62.25), (51.1, 62.25)]),
    ("LAN0_1V2", "F.Cu", 0.2, [(49.6, 64.75), (50.4, 64.75), (50.4, 65.6)]),
    # M.2 地腳(51、45、39)→ 旁邊的地過孔
    ("GND", "F.Cu", 0.25, [(4.3, 11.75), (5.725, 11.75)]),
    ("GND", "F.Cu", 0.25, [(4.3, 13.25), (5.725, 13.25)]),
    ("GND", "F.Cu", 0.25, [(4.45, 14.75), (5.725, 14.75)]),
)
EXTRA_VIAS = (
    ("LAN0_1V2", 51.1, 62.25), ("LAN0_1V2", 50.4, 65.6),
    # M.2 奇數排的地腳夾在 PCIe 各對之間,外側被走線圍住:就地打到 In1
    ("GND", 4.3, 11.75), ("GND", 4.3, 13.25), ("GND", 4.45, 14.75),
)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def chamfer(pts, c: float = CHAMFER) -> list:
    """直角轉角切成 45°(切的長度不超過相鄰兩段各一半);其他角度不動。"""
    out = [pts[0]]
    for a, v, b in zip(pts, pts[1:], pts[2:]):
        d1, d2 = _unit(a, v), _unit(v, b)
        if abs(d1[0] * d2[0] + d1[1] * d2[1]) > 1e-9:
            out.append(v)
            continue
        k = min(c, math.dist(a, v) / 2, math.dist(v, b) / 2)
        out += [(v[0] - d1[0] * k, v[1] - d1[1] * k), (v[0] + d2[0] * k, v[1] + d2[1] * k)]
    return out + [pts[-1]]


def offset(pts, h: float) -> list:
    """往行進方向左側偏移 h(畫面座標 y 朝下:往東走時左側是北);轉角用斜接。"""
    out = []
    for i, v in enumerate(pts):
        ns = []
        if i > 0:
            d = _unit(pts[i - 1], v)
            ns.append((d[1], -d[0]))
        if i < len(pts) - 1:
            d = _unit(v, pts[i + 1])
            ns.append((d[1], -d[0]))
        if len(ns) == 1:
            n, s = ns[0], 1.0
        else:
            n = (ns[0][0] + ns[1][0], ns[0][1] + ns[1][1])
            s = 1 / (1 + ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1])
        out.append((v[0] + h * n[0] * s, v[1] + h * n[1] * s))
    return out


def _length(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _closer(p, n, a, b) -> bool:
    """端子 p、n 對到 a、b(而不是 b、a)比較近。"""
    return math.dist(p, a) + math.dist(n, b) <= math.dist(p, b) + math.dist(n, a)


def route(pair, start: dict, end: dict):
    """start / end:{"P": (x, y), "N": (x, y)}(焊盤中心)。
    回傳 (走線 [(網, 層, 線寬, [點…])], 過孔 [(網, x, y)], 長度 {"P", "N"}, 問題 [str])。"""
    name, pnet, nnet, cls, _, _, path = pair
    w, gap = CLASSES[cls]
    h = (w + gap) / 2
    tracks, vias, problems = [], [], []
    length = {"P": 0.0, "N": 0.0}
    term = start
    for k, item in enumerate(path):
        if item[0] == "via":
            continue
        layer, pts = item
        pts = chamfer(pts)
        left, right = offset(pts, h), offset(pts, -h)
        sp, sn = (left, right) if _closer(term["P"], term["N"], left[0], right[0]) else (right, left)
        if k + 1 < len(path):
            cx, cy = path[k + 1][1]
            d = _unit(pts[-2], pts[-1])
            u = (d[1] * VIA_PITCH / 2, -d[0] * VIA_PITCH / 2)  # 過孔對垂直於行進方向
            a, b = (cx + u[0], cy + u[1]), (cx - u[0], cy - u[1])
            nxt = {"P": a, "N": b} if _closer(sp[-1], sn[-1], a, b) else {"P": b, "N": a}
            vias += [(pnet, *nxt["P"]), (nnet, *nxt["N"])]
        else:
            nxt = end
            if not _closer(end["P"], end["N"], sp[-1], sn[-1]):
                problems.append(f"{name}:終點的 P/N 在行進方向的另一側(兩端手性相反,要扭轉)")
        for key, net, side in (("P", pnet, sp), ("N", nnet, sn)):
            line = [term[key]] + side + [nxt[key]]
            tracks.append((net, layer, w, line))
            length[key] += _length(line)
        term = nxt
    skew = abs(length["P"] - length["N"])
    if skew > SKEW_MAX:
        short = pnet if length["P"] < length["N"] else nnet
        if _compensate(tracks, short, pnet if short == nnet else nnet, skew):
            length = {k: sum(_length(t[3]) for t in tracks if t[0] == net)
                      for k, net in (("P", pnet), ("N", nnet))}
            skew = abs(length["P"] - length["N"])
        if skew > SKEW_MAX:
            problems.append(f"{name}:對內長度差 {skew:.3f} mm > {SKEW_MAX} mm")
    return tracks, vias, length, problems


BUMP_MAX = 0.25      # 補長凸起的高度上限(對與對之間至少 0.52 mm,凸起後仍 ≥ 0.27)
BUMP_TOP = 0.5       # 凸起頂部長度
BUMP_GAP = 0.6       # 凸起之間


def _dist_to_line(p, line) -> float:
    best = math.inf
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        best = min(best, math.dist(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def _compensate(tracks, short: str, other: str, skew: float) -> bool:
    """在較短那條線最長的水平 / 垂直段上加 45° 梯形凸起(朝遠離另一條的方向)補長度。

    每個凸起多出 2a(√2 − 1)(a 為高度);個數取 a ≤ BUMP_MAX 的最少個,a 依此算到剛好補齊。"""
    per = 2 * (math.sqrt(2) - 1)
    n = math.ceil(skew / (per * BUMP_MAX))
    a = skew / (n * per)
    need = n * (2 * a + BUMP_TOP) + (n - 1) * BUMP_GAP + 2  # 兩端各留 1 mm
    best = None
    for ti, (net, layer, w, line) in enumerate(tracks):
        if net != short:
            continue
        partner = [p for t in tracks if t[0] == other and t[1] == layer for p in t[3]]
        for si, (p, q) in enumerate(zip(line, line[1:])):
            L = math.dist(p, q)
            axis = abs(p[0] - q[0]) < 1e-9 or abs(p[1] - q[1]) < 1e-9
            if axis and L >= need and partner and (best is None or L > best[0]):
                best = (L, ti, si, partner)
    if best is None:
        return False
    L, ti, si, partner = best
    net, layer, w, line = tracks[ti]
    p, q = line[si], line[si + 1]
    d = _unit(p, q)
    mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    nrm = (d[1], -d[0])
    probe = lambda s: _dist_to_line((mid[0] + s * nrm[0] * 0.5, mid[1] + s * nrm[1] * 0.5), partner)  # noqa: E731
    if probe(1) < probe(-1):
        nrm = (-nrm[0], -nrm[1])
    span = n * (2 * a + BUMP_TOP) + (n - 1) * BUMP_GAP
    s0 = (L - span) / 2
    pts = []
    for i in range(n):
        s = s0 + i * (2 * a + BUMP_TOP + BUMP_GAP)
        for along, out in ((s, 0), (s + a, a), (s + a + BUMP_TOP, a), (s + 2 * a + BUMP_TOP, 0)):
            pts.append((p[0] + d[0] * along + nrm[0] * out, p[1] + d[1] * along + nrm[1] * out))
    tracks[ti] = (net, layer, w, line[:si + 1] + pts + line[si + 1:])
    return True


def dru() -> str:
    """對內間距比網路類別的 0.2 mm 小:每一對加一條規則(座標取到 nm 會有捨入,下限留 0.01 mm)。"""
    out = []
    for name, p, n, cls, *_ in PAIRS:
        gap = CLASSES[cls][1] - 0.01
        out.append(f'(rule "diff pair {name}"\n'
                   f'  (condition "(A.NetName == \'{p}\' && B.NetName == \'{n}\') || '
                   f'(A.NetName == \'{n}\' && B.NetName == \'{p}\')")\n'
                   f'  (constraint clearance (min {gap:g}mm)))\n')
    return "".join(out)


def keepouts() -> list:
    """自動擺件的禁區:F.Cu 上每段中心線(含兩側)的外接框、每個過孔周圍。"""
    out = []
    vias = [(x, y) for _, x, y in EXTRA_VIAS]
    for name, pnet, nnet, cls, _, _, path in PAIRS:
        w, gap = CLASSES[cls]
        r = gap / 2 + w + KEEP
        for k, item in enumerate(path):
            if item[0] == "via":
                vias.append(item[1])
            elif item[0] == "F.Cu":
                for (xa, ya), (xb, yb) in zip(item[1], item[1][1:]):
                    out.append((min(xa, xb) - r, min(ya, yb) - r, max(xa, xb) + r, max(ya, yb) + r))
    for _, layer, w, pts in EXTRA_TRACKS:
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            r = w / 2 + KEEP
            out.append((min(xa, xb) - r, min(ya, yb) - r, max(xa, xb) + r, max(ya, yb) + r))
    r = VIA_PITCH / 2 + 0.3 + KEEP
    out += [(x - r, y - r, x + r, y + r) for x, y in vias]
    return out
