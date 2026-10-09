"""市电区:走线、开槽、禁止区与 DRC 规则。pcb.py 与布线后的收尾步骤共用。

几何(每路一栏,栏中心 xc,板子 y 向下):
  端子台(转 180°,接线口朝上缘)  pin1 NO @ xc+5.08、pin2 COM @ xc、pin3 NC @ xc−5.08,y = TERM_Y
  继电器(转 90°)                  COM @ (xc, RELAY_Y);线圈 2/5 @ (xc±6, RELAY_Y−1.95);
                                    NO @ (xc+6.05, RELAY_Y−14.15)、NC @ (xc−6, RELAY_Y−14.2)
  COM 走线从继电器 COM 垂直往上,穿过两个线圈脚之间、再从 NO/NC 之间到端子。

间距(IEC 62368-1 量级,250VAC、污染等级 2;只是设计目标,不是认证):
  - 市电 ↔ 低压:空气间隙 ≥ 3.0mm(DRC 规则);爬电 ≥ 5mm 靠 COM 走线两侧的槽:
    COM 走线到线圈焊盘的板面路径必须绕过槽的两端
  - 市电 ↔ 市电(不同网):≥ 2.4mm,即端子台本身 5.08mm 脚距留下的间隙
  - 市电走线 2.5mm、上下两层并联:1oz 约 6A → 本板每路额定 5A(继电器本身 10A)
"""
import pcbnew

MAINS_W = 2.5
SLOT_X = (2.3, 3.3)         # 槽相对栏中心的 x 范围(两侧对称),宽 1mm
SLOT_Y = (-6.0, 4.2)        # 槽相对继电器 COM 的 y 范围:上端超过线圈焊盘,下端超过 COM 焊盘


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def _vec(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def channels(board):
    """[(继电器, 端子台)],按通道号排序。"""
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    return [(fps[f"K{ch}"], fps[f"J{10 + ch}"]) for ch in range(1, 9)]


def pad_xy(fp, number: str) -> tuple[float, float]:
    p = fp.FindPadByNumber(number).GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def add_mains_tracks(board) -> int:
    """继电器 COM/NO/NC → 端子台,上下两层各一条。先删掉这些网上已有的走线,可重复执行。"""
    mains_nets = {f"RL{ch}_{t}" for ch in range(1, 9) for t in ("COM", "NO", "NC")}
    for t in list(board.GetTracks()):
        if t.GetNetname() in mains_nets:
            board.Delete(t)     # 不用 Remove,见 route.py import_ses 的说明
    count = 0
    for relay, term in channels(board):
        for relay_pin, term_pin in (("1", "2"), ("3", "1"), ("4", "3")):
            a = relay.FindPadByNumber(relay_pin)
            b = term.FindPadByNumber(term_pin)
            assert a.GetNetname() == b.GetNetname(), (relay.GetReference(), relay_pin)
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(a.GetPosition())
                t.SetEnd(b.GetPosition())
                t.SetWidth(mm(MAINS_W))
                t.SetLayer(layer)
                t.SetNet(a.GetNet())
                board.Add(t)
                count += 1
    return count


def add_slots(board) -> int:
    """COM 走线两侧各一道 1mm 槽(Edge.Cuts 内部开口),拉长市电到线圈的爬电距离。"""
    n = 0
    for relay, _term in channels(board):
        cx, cy = pad_xy(relay, "1")
        for sign in (-1, 1):
            x0, x1 = sorted((cx + sign * SLOT_X[0], cx + sign * SLOT_X[1]))
            y0, y1 = cy + SLOT_Y[0], cy + SLOT_Y[1]
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
                seg = pcbnew.PCB_SHAPE(board)
                seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
                seg.SetLayer(pcbnew.Edge_Cuts)
                seg.SetWidth(mm(0.1))
                seg.SetStart(_vec(ax, ay))
                seg.SetEnd(_vec(bx, by))
                board.Add(seg)
            n += 1
    return n


def add_terminal_labels(board, below_pads: float) -> int:
    """在每个端子焊盘下方 below_pads mm 处印 NO / COM / NC。

    文字取自焊盘实际所在的网(RL3_NO → "NO"),不是写死的顺序:接线的人只看得到
    板面,丝印必须跟电路一致,改了接法丝印也跟着变。坐标相对焊盘(板上的绝对坐标),
    第一版传了板框坐标,字全印到了板外 —— DRC 不查「字在不在该在的地方」,是放大
    渲染图才看出来的。端子的位号(J11…)让给标签,移到 F.Fab。
    """
    # 通道由继电器旁的 K1…K8 位号标识;再印一行 CH1… 会压到继电器丝印外框。
    n = 0
    for _relay, term in channels(board):
        term.Reference().SetLayer(pcbnew.F_Fab)
        for pad in term.Pads():
            x, y = pad_xy(term, pad.GetNumber())
            _silk_text(board, pad.GetNetname().split("_")[-1], x, y + below_pads, 1.2)
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


def _mains_outline(board, relay, *, top_extra: float, corridor: float, bottom: float):
    """一栏的市电区多边形:上半部整栏(端子 + 触点),下半部只有 COM 走廊。"""
    cx, cy = pad_xy(relay, "1")
    top_bottom = cy - 14.2 + top_extra      # 触点焊盘中心往下 top_extra
    return [
        (cx - 9, 0), (cx + 9, 0), (cx + 9, top_bottom), (cx + corridor, top_bottom),
        (cx + corridor, cy + bottom), (cx - corridor, cy + bottom),
        (cx - corridor, top_bottom), (cx - 9, top_bottom),
    ]


def add_routing_keepouts(board) -> None:
    """布线前:低压走线/过孔不得进入市电区(freerouting 遵守 DSN 里的 keepout)。"""
    for relay, _term in channels(board):
        # 走廊半宽 4.8:COM 焊盘半径 1.5 + 3.0 间距 + 余量,也盖住两侧的槽(x 2.3…3.3)
        # 与槽边 0.5mm。正好到线圈焊盘内缘(6.05 − 1.25),线圈仍可从外侧接线。
        # 第一版用 3.6,freerouting 把 DC_IN 布到离 COM 焊盘 2.75mm,线圈线贴着槽角 0.42mm。
        pts = _mains_outline(board, relay, top_extra=6.0, corridor=4.8, bottom=4.8)
        _rule_area(board, pts, f"mains_route_{relay.GetReference()}", no_tracks=True, no_fill=True)


def add_fill_keepouts(board) -> None:
    """布线后:GND 铺铜离市电 ≥ 3mm;市电走线本身允许在区内。"""
    for relay, _term in channels(board):
        pts = _mains_outline(board, relay, top_extra=8.5, corridor=4.6, bottom=5.0)
        _rule_area(board, pts, f"mains_nofill_{relay.GetReference()}", no_tracks=False, no_fill=True)


DRU = """(version 1)
# 市电与低压之间的空气间隙(爬电另靠开槽)。只是设计目标,不是安规认证。
(rule "mains_to_lv"
  (condition "A.NetClass == 'Mains' && B.NetClass != 'Mains'")
  (constraint clearance (min 3.0mm)))
# 不同市电网之间(同一路的 NO/COM/NC、相邻两路):端子台 5.08mm 脚距留下的间隙
(rule "mains_to_mains"
  (condition "A.NetClass == 'Mains' && B.NetClass == 'Mains' && A.Net != B.Net")
  (constraint clearance (min 2.4mm)))
"""
