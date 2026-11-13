"""freerouting 的 .ses → 写回 .kicad_pcb,再铺双面 GND。

流程(都用 KiCad 自带的 python.exe):
    pcbgen.py            网表 → usbc-ldo.kicad_pcb(放件、板框、规则)
    route.py dsn         导出 usbc-ldo.dsn
    freerouting          usbc-ldo.dsn → usbc-ldo.ses
    route.py ses         导入 .ses、铺 GND、填充、存档(板上原有的铜区,如内层电源平面,保留)

freerouting 2.5.0 的原生 CLI 在 KiCad 10 的 DSN 上会崩(上游 #957),
用 jar 版 + Java 25:
    tools/jre/<jre>/bin/java.exe -jar tools/freerouting/freerouting-2.5.0.jar \
        -de usbc-ldo.dsn -do usbc-ldo.ses --router.autorouter.max_passes=30 \
        --gui.enabled=false
"""
import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcbgen import mm, stable_uuids  # noqa: E402


def export_dsn(pcb: Path, dsn: Path, only: set = None) -> None:
    board = pcbnew.LoadBoard(str(pcb))
    stable_uuids(board, pcb.stem)  # DSN 照 UUID 排序:汇出前统一
    board.Save(str(pcb))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("ExportSpecctraDSN 失败")
    text = dsn.read_text(encoding="utf-8")
    if any(not z.GetIsRuleArea() for z in board.Zones()):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())  # 只为了读填充范围;不存档
        text = filled_planes(text, board)
        print("  铜区照填充后的范围汇出(plane)")
    planes = [board.GetLayerName(lid) for lid in board.GetEnabledLayers().CuStack()
              if board.GetLayerType(lid) == pcbnew.LT_POWER]
    if planes:
        signal = [board.GetLayerName(lid) for lid in board.GetEnabledLayers().CuStack()
                  if board.GetLayerType(lid) != pcbnew.LT_POWER]
        text = plane_layers_off(text, planes, signal)
        print(f"  {', '.join(planes)}:只接平面、不走线(use_layer {' '.join(signal)})")
    if only:
        text = only_nets(text, only, grow=lambda base: grown_obstacles(board, only, base))
        print(f"  只布 {len(only)} 个网:{' '.join(sorted(only))}")
    dsn.write_text(text, encoding="utf-8")
    print(f"wrote {dsn.name}")


PLANE_RE = re.compile(r"\n[ \t]*\(plane \S+ \(polygon [^()]*\)\)")
MIN_PLANE_MM2 = 0.05


def filled_planes(text: str, board) -> str:
    """DSN 的 (plane 网 (polygon …)) 换成每个铜区填充后的外轮廓(每个岛一个 plane)。

    KiCad 汇出的是铜区的外框。外框边上的铜常常因为让开别的网(焊盘、过孔的间距)而填不到,
    freerouting 却以为那里有铜,会把走线接到外框边上:导入后 KiCad 重新填充,那段线就悬空
    (cm5 第一次 30 轮:+5V 支线、U62 鋪銅旁的 +5V 线都这样断开)。填充的洞(让开的过孔)不汇出:
    洞里本来就是别的网的东西,freerouting 不会在那里接。"""
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        net = z.GetNetname()
        q = f'"{net}"' if re.search(r'[\s()"]', net) else net
        for lid in z.GetLayerSet().CuStack():
            fill = z.GetFilledPolysList(lid)
            for i in range(fill.OutlineCount()):
                ol = fill.Outline(i)
                if abs(ol.Area()) / 1e12 < MIN_PLANE_MM2:
                    continue
                pts = [ol.CPoint(j) for j in range(ol.PointCount())] + [ol.CPoint(0)]
                xy = "  ".join(f"{p.x / 1000:g} {-p.y / 1000:g}" for p in pts)
                out.append(f"\n    (plane {q} (polygon {board.GetLayerName(lid)} 0  {xy}))")
    found = PLANE_RE.findall(text)
    if not found:
        raise SystemExit("DSN 里没有 (plane …),板上却有铜区")
    first = text.index(found[0])
    text = PLANE_RE.sub("", text)
    return text[:first] + "".join(out) + text[first:]


TOKEN_RE = re.compile(r'\(|\)|"[^"]*"|[^\s()]+')
QUOTE = '(string_quote ")'


