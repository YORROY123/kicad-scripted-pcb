"""市电区:汇流排、走线、开槽、禁止区与 DRC 规则(v2:板上 AC-DC,一条市电线供全部)。

板子 y 向下,下面的 y 都是板框坐标(pcbgen.ORIGIN 之上的偏移)。

  上缘 y = TERM_Y   J20 输入(L、N)+ 8 个输出端子(NO · N · NC,转 180°,接线口朝上缘)
  N_BUS 汇流排      B.Cu,中心 N_BUS_Y,宽 BUS_W:J20 的 N → 每路端子中间那格
  L_BUS 汇流排      B.Cu,中心 L_BUS_Y,宽 BUS_W:F1 之后 → 8 个继电器 COM
  继电器             转 90°,触点朝上;COM 从 B.Cu 往上接 L_BUS,穿过两个线圈脚之间
  NO / NC            F.Cu,从触点往上跨过两条汇流排(不同层,隔着板材)接到端子
  左侧输入区         J20 → F1(T8A)→ F2(T1A)→ PS1 HLK-10M05;RV1 跨在 L_BUS 与 N_BUS 上

间距(IEC 62368-1 量级,250VAC、污染等级 2;只是设计目标,不是认证):
  - 市电 ↔ 低压:空气间隙 ≥ 3.0mm(DRC 规则);爬电 ≥ 5mm 靠 COM 走线两侧的槽
  - 市电 ↔ 市电(不同网):≥ 2.4mm
  - 汇流排 6.5mm(1oz 约 8A)→ F1 = T8A,总电流 8A;每路 NO/NC 3.5mm、COM 3.0mm → 每路 5A
"""
import pcbnew
from pcbgen import ORIGIN

TERM_Y = 5.6
N_BUS_Y = 12.85
L_BUS_Y = 22.15
BUS_W = 6.5
SWITCH_W = 3.5      # NO / NC
RISER_W = 3.0       # COM 与 N 的竖线
INPUT_W = 3.5       # J20 → F1 → F2 的 L
PS_W = 1.5          # 送 PS1 的 L_PS 与 N(PS1 只吃 ~0.1A)
SLOT_X = (2.3, 3.3)     # 槽相对 COM 的 x 范围(两侧对称),宽 1mm
SLOT_Y = (-6.0, 4.2)    # 槽相对 COM 的 y 范围:上端超过线圈焊盘,下端超过 COM 焊盘

LABELS = {"N_BUS": "N", "L_IN": "L"}    # 其余网取最后一段:RL3_NO → "NO"


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def board_y(y: float) -> float:
    return ORIGIN[1] + y


def _vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def fps(board) -> dict:
    return {fp.GetReference(): fp for fp in board.GetFootprints()}


def channels(board):
    """[(继电器, 端子台)],按通道号排序。"""
    f = fps(board)
    return [(f[f"K{ch}"], f[f"J{10 + ch}"]) for ch in range(1, 9)]


def pad_xy(fp, number: str, toward=None) -> tuple[float, float]:
    """焊盘中心(绝对坐标 mm)。同号多焊盘(保险丝夹)时取离 toward 最近的那个。"""
    pads = [p for p in fp.Pads() if p.GetNumber() == number]
    pts = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in pads]
    if toward is None or len(pts) == 1:
        return pts[0]
    return min(pts, key=lambda q: (q[0] - toward[0]) ** 2 + (q[1] - toward[1]) ** 2)


def _track(board, a, b, net: str, width: float, layer) -> None:
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(_vec(*a))
    t.SetEnd(_vec(*b))
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(board.FindNet(net))
    board.Add(t)


def _net_of(fp, number: str) -> str:
    return next(p.GetNetname() for p in fp.Pads() if p.GetNumber() == number)


def mains_nets(board) -> set:
    return {n for n in (board.GetNetInfo().GetNetItem(i).GetNetname()
                        for i in range(board.GetNetInfo().GetNetCount()))
            if n.startswith(("RL", "L_", "N_BUS")) and not n.startswith("RLY")}


