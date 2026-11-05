"""lib/route.py 的 clear_routing:重新导入 .ses 前清掉什么、留下什么;plane_layers_off:DSN 的平面层;
only_nets:分阶段布线只留部分网。

    python lib/route_test.py        (用 KiCad 自带的 python;不需要先 build)

cm5 的内层电源平面与电源级与供电支线的外层铺铜(有名字)、锁定的过孔必须留下(以前全部 zone 都被删掉);
其他三块板的结果不变:它们板上只有 gnd_pour 的铺铜和规则区,也没有锁定的走线,照旧全删。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcbgen import mm  # noqa: E402
from route import clear_routing, gnd_pour, only_nets, plane_layers_off, sexp_parse  # noqa: E402

BOARDS = Path(__file__).resolve().parent.parent / "boards"


def zone_keys(board):
    return sorted(
        (board.GetLayerName(z.GetFirstLayer()), z.GetNetname(), z.GetIsRuleArea(), z.GetZoneName())
        for z in board.Zones()
    )


def add_zone(board, layer, net, name="", rule_area=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
    else:
        z.SetNet(board.FindNet(net))
    z.SetZoneName(name)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in ((0, 0), (10, 0), (10, 10), (0, 10)):
        outline.Append(pcbnew.VECTOR2I(mm(x), mm(y)))
    board.Add(z)


def synthetic() -> None:
    board = pcbnew.BOARD()
    for name in ("GND", "+5V"):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    board.SetCopperLayerCount(4)
    add_zone(board, pcbnew.In1_Cu, "GND", "GND plane")
    add_zone(board, pcbnew.In2_Cu, "+5V", "+5V plane")
    add_zone(board, pcbnew.F_Cu, "+5V", "+5V island")
    add_zone(board, pcbnew.F_Cu, "GND")  # 上一轮 gnd_pour 的样子
    add_zone(board, pcbnew.B_Cu, "GND")
    add_zone(board, pcbnew.F_Cu, "", "keepout", rule_area=True)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(0, 0))
    track.SetEnd(pcbnew.VECTOR2I(mm(5), 0))
    board.Add(track)
    for locked in (False, True):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(mm(2), mm(2)))
        via.SetLocked(locked)
        board.Add(via)

    clear_routing(board)
    left = list(board.GetTracks())
    assert len(left) == 1 and left[0].Type() == pcbnew.PCB_VIA_T and left[0].IsLocked(), "tracks left"
    got = zone_keys(board)
    want = [("F.Cu", "+5V", False, "+5V island"), ("In1.Cu", "GND", False, "GND plane"),
            ("In2.Cu", "+5V", False, "+5V plane")]
    assert got == want, got

    # 再跑一轮:gnd_pour 加的两块会被下一轮认出来删掉,不会越叠越多
    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    clear_routing(board)
    assert zone_keys(board) == want, zone_keys(board)
    print("ok    synthetic: planes, named zones and locked vias kept; pours, keepouts and tracks removed")


def real_boards() -> None:
    for name, kept in (("cm5", 24), ("relay8", 0), ("esp32c3", 0), ("usbc-ldo", 0)):
        pcb = BOARDS / name / f"{name}.kicad_pcb"
        board = pcbnew.LoadBoard(str(pcb))
        before = len(list(board.Zones()))
        locked = sum(t.IsLocked() for t in board.GetTracks())
        clear_routing(board)
        assert len(board.GetTracks()) == locked, (name, "unlocked tracks left")
        after = zone_keys(board)
        assert len(after) == kept, (name, after)
        assert all(z.GetZoneName() for z in board.Zones()), (name, after)
        print(f"ok    {name}: {before} zones -> kept {len(after)}; {locked} locked tracks and vias kept")


DSN = """  (structure
    (layer F.Cu
      (type signal)
    )
    (layer In1.Cu
      (type power)
    )
    (layer B.Cu
      (type signal)
    )
  (network
    (class kicad_default A B
      (circuit
        (use_via "Via[0-3]_600:300_um")
      )
    )
    (class Power GND
      (circuit
        (use_via "Via[0-3]_600:300_um")
      )
    )
"""


def plane_layers():
    out = plane_layers_off(DSN, ["In1.Cu"], ["F.Cu", "B.Cu"])
    assert "(type power)" not in out and out.count("(type signal)") == 3, out
    assert out.count("(use_layer F.Cu B.Cu)") == 2 == out.count("(circuit"), out
    assert out.index("(use_layer") < out.index("(use_via"), out
    # 层名对不上、或没有类别:要报错,不能默默汇出一个 freerouting 会在平面层走线的 DSN
    for bad, layers in ((DSN.replace("(type power)", "(type signal)"), ["In1.Cu"]), (DSN, ["In2.Cu"]),
                        (DSN.replace("(circuit", "(rule"), ["In1.Cu"])):
        try:
            plane_layers_off(bad, layers, ["F.Cu", "B.Cu"])
        except SystemExit:
            continue
        raise AssertionError("plane_layers_off 应该失败")
    print("ok    plane_layers_off: power -> signal, use_layer on every class; bad input refused")


STAGE_DSN = """(pcb "x.dsn"
  (parser (string_quote ") (space_in_quoted_tokens on))
  (structure
    (layer F.Cu (type signal))
    (rule (width 150) (clearance 150) (clearance 37.5 (type smd_smd)))
    (plane GND (polygon F.Cu 0  0 0  10 0  10 10  0 0))
    (plane GND (polygon In1.Cu 0  0 0  10 0  10 10  0 0))
    (plane FB (polygon B.Cu 0  0 0  5 0  5 5  0 0))
  )
  (network
    (net FB (pins U1-5 R1-2))
    (net GND (pins U1-6 C1-2))
    (net "odd (name)" (pins U1-7))
    (class kicad_default FB "odd (name)" (circuit (use_via V)) (rule (width 150) (clearance 150)))
    (class Power GND (circuit (use_via V)) (rule (width 250) (clearance 250)))
  )
  (wiring
    (wire (path F.Cu 190  1 1  2 2)(net GND)(type fix))
    (via "V" 3 3 (net FB)(type fix))
  )
)
"""


def stage_nets():
    out = only_nets(STAGE_DSN, {"FB", "odd (name)"})
    tree = sexp_parse(out)
    sec = {c[0]: c for c in tree if isinstance(c, list)}
    nets = [c[1] for c in sec["network"] if c[0] == "net"]
    classes = [c[1] for c in sec["network"] if c[0] == "class"]
    assert nets == ["FB", '"odd (name)"'] and classes == ["kicad_default"], out
    # 类别与板子层级(没有网的障碍用它)都取被拿掉的 Power 的间距;smd_smd 不动
    assert out.count("(clearance 250)") == 2 and "(clearance 150)" not in out, out
    assert "(clearance 37.5 (type smd_smd))" in out, out
    # GND 的线变成没有网的障碍,FB 的过孔照旧带网
    wire, via = sec["wiring"][1], sec["wiring"][2]
    assert not any(isinstance(t, list) and t[0] == "net" for t in wire), out
    assert ["net", "FB"] in via, out
    # 外层 GND 鋪銅 -> keepout,内层 GND 平面拿掉,FB 自己的 plane 留着
    kinds = [(c[0], c[-1][1]) for c in sec["structure"] if c[0] in ("plane", "keepout")]
    assert kinds == [("keepout", "F.Cu"), ("plane", "B.Cu")], kinds
    assert '(string_quote ")' in out, out
    try:
        only_nets(STAGE_DSN, {"FB", "NOPE"})
    except SystemExit:
        pass
    else:
        raise AssertionError("only_nets 遇到不存在的网应该失败")
    print("ok    only_nets: other nets become obstacles, outer pours keepouts, inner planes dropped")


if __name__ == "__main__":
    stage_nets()
    plane_layers()
    synthetic()
    real_boards()
