"""lib/route.py 的 clear_routing:重新导入 .ses 前清掉什么、留下什么。

    python lib/route_test.py        (用 KiCad 自带的 python;不需要先 build)

cm5 的内层电源平面必须留下(以前全部 zone 都被删掉);其他三块板的结果不变:
它们板上只有 gnd_pour 的铺铜和规则区,照旧全删。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcbgen import mm  # noqa: E402
from route import clear_routing, gnd_pour  # noqa: E402

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

    clear_routing(board)
    assert len(board.GetTracks()) == 0, "tracks left"
    got = zone_keys(board)
    want = [("F.Cu", "+5V", False, "+5V island"), ("In1.Cu", "GND", False, "GND plane"),
            ("In2.Cu", "+5V", False, "+5V plane")]
    assert got == want, got

    # 再跑一轮:gnd_pour 加的两块会被下一轮认出来删掉,不会越叠越多
    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    clear_routing(board)
    assert zone_keys(board) == want, zone_keys(board)
    print("ok    synthetic: planes and named zones kept; pours, keepouts and tracks removed")


def real_boards() -> None:
    for name, kept in (("cm5", 3), ("relay8", 0), ("esp32c3", 0), ("usbc-ldo", 0)):
        pcb = BOARDS / name / f"{name}.kicad_pcb"
        board = pcbnew.LoadBoard(str(pcb))
        before = len(list(board.Zones()))
        clear_routing(board)
        after = zone_keys(board)
        assert len(after) == kept, (name, after)
        assert all(z.GetZoneName() for z in board.Zones()), (name, after)
        print(f"ok    {name}: {before} zones -> kept {len(after)}")


if __name__ == "__main__":
    synthetic()
    real_boards()