def add_mains_tracks(board) -> int:
    """全部市电铜:汇流排、每路 COM/N 竖线与 NO/NC、输入区。先删掉市电网上已有的走线,可重复执行。"""
    nets = mains_nets(board)
    for t in list(board.GetTracks()):
        if t.GetNetname() in nets:
            board.Delete(t)     # 不用 Remove,见 lib/route.py import_ses 的说明
    f = fps(board)
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    n_y, l_y = board_y(N_BUS_Y), board_y(L_BUS_Y)
    segs = []

    xs = []
    for relay, term in channels(board):
        com = pad_xy(relay, "1")
        xs.append(com[0])
        segs.append((com, (com[0], l_y), "L_BUS", RISER_W, B))                    # COM → L_BUS
        npin = pad_xy(term, "2")
        segs.append((npin, (npin[0], n_y), "N_BUS", RISER_W, B))                  # 端子 N → N_BUS
        for relay_pin, term_pin in (("3", "1"), ("4", "3")):                      # NO、NC
            net = _net_of(relay, relay_pin)
            assert net == _net_of(term, term_pin), (relay.GetReference(), relay_pin)
            segs.append((pad_xy(relay, relay_pin), pad_xy(term, term_pin), net, SWITCH_W, F))

    j20, f1, f2, ps1, rv1 = f["J20"], f["F1"], f["F2"], f["PS1"], f["RV1"]
    l_in, n_in = pad_xy(j20, "1"), pad_xy(j20, "2")
    f2a, f2b = pad_xy(f2, "1"), pad_xy(f2, "2")
    # 汇流排:N 从 J20 的 N 到第 8 路;L 从 F2 那一列到第 8 路
    segs.append(((n_in[0], n_y), (xs[-1], n_y), "N_BUS", BUS_W, B))
    segs.append(((f2a[0], l_y), (xs[-1], l_y), "L_BUS", BUS_W, B))
    segs.append((n_in, (n_in[0], n_y), "N_BUS", RISER_W, B))                      # J20 N → N_BUS
    # L:J20 → F1 → L 汇流排竖线(全部负载电流)。F2 只从竖线下端用细线分接(PS1 吃 ~0.1A):
    # 第一版让 3.5mm 竖线一路接到 F2 的 1 脚,离 F2 的 2 脚(L_PS)只剩 2.33mm,TR5 脚距才 5.1mm。
    f1a = pad_xy(f1, "1", toward=l_in)
    f1b = pad_xy(f1, "2", toward=f2a)
    corner = (f2a[0], f1b[1])
    segs.append((l_in, f1a, "L_IN", INPUT_W, F))
    segs.append((f1b, corner, "L_BUS", INPUT_W, B))
    segs.append(((f2a[0], l_y), corner, "L_BUS", INPUT_W, B))
    segs.append((corner, f2a, "L_BUS", PS_W, B))
    segs.append((f2b, pad_xy(ps1, "1"), "L_PS", PS_W, F))
    segs.append((n_in, pad_xy(ps1, "2"), "N_BUS", PS_W, F))
    # 保险丝每个脚有两片夹子(两个同号焊盘),铜上也要连起来
    for fuse_pin in ("1", "2"):
        c0, c1 = [p for p in f1.Pads() if p.GetNumber() == fuse_pin]
        a = (pcbnew.ToMM(c0.GetPosition().x), pcbnew.ToMM(c0.GetPosition().y))
        b = (pcbnew.ToMM(c1.GetPosition().x), pcbnew.ToMM(c1.GetPosition().y))
        segs.append((a, b, c0.GetNetname(), INPUT_W, B))
    # RV1 的两个脚放在两条汇流排上,焊盘本身压在汇流排铜上即连通,不另拉线
    for pin, net in (("1", "L_BUS"), ("2", "N_BUS")):
        assert _net_of(rv1, pin) == net, ("RV1", pin)

    for a, b, net, width, layer in segs:
        _track(board, a, b, net, width, layer)
    return len(segs)


def add_slots(board) -> int:
    """COM 走线两侧各一道 1mm 槽(Edge.Cuts 内部开口),拉长市电到线圈的爬电距离。"""
    n = 0
    for relay, _term in channels(board):
        cx, cy = pad_xy(relay, "1")
        for sign in (-1, 1):
            x0, x1 = sorted((cx + sign * SLOT_X[0], cx + sign * SLOT_X[1]))
            y0, y1 = cy + SLOT_Y[0], cy + SLOT_Y[1]
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            for a, b in zip(corners, corners[1:] + corners[:1]):
                seg = pcbnew.PCB_SHAPE(board)
                seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
                seg.SetLayer(pcbnew.Edge_Cuts)
                seg.SetWidth(mm(0.1))
                seg.SetStart(_vec(*a))
                seg.SetEnd(_vec(*b))
                board.Add(seg)
            n += 1
    return n


