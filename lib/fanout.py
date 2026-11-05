"""平面网络的扇出(dogbone):SMD 焊盘旁放一个过孔 + 一段短线,锁定,接到内层平面。

freerouting 2.5.0 的扇出是让焊盘往平面层逃;平面层用 use_layer 排除走线后(lib/route.py
plane_layers_off),它一个过孔都不打,平面网络的焊盘就接不上(cm5:扇出 +0 过孔、49 个
GND / +3V3 焊盘没接)。所以平面网络先在这里扇好,freerouting 只布其余的线。

规则(每个候选位置都查,已放下的过孔也算进去):
- 只处理还没接到同网平面的 SMD 焊盘(电源级、供电支线已经接好的跳过)。
- 过孔中心要在该网平面填充后的铜上(+3V3 不能落在 In2 的 +5V 区)。
- 过孔与短线和异网的铜(外层焊盘、走线、过孔)保持网络类别间距;孔与孔 >= HOLE_GAP;
  过孔不进其他器件的 courtyard;不压在自己的焊盘上(不做盘中孔)。
- 优先离器件中心较远的方向(往外逃),同方向取最近。
- 散热焊盘(QFN 底部,两边 >= EP_MIN):焊盘内打 EP_PITCH 间距的过孔阵列(这时允许盘中孔)。
"""
import math

import pcbnew

STEP = 0.05          # 搜索格距 mm
R_MIN, R_MAX = 0.35, 3.0  # 过孔中心离焊盘中心的距离范围 mm(0.4mm 连接器要往远处错开)
# 散热焊盘(QFN 底部):接近正方形、边长 EP_MIN–EP_MAX mm;焊盘内打最多 EP_N × EP_N 个过孔。
# 电池座(17.8 mm)、电解电容(4.0 × 2.5)这种大焊盘不算,照一般焊盘扇出。
EP_MIN, EP_MAX = 2.5, 6.0
EP_N = 3
EP_PITCH = 1.2       # 散热过孔间距 mm(上限;焊盘小时缩小)
HOLE_GAP = 0.25      # 孔边到孔边 mm(JLC 0.25)


def _mm(v):
    return v / 1e6


def _nm(v):
    return int(round(v * 1e6))


def _seg(a, b, w):
    return pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(_nm(a[0]), _nm(a[1])),
                                pcbnew.VECTOR2I(_nm(b[0]), _nm(b[1])), _nm(w))