def sexp_parse(text: str) -> list:
    """DSN → 巢状 list(字串原样保留,含引号)。(string_quote ") 那个落单的引号先换掉。"""
    stack = [[]]
    for tok in TOKEN_RE.findall(text.replace(QUOTE, "(string_quote QUOTE_CHAR)")):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise SystemExit("DSN 括号不成对")
    return stack[0][0]


def sexp_dump(node, depth: int = 0) -> str:
    if not isinstance(node, list):
        return node
    if depth >= 3 or not any(isinstance(c, list) for c in node):
        return "(" + " ".join(sexp_dump(c, 9) for c in node) + ")"
    pad = "\n" + "  " * (depth + 1)
    return "(" + " ".join(c for c in node if not isinstance(c, list)) + "".join(
        pad + sexp_dump(c, depth + 1) for c in node if isinstance(c, list)) + ")"


def only_nets(text: str, keep: set, outer=("F.Cu", "B.Cu"), grow=None) -> str:
    """只留 keep 里的网给 freerouting 布(分阶段布线的第一阶段:回授、晶振这些要先占好位置的线)。

    其他网从 network 与类别里拿掉:它们的焊盘变成没有网的障碍;已经画好的线、过孔去掉 (net …)
    变成障碍;外层铜区(别的网的鋪銅)改成 keepout,内层平面拿掉(过孔要穿过去,真板上会让开)。

    障碍没有网,freerouting 只用板子层级的间距算它们,不知道它们原本的类别。间距取「留下的网
    所属类别」里最大的(base);类别间距比 base 大的障碍,由 grow(base) 给出加大过的 keepout
    补上差额。原本一律取全板最大(0.25):0.4 mm 间距的 CM5 连接器、LAN7800 QFN 脚出线要
    ≤0.225,GPIO、PCIe 边带、LED 这些网整批佈不通(cm5 两种分批都卡在未接 112)。"""
    tree = sexp_parse(text)
    def name(n):
        return n.strip('"')
    found = set()
    for sec in tree:
        if not isinstance(sec, list) or not sec:
            continue
        if sec[0] == "network":
            # 留下的网的间距取它们类别里最大的(base):没有网的障碍,freerouting 只用走线这一边的
            # 类别间距(cm5 第一次:FB 离 +54V 焊盘 0.233 < HV54 0.25,共 21 处 → 由 grow 补上)
            rules = [r for c in sec if isinstance(c, list) and c[0] == "class"
                     and any(not isinstance(t, list) and name(t) in keep for t in c[2:])
                     for r in c if isinstance(r, list) and r[0] == "rule"]
            worst = max((float(x[1]) for r in rules for x in r if isinstance(x, list) and x[0] == "clearance"),
                        default=0.0)
            for r in rules:
                for x in r:
                    if isinstance(x, list) and x[0] == "clearance":
                        x[1] = f"{worst:g}"
            out = []
            for c in sec:
                if isinstance(c, list) and c[0] == "net":
                    if name(c[1]) not in keep:
                        continue
                    found.add(name(c[1]))
                elif isinstance(c, list) and c[0] == "class":
                    c[2:] = [t for t in c[2:] if isinstance(t, list) or name(t) in keep]
                    if not any(not isinstance(t, list) for t in c[2:]):
                        continue
                out.append(c)
            sec[:] = out
        elif sec[0] == "wiring":
            for c in sec[1:]:
                c[:] = [t for t in c if not (isinstance(t, list) and t[0] == "net" and name(t[1]) not in keep)]
        elif sec[0] == "structure":
            # 没有网的障碍照板子层级的 (rule (clearance …)) 算(cm5 第二次:类别间距已取 0.25,
            # FB 离 GND 焊盘仍只有 0.158)→ 也取全板最大。network 在 structure 后面,先放记号
            for r in sec:
                if isinstance(r, list) and r[0] == "rule":
                    for x in r:
                        if isinstance(x, list) and x[0] == "clearance" and len(x) == 2:
                            x[1] = "WORST_CLEARANCE"
            out = []
            for c in sec:
                if isinstance(c, list) and c[0] == "plane" and name(c[1]) not in keep:
                    if c[2][1] not in outer:
                        continue
                    c = ["keepout", '""', c[2]]
                out.append(c)
            sec[:] = out
            structure = sec
    if grow:
        structure.extend(sexp_parse("(x " + " ".join(grow(worst)) + ")")[1:])
    missing = keep - found
    if missing:
        raise SystemExit(f"DSN 里没有这些网:{', '.join(sorted(missing))}")
    out = sexp_dump(tree).replace("(string_quote QUOTE_CHAR)", QUOTE)
    return out.replace("WORST_CLEARANCE", f"{worst:g}") + "\n"