def add_terminal_labels(board, below_pads: float) -> int:
    """在每个市电端子焊盘下方印该脚的功能(L / N / NO / NC)。

    文字取自焊盘实际所在的网,不是写死的顺序:接线的人只看得到板面,丝印必须跟电路一致。
    位号(J11…、J20)让给标签,移到 F.Fab。
    """
    f = fps(board)
    terms = [term for _relay, term in channels(board)] + [f["J20"]]
    n = 0
    for term in terms:
        term.Reference().SetLayer(pcbnew.F_Fab)
        for pad in term.Pads():
            x, y = pad_xy(term, pad.GetNumber())
            net = pad.GetNetname()
            _silk_text(board, LABELS.get(net, net.split("_")[-1]), x, y + below_pads, 1.2)
            n += 1
    return n


def _silk_text(board, text: str, x: float, y: float, size: float) -> None:
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(_vec(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    board.Add(t)


def _rule_area(board, pts, name, *, no_tracks: bool, no_fill: bool) -> None:
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    z.SetDoNotAllowTracks(no_tracks)
    z.SetDoNotAllowVias(no_tracks)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowZoneFills(no_fill)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(_vec(x, y))
    board.Add(z)


def _mains_regions(board, width: float, margin: float):
    """市电区多边形(绝对坐标):上缘整条(端子 + 两条汇流排 + 触点)、每路 COM 走廊、左侧输入区。

    margin 往外扩:布线禁止区用 0(另有走廊半宽),铺铜禁止区用 3 —— GND 铺铜离市电 ≥ 3mm。
    """
    f = fps(board)
    x0, y0 = ORIGIN
    contacts_bottom = max(pad_xy(r, "3")[1] for r, _t in channels(board)) + 1.5
    strip_bottom = contacts_bottom + 4.5 + margin
    regions = [[(x0, y0), (x0 + width, y0), (x0 + width, strip_bottom), (x0, strip_bottom)]]
    for relay, _term in channels(board):
        cx, cy = pad_xy(relay, "1")
        half = 4.8 if margin == 0 else 4.6
        bottom = cy + (4.8 if margin == 0 else 5.0)
        regions.append([(cx - half, strip_bottom), (cx + half, strip_bottom),
                        (cx + half, bottom), (cx - half, bottom)])
    # 输入区:到 PS1 的 AC 脚下方;PS1 的 DC 端(低压)不在里面
    ac_y = max(pad_xy(f["PS1"], p)[1] for p in ("1", "2"))
    right = max(pad_xy(f["RV1"], p)[0] for p in ("1", "2")) + 4.0 + margin
    regions.append([(x0, y0), (right, y0), (right, ac_y + 6 + margin), (x0, ac_y + 6 + margin)])
    return regions


def add_routing_keepouts(board, width: float) -> None:
    """布线前:低压走线/过孔不得进入市电区(freerouting 遵守 DSN 里的 keepout)。"""
    for i, pts in enumerate(_mains_regions(board, width, 0.0)):
        _rule_area(board, pts, f"mains_route_{i}", no_tracks=True, no_fill=True)


def add_fill_keepouts(board, width: float) -> None:
    """布线后:GND 铺铜离市电 ≥ 3mm;市电走线本身允许在区内。"""
    for i, pts in enumerate(_mains_regions(board, width, 3.0)):
        _rule_area(board, pts, f"mains_nofill_{i}", no_tracks=False, no_fill=True)


DRU = """(version 1)
# 市电与低压之间的空气间隙(爬电另靠开槽)。只是设计目标,不是安规认证。
(rule "mains_to_lv"
  (condition "A.NetClass == 'Mains' && B.NetClass != 'Mains'")
  (constraint clearance (min 3.0mm)))
# 不同市电网之间(L 与 N、同一路的 NO/NC、相邻两路)
(rule "mains_to_mains"
  (condition "A.NetClass == 'Mains' && B.NetClass == 'Mains' && A.Net != B.Net")
  (constraint clearance (min 2.4mm)))
"""