def fanout(board, plane_layer_of: dict, via_d: float, via_drill: float, width_of, clearance_of) -> dict:
    """plane_layer_of: {网名: pcbnew 层 id};width_of / clearance_of(网名) -> mm。

    回传 {"placed": n, "skipped": [焊盘名…](找不到位置)}。放下的过孔与走线都锁定。"""
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    conn = board.GetConnectivity()

    obstacles = []  # (layer, net, shape, 外接框 mm (x0, y0, x1, y1))

    def add_obstacle(L, net, shape):
        bb = shape.BBox()
        obstacles.append((L, net, shape, (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()))))

    for t in board.GetTracks():
        for L in (F, B):
            if t.IsOnLayer(L):
                add_obstacle(L, t.GetNetname(), t.GetEffectiveShape(L))
    for p in board.GetPads():
        for L in (F, B):
            if p.IsOnLayer(L):
                add_obstacle(L, p.GetNetname(), p.GetEffectiveShape(L))
    holes = []
    for p in board.GetPads():
        if p.HasHole():
            holes.append((_mm(p.GetX()), _mm(p.GetY()), _mm(max(p.GetDrillSizeX(), p.GetDrillSizeY())) / 2))
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            holes.append((_mm(t.GetX()), _mm(t.GetY()), _mm(t.GetDrillValue()) / 2))
    courtyards = [(fp.GetReference(), fp.GetCourtyard(F)) for fp in board.GetFootprints()
                  if fp.GetCourtyard(F).OutlineCount()]
    planes = {}
    for z in board.Zones():
        if z.GetLayer() in plane_layer_of.values() and not z.GetIsRuleArea():
            planes.setdefault((z.GetNetname(), z.GetLayer()), []).append(z.GetFilledPolysList(z.GetLayer()))

    near = []

    other_gap = {}

    def clear(shape, layer, net, gap):
        # 间距取两边网络类别较大的(例:PoE 0.25)
        for L, n, s in near:
            if L != layer or n == net:
                continue
            g = other_gap.setdefault(n, clearance_of(n) if n else 0.0)
            if s.Collide(shape, _nm(max(gap, g))):
                return False
        return True

    def on_plane(net, x, y):
        pt = pcbnew.VECTOR2I(_nm(x), _nm(y))
        return any(f.Contains(pt) for f in planes.get((net, plane_layer_of[net]), []))

    placed, skipped = 0, []
    pads = sorted((p for p in board.GetPads()
                   if p.GetNetname() in plane_layer_of and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                   and p.IsOnLayer(F)),
                  key=lambda p: (p.GetParentFootprint().GetReference(), p.GetNumber()))
    for pad in pads:
        net = pad.GetNetname()
        name = f"{pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}"
        if any(z.GetClass() == "ZONE" and z.GetLayer() == plane_layer_of[net]
               for z in conn.GetConnectedItems(pad)):
            continue
        fp = pad.GetParentFootprint()
        px, py = _mm(pad.GetX()), _mm(pad.GetY())
        sx, sy = _mm(pad.GetBoundingBox().GetWidth()), _mm(pad.GetBoundingBox().GetHeight())
        if EP_MIN <= min(sx, sy) and max(sx, sy) <= EP_MAX and max(sx, sy) / min(sx, sy) < 1.2:
            reach = max(sx, sy)
            near[:] = [(L, n, sh) for L, n, sh, (x0, y0, x1, y1) in obstacles
                       if x0 < px + reach and x1 > px - reach and y0 < py + reach and y1 > py - reach]
            pitch = min(EP_PITCH, (min(sx, sy) - via_d - 0.4) / (EP_N - 1))
            nx = ny = EP_N
            n_ep = 0
            for i in range(nx):
                for j in range(ny):
                    x = px + (i - (nx - 1) / 2) * pitch
                    y = py + (j - (ny - 1) / 2) * pitch
                    via = _seg((x, y), (x, y), via_d)
                    if not on_plane(net, x, y) or not clear(via, B, net, clearance_of(net)):
                        continue
                    if any(math.hypot(x - hx, y - hy) < hr + via_drill / 2 + HOLE_GAP for hx, hy, hr in holes):
                        continue
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I(_nm(x), _nm(y)))
                    v.SetWidth(_nm(via_d))
                    v.SetDrill(_nm(via_drill))
                    v.SetNet(pad.GetNet())
                    v.SetLocked(True)
                    board.Add(v)
                    add_obstacle(B, net, v.GetEffectiveShape(B))
                    holes.append((x, y, via_drill / 2))
                    n_ep += 1
            if n_ep:
                placed += n_ep
                # 走线接到 EP 的脚(例:cm5 U10 6、8 脚)排在 EP 后面,要看得到新的散热过孔
                board.BuildConnectivity()
                conn = board.GetConnectivity()
                continue
        cx, cy = _mm(fp.GetX()), _mm(fp.GetY())
        own = pad.GetEffectiveShape(F)
        gap, w = clearance_of(net), width_of(net)
        # 短线不比焊盘窄边宽:0.4 mm 脚距的连接器(焊盘 0.2)用 0.25 的线,离隔壁脚只剩 0.175
        w = min(w, min(sx, sy) - 0.01)
        reach = R_MAX + via_d + 1.0
        near[:] = [(L, n, sh) for L, n, sh, (x0, y0, x1, y1) in obstacles
                   if x0 < px + reach and x1 > px - reach and y0 < py + reach and y1 > py - reach]
        best = None
        steps = int(R_MAX / STEP)
        for i in range(-steps, steps + 1):
            for j in range(-steps, steps + 1):
                x, y = px + i * STEP, py + j * STEP
                d = math.hypot(x - px, y - py)
                if not (R_MIN <= d <= R_MAX):
                    continue
                # 往外:与「器件中心→焊盘」方向的夹角越小越好;同一档取近的
                ox, oy = px - cx, py - cy
                cos = ((x - px) * ox + (y - py) * oy) / (d * (math.hypot(ox, oy) or 1))
                score = (round(1 - cos, 1), d)
                if best and score >= best[0]:
                    continue
                via = _seg((x, y), (x, y), via_d)
                if own.Collide(via, 0):
                    continue
                if any(math.hypot(x - hx, y - hy) < hr + via_drill / 2 + HOLE_GAP for hx, hy, hr in holes):
                    continue
                pt = pcbnew.VECTOR2I(_nm(x), _nm(y))
                if any(ref != fp.GetReference() and c.Contains(pt) for ref, c in courtyards):
                    continue
                if not on_plane(net, x, y):
                    continue
                if not (clear(via, F, net, gap) and clear(via, B, net, gap)):
                    continue
                if not clear(_seg((px, py), (x, y), w), F, net, gap):
                    continue
                best = (score, x, y)
        if best is None:
            skipped.append(name)
            continue
        _, x, y = best
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(_nm(x), _nm(y)))
        v.SetWidth(_nm(via_d))
        v.SetDrill(_nm(via_drill))
        v.SetNet(pad.GetNet())
        v.SetLocked(True)
        board.Add(v)
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(F)
        t.SetStart(pad.GetPosition())
        t.SetEnd(v.GetPosition())
        t.SetWidth(_nm(w))
        t.SetNet(pad.GetNet())
        t.SetLocked(True)
        board.Add(t)
        for L in (F, B):
            add_obstacle(L, net, v.GetEffectiveShape(L))
        add_obstacle(F, net, t.GetEffectiveShape(F))
        holes.append((x, y, via_drill / 2))
        placed += 1
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())  # 平面要让开新的过孔
    return {"placed": placed, "skipped": skipped}