def grown_obstacles(board, keep: set, base_um: float, layers=(pcbnew.F_Cu, pcbnew.B_Cu)) -> list:
    """别的网的焊盘、线、过孔、铜区,自身间距比 base 大的:外扩差额,变成 keepout。

    freerouting 对 keepout 也是用 base 的间距,外扩后加起来正好是原本的类别间距
    (例:HV54 0.25 的焊盘外扩 0.1,GPIO 0.15 的线离它仍 ≥0.25)。"""
    base = base_um * 1000  # DSN 单位 µm → KiCad nm
    out = []

    def emit(item, layer, extra):
        sps = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(sps, layer, int(extra), mm(0.005), pcbnew.ERROR_OUTSIDE)
        for i in range(sps.OutlineCount()):
            ol = sps.Outline(i)
            pts = [ol.CPoint(j) for j in range(ol.PointCount())] + [ol.CPoint(0)]
            xy = "  ".join(f"{p.x / 1000:g} {-p.y / 1000:g}" for p in pts)
            out.append(f'(keepout "" (polygon {board.GetLayerName(layer)} 0  {xy}))')

    items = list(board.GetPads()) + list(board.GetTracks())
    for it in items:
        if it.GetNetname() in keep or it.GetNetCode() <= 0:
            continue
        for layer in layers:
            if it.IsOnLayer(layer):
                extra = it.GetOwnClearance(layer) - base
                if extra > 0:
                    emit(it, layer, extra)
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() in keep:
            continue
        for layer in layers:
            if not z.IsOnLayer(layer):
                continue
            extra = z.GetOwnClearance(layer) - base
            if extra <= 0:
                continue
            fill = z.GetFilledPolysList(layer).CloneDropTriangulation()
            fill.Inflate(int(extra), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.005))
            for i in range(fill.OutlineCount()):
                ol = fill.Outline(i)
                pts = [ol.CPoint(j) for j in range(ol.PointCount())] + [ol.CPoint(0)]
                xy = "  ".join(f"{p.x / 1000:g} {-p.y / 1000:g}" for p in pts)
                out.append(f'(keepout "" (polygon {board.GetLayerName(layer)} 0  {xy}))')
    return out


def plane_layers_off(text: str, planes: list, signal: list) -> str:
    """电源平面层(KiCad 层类型 power)在 DSN 里改回 signal、每个网络类别加 use_layer 只用其他层。

    freerouting 2.5.0 只在 signal 层上把平面网络(GND、+3V3…)的焊盘用过孔接到平面;层标成 power 时
    完全不接(cm5 实测:未接 229 条,其中 100 条是平面网络)。它也没有只挡走线、不挡过孔的
    wire_keepout(keepout 连过孔一起挡,平面就接不上)。所以层照样给 signal,改用每个类别的
    (circuit (use_layer …)) 限制走线层:过孔照样穿过平面层,走线只在其他层。"""
    for name in planes:
        text, n = re.subn(rf"(\(layer {re.escape(name)}\s+)\(type power\)", r"\1(type signal)", text)
        if n != 1:
            raise SystemExit(f"DSN 里找不到 {name} 的 (type power)")
    text, n = re.subn(r"\(circuit(\s+)", lambda m: f"(circuit{m.group(1)}(use_layer {' '.join(signal)}){m.group(1)}", text)
    if n == 0:
        raise SystemExit("DSN 里没有网络类别的 (circuit …)")
    return text


def gnd_pour(board, layer) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(board.FindNet("GND"))
    zone.SetLocalClearance(mm(0.3))
    zone.SetMinThickness(mm(0.25))
    # SMD 焊盘实心连接、插件焊盘用热焊盘:0402 这类小焊盘做热焊盘时常常只剩 1 条
    # 引线接得上铺铜(DRC starved_thermal),实心连接对回流焊不是问题;排针等插件脚
    # 仍用热焊盘,方便手焊。
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    # 比板框内缩 0.3mm,铜不贴板边(JLCPCB 要求铜到板边 ≥0.3mm)。
    # 范围直接取板框(Edge.Cuts)的外接矩形,不依赖哪块板子的尺寸常数。
    bb = board.GetBoardEdgesBoundingBox()
    inset = mm(0.3)
    x0, y0 = bb.GetLeft() + inset, bb.GetTop() + inset
    x1, y1 = bb.GetRight() - inset, bb.GetBottom() - inset
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(pcbnew.VECTOR2I(x, y))
    board.Add(zone)


