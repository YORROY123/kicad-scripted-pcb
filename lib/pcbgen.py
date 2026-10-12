"""网表 → .kicad_pcb:放件、指定焊盘网络、画板框、设规则。

kicad-cli 没有「原理图 → PCB」的指令,所以这一步自己做:读
`kicad-cli sch export netlist --format kicadsexpr` 的输出,用 pcbnew 从安装目录
的封装库载入封装。必须用 KiCad 自带的 python.exe 跑(pcbnew 只在那里)。

各板的摆放写在 boards/<板>/gen/pcb.py 的 BoardSpec 里,调用这里的 build()。
布线不在这里做 —— 交给 freerouting(见 route.py)。
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import uuid as _uuid

import pcbnew

# 新物件的 UUID 預設是隨機的,而 KiCad 的 Specctra 匯出器照 UUID 排序元件、image 與網路腳位。
# 同一份擺位每次會生出順序不同的 DSN,freerouting 對順序敏感(對同一份 DSN 則每次結果相同)
# → 佈線成敗變成擲骰子。固定種子讓 UUID、DSN、佈線結果與 .kicad_pcb 都可重現。
# 所有寫板子的腳本(各板 gen/pcb.py、route.py)都 import 本模組,種子在這裡設一次就涵蓋。
pcbnew.KIID.SeedGenerator(20261010)

FP_DIR = Path(pcbnew.__file__).resolve().parents[3] / "share" / "kicad" / "footprints"
if not FP_DIR.is_dir():  # pcbnew.py 在 bin/Lib/site-packages 或 bin 下,两种都试
    FP_DIR = Path(sys.executable).resolve().parents[1] / "share" / "kicad" / "footprints"


# ── 最小 S-表达式解析 ────────────────────────────────────────────────────
def parse_sexpr(text: str):
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            tokens.append(c)
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            tokens.append(("S", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            tokens.append(("S", text[i:j]))
            i = j
    stack = [[]]
    for t in tokens:
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1])
    return stack[0][0]


def child(node, key):
    return next((c for c in node[1:] if isinstance(c, list) and c and c[0] == key), None)


def children(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def read_netlist(path: Path):
    root = parse_sexpr(path.read_text(encoding="utf-8"))
    comps = {}
    for comp in children(child(root, "components"), "comp"):
        comps[child(comp, "ref")[1]] = {
            "value": child(comp, "value")[1],
            "footprint": child(comp, "footprint")[1],
        }
    pad_net = {}  # (ref, pad) -> net name
    for net in children(child(root, "nets"), "net"):
        name = child(net, "name")[1]
        for node in children(net, "node"):
            pad_net[(child(node, "ref")[1], child(node, "pin")[1])] = name
    return comps, pad_net


@dataclass
class BoardSpec:
    """一块板子的专属设定;其余(读网表、放件、规则、自检)各板共用。"""
    name: str                      # 输出档名(不含扩展名)
    width: float                   # 板框尺寸,mm
    height: float
    place: dict                    # ref -> (x, y, rot),mm,板框左上角为原点
    power_nets: tuple = ()         # 归入 Power 网络类别(加粗)的网
    # 允许伸出板边的器件(USB-C 开口、模块天线):只查焊盘在板内,不查 courtyard
    overhang: tuple = ()
    # 最小孔径(mm)。KiCad 默认 0.3;JLCPCB 双层板能做到 0.15
    # (~/.claude/skills/easyeda-agent/references/fab-rules-jlcpcb.json,manufacturingMin)。
    min_hole: float = 0.3
    # 这些库的器件,位号移到 F.Fab(不印在板上):密集小板上 0402 的位号必然压焊盘/互相重叠,
    # 装配以 BOM + 坐标文件为准。
    fab_ref_libs: tuple = ()
    # 额外的网络类别:(名称, 线宽 mm, 间距 mm, 网名通配符…)。例:市电网 3mm 宽。
    netclasses: tuple = ()
    # 固定孔中心 (x, y),mm。不在原理图里:放成「只在板上」的封装 H1、H2…,不进 BOM / CPL,
    # 原理图一致性检查也略过。courtyard 照常参与重叠检查(螺丝头与垫圈要有空间)。
    mounting_holes: tuple = ()
    mounting_hole_fp: str = "MountingHole:MountingHole_3.2mm_M3"
    extra: dict = field(default_factory=dict)


ORIGIN = (100.0, 100.0)  # 板框放在 (100,100),远离 KiCad 页面原点

# JLCPCB 双层板能力是 0.127/0.127mm;取宽松一点的值,留出良率余量。
TRACK_W = 0.25
CLEARANCE = 0.2
VIA_D, VIA_DRILL = 0.6, 0.3
# 允许走线在 USB-C 0.5mm 间距焊盘处收窄(neck-down);仍高于 JLC 的 0.127。
TRACK_MIN = 0.15
POWER_W = 0.5


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def at(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


def build(spec: BoardSpec, net_path: Path, out: Path) -> None:
    comps, pad_net = read_netlist(net_path)
    missing = set(comps) - set(spec.place)
    if missing:
        raise SystemExit(f"没有摆放坐标的器件: {sorted(missing)}")

    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetTrackWidth(mm(TRACK_W))
    nc.SetClearance(mm(CLEARANCE))
    nc.SetViaDiameter(mm(VIA_D))
    nc.SetViaDrill(mm(VIA_DRILL))
    ds.m_TrackMinWidth = mm(TRACK_MIN)
    ds.m_MinThroughDrill = mm(spec.min_hole)

    ns = ds.m_NetSettings
    power = pcbnew.NETCLASS("Power")
    power.SetTrackWidth(mm(POWER_W))
    power.SetClearance(mm(CLEARANCE))
    power.SetViaDiameter(mm(VIA_D))
    power.SetViaDrill(mm(VIA_DRILL))
    ns.SetNetclass("Power", power)
    for name in spec.power_nets:
        ns.SetNetclassPatternAssignment(name, "Power")
    for cls_name, width, clearance, *patterns in spec.netclasses:
        cls = pcbnew.NETCLASS(cls_name)
        cls.SetTrackWidth(mm(width))
        cls.SetClearance(mm(clearance))
        cls.SetViaDiameter(mm(VIA_D))
        cls.SetViaDrill(mm(VIA_DRILL))
        ns.SetNetclass(cls_name, cls)
        for pattern in patterns:
            ns.SetNetclassPatternAssignment(pattern, cls_name)

    nets = {}
    for name in sorted(set(pad_net.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    for ref, info in sorted(comps.items()):
        lib, name = info["footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(FP_DIR / f"{lib}.pretty"), name)
        if fp is None:
            raise SystemExit(f"{ref}: 载入封装失败 {info['footprint']}")
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        x, y, rot = spec.place[ref]
        fp.SetPosition(at(x, y))
        fp.SetOrientationDegrees(rot)
        if lib in spec.fab_ref_libs:
            fp.Reference().SetLayer(pcbnew.F_Fab)
        board.Add(fp)
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:  # 定位孔(NPTH)
                continue
            net = pad_net.get((ref, num))
            if net:
                pad.SetNet(nets[net])

    lib, name = spec.mounting_hole_fp.split(":")
    for i, (x, y) in enumerate(spec.mounting_holes, 1):
        ref = f"H{i}"
        if ref in comps:
            raise SystemExit(f"固定孔位号 {ref} 与原理图器件冲突")
        fp = pcbnew.FootprintLoad(str(FP_DIR / f"{lib}.pretty"), name)
        fp.SetReference(ref)
        fp.SetValue(name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetBoardOnly(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        fp.Reference().SetLayer(pcbnew.F_Fab)  # 孔贴着板边,位号不必印
        fp.SetPosition(at(x, y))
        board.Add(fp)

    # 板框
    corners = [(0, 0), (spec.width, 0), (spec.width, spec.height), (0, spec.height)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        seg.SetStart(at(x1, y1))
        seg.SetEnd(at(x2, y2))
        board.Add(seg)

    move_clashing_refs(board)
    check_placement(spec, board, comps, pad_net)
    # 网络类别存在 .kicad_pro,不在 .kicad_pcb;SaveBoard 会一并写出专案档
    stable_uuids(board, spec.name)
    pcbnew.SaveBoard(str(out), board)
    print(f"wrote {out.name}: {len(comps)} footprints, {len(nets)} nets")


_UUID_NS = _uuid.UUID("6f1c5a2e-3b8d-4e5f-9a10-c0ffee000001")


def stable_uuids(board, name: str) -> None:
    """每个物件的 UUID 由「板名 + 位号 + 种类 + 序号」算出来,与 KiCad 内部取号无关。

    只靠 KIID.SeedGenerator 不够:KiCad 载入封装时会为暂存物件取号,10.0.6 与 10.0.7
    取的个数不同(usbc-ldo 从 J1 开始分岔)。Specctra 汇出器照 UUID 排序元件与网络脚位,
    UUID 一变 DSN 顺序就变,freerouting 结果也跟着变(本机 6 个过孔、CI 9 个)。
    写板子的每一步(摆放、DSN 汇出前、SES 导入后、relay8 的市电步骤)存档前都要调用。
    """
    items = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        items.append((fp, ref))
        items += [(f, f"{ref}/field/{i}") for i, f in enumerate(fp.GetFields())]
        items += [(p, f"{ref}/pad/{p.GetNumber()}/{i}") for i, p in enumerate(fp.Pads())]
        items += [(g, f"{ref}/gfx/{i}") for i, g in enumerate(fp.GraphicalItems())]
        items += [(z, f"{ref}/zone/{i}") for i, z in enumerate(fp.Zones())]
    items += [(d, f"drawing/{i}") for i, d in enumerate(board.GetDrawings())]
    items += [(t, f"track/{i}") for i, t in enumerate(board.GetTracks())]
    items += [(z, f"zone/{i}") for i, z in enumerate(board.Zones())]
    keys = [k for _, k in items]
    if len(set(keys)) != len(keys):
        raise SystemExit("stable_uuids: 重复的键")
    # 两阶段:重新载入后物件的列举顺序可能和存档前不同,直接改成最终值时,
    # 目标 UUID 可能还在别的物件身上,KiCad 会跳「duplicate target UUID」断言。
    # 先全部换成另一个命名空间的暂用值,再设最终值。
    for stage in ("tmp", "final"):
        for item, key in items:
            want = str(_uuid.uuid5(_UUID_NS, f"{stage}/{name}/{key}" if stage == "tmp" else f"{name}/{key}"))
            if item.m_Uuid.AsString() != want:
                item.SetUuid(pcbnew.KIID(want))


def move_clashing_refs(board) -> None:
    """位号文字压到别的器件焊盘时移到 F.Fab(不印在板上),并逐个报出来。

    丝印压焊盘会被板厂裁掉、DRC 报 silk_over_copper;不印总比印一半好,
    装配以 BOM + 坐标文件为准。
    """
    pads = [(fp.GetReference(), pad.GetBoundingBox())
            for fp in board.GetFootprints() for pad in fp.Pads()]
    moved = []
    for fp in board.GetFootprints():
        ref = fp.Reference()
        if ref.GetLayer() != pcbnew.F_SilkS:
            continue
        box = ref.GetBoundingBox()
        if any(owner != fp.GetReference() and box.Intersects(pb) for owner, pb in pads):
            ref.SetLayer(pcbnew.F_Fab)
            moved.append(fp.GetReference())
    if moved:
        print(f"位号压到别的焊盘,移到 F.Fab: {', '.join(sorted(moved))}")


def check_placement(spec: BoardSpec, board, comps, pad_net) -> None:
    """写出前自检:每个焊盘的网都对上网表、器件不出板、封装不互相重叠。"""
    problems = []
    seen = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            seen.add((ref, num))
            want = pad_net.get((ref, num), "")
            got = pad.GetNetname()
            if want and got != want:
                problems.append(f"{ref}.{num}: 网 {got!r} != 网表 {want!r}")
    for key in set(pad_net) - seen:
        problems.append(f"网表里的 {key[0]}.{key[1]} 在封装上找不到焊盘")

    edge = pcbnew.BOX2I(at(0, 0), pcbnew.VECTOR2L(mm(spec.width), mm(spec.height)))
    boxes = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        boxes.append((ref, bb))
        if ref in spec.overhang:
            # 伸出板边是设计意图(USB-C 开口、天线),但焊盘必须在板内
            for pad in fp.Pads():
                if not edge.Contains(pad.GetBoundingBox()):
                    problems.append(f"{ref}.{pad.GetNumber()} 的焊盘超出板框")
                    break
        elif not edge.Contains(bb):
            problems.append(f"{ref} 的 courtyard 超出板框")
    # 用 courtyard 的真实多边形求交,不用外接矩形:ESP32 模块之类的 courtyard 是 T 形
    # (天线区宽、本体窄),外接矩形会把本体两侧合法的位置误判成重叠。
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for i, (ra, a) in enumerate(boxes):
        for rb, b in boxes[i + 1:]:
            if not a.Intersects(b):
                continue
            inter = pcbnew.SHAPE_POLY_SET(fps[ra].GetCourtyard(pcbnew.F_CrtYd))
            inter.BooleanIntersection(fps[rb].GetCourtyard(pcbnew.F_CrtYd))
            if inter.Area() > 0:
                problems.append(f"{ra} 与 {rb} 的 courtyard 重叠")
    if problems:
        print(f"!! 放置自检失败 {len(problems)} 项,拒绝写出:")
        for p in problems:
            print("   ", p)
        raise SystemExit(1)