def is_own_pour(board, zone) -> bool:
    """gnd_pour 铺的铜:外层、GND、没有名字、不是规则区。

    板子生成器自己加的铜区(cm5 的内层 GND / +5V / +3V3 平面)都有名字,不算。
    """
    return (
        not zone.GetIsRuleArea()
        and zone.GetZoneName() == ""
        and zone.GetNetname() == "GND"
        and zone.GetFirstLayer() in (pcbnew.F_Cu, pcbnew.B_Cu)
    )


def clear_routing(board) -> None:
    """清掉上一轮的走线、过孔、gnd_pour 的铺铜,以及规则区(布线禁止区)。

    锁定(locked)的走线与过孔留下:板子生成器自己画的(cm5 电源级接到内层平面的过孔阵列与闸极驱动线,
    gen/power_stage.py),不是 freerouting 的结果。

    规则区只在布线时有用:relay8 的 mains_route_* 禁止低压线进市电区,导入后
    gen/pcb.py finish 补回市电走线、改加只禁铺铜的 mains_nofill_*。
    其他铜区(内层电源平面)保留:以前这里删掉所有 zone,cm5 的平面会被清空。
    """
    # 用 Delete 不用 Remove:Remove 把所有权交回 Python(thisown=1),删完走线再删 zone 时
    # 会报 'SwigPyObject has no attribute thisown',或直接让 pcbnew 崩溃(0xC0000005)。
    # 前两块板放件时板上没有 zone,这段从没真正执行过;继电器板带着布线禁止区才踩到。
    for t in [t for t in board.GetTracks() if not t.IsLocked()]:
        board.Delete(t)
    for z in [board.GetArea(i) for i in range(board.GetAreaCount())]:
        if z.GetIsRuleArea() or is_own_pour(board, z):
            board.Delete(z)


def import_ses(pcb: Path, ses: Path, lock: bool = False) -> None:
    """lock:分阶段布线的第一阶段。导入的线全部锁定、不铺 GND:下一阶段 clear_routing 会留下它们,
    DSN 也标成不可动。"""
    board = pcbnew.LoadBoard(str(pcb))
    # 重复执行时先清掉上一轮的结果,避免叠加
    clear_routing(board)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("ImportSpecctraSES 失败")
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    # freerouting 2.5.0 扇出时会把线收到类别线宽的 60% / 50%,不管 neck_width(上游 #978,
    # 修在 master、还没发版):cm5 0.15 → 0.09 < 板子最小线宽 0.1。只加宽到最小线宽,间距交给 DRC。
    tmin = board.GetDesignSettings().m_TrackMinWidth
    thin = [t for t in tracks if not t.IsLocked() and t.GetWidth() < tmin]
    for t in thin:
        t.SetWidth(tmin)
    if thin:
        print(f"  {len(thin)} 段线比最小线宽 {tmin / 1e6:g} mm 窄,已加宽")
    if lock:
        new = [t for t in board.GetTracks() if not t.IsLocked()]
        for t in new:
            t.SetLocked(True)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        stable_uuids(board, pcb.stem)
        board.Save(str(pcb))
        print(f"imported {ses.name}: locked {len(new)} new tracks/vias (stage 1)")
        return

    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    stable_uuids(board, pcb.stem)
    board.Save(str(pcb))
    kept = sum(1 for z in board.Zones() if not is_own_pour(board, z))
    print(f"imported {ses.name}: {len(tracks)} tracks, {len(vias)} vias; GND poured on F/B.Cu"
          + (f"; kept {kept} existing zones" if kept else ""))


if __name__ == "__main__":
    # route.py dsn <板名> <目录> [网,网…]   最后一个参数:只布这些网(分阶段的第一阶段)
    # route.py ses|lock <板名> <目录>        lock:导入后锁定、不铺 GND
    step, name, d = sys.argv[1], sys.argv[2], Path(sys.argv[3]).resolve()
    pcb = d / f"{name}.kicad_pcb"
    if step == "dsn":
        export_dsn(pcb, d / f"{name}.dsn", set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None)
    else:
        import_ses(pcb, d / f"{name}.ses", lock=step == "lock")
