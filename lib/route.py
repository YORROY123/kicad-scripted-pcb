"""freerouting 的 .ses → 写回 .kicad_pcb,再铺双面 GND。

流程(都用 KiCad 自带的 python.exe):
    pcbgen.py            网表 → usbc-ldo.kicad_pcb(放件、板框、规则)
    route.py dsn         导出 usbc-ldo.dsn
    freerouting          usbc-ldo.dsn → usbc-ldo.ses
    route.py ses         导入 .ses、铺 GND、填充、存档

freerouting 2.5.0 的原生 CLI 在 KiCad 10 的 DSN 上会崩(上游 #957),
用 jar 版 + Java 25:
    tools/jre/<jre>/bin/java.exe -jar tools/freerouting/freerouting-2.5.0.jar \
        -de usbc-ldo.dsn -do usbc-ldo.ses --router.autorouter.max_passes=30 \
        --gui.enabled=false
"""
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcbgen import mm  # noqa: E402


def export_dsn(pcb: Path, dsn: Path) -> None:
    board = pcbnew.LoadBoard(str(pcb))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("ExportSpecctraDSN 失败")
    print(f"wrote {dsn.name}")


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


def import_ses(pcb: Path, ses: Path) -> None:
    board = pcbnew.LoadBoard(str(pcb))
    # 重复执行时先清掉上一轮的走线、过孔与铺铜,避免叠加
    # 用 Delete 不用 Remove:Remove 把所有权交回 Python(thisown=1),删完走线再删 zone 时
    # 会报 'SwigPyObject has no attribute thisown',或直接让 pcbnew 崩溃(0xC0000005)。
    # 前两块板放件时板上没有 zone,这段从没真正执行过;继电器板带着布线禁止区才踩到。
    for t in list(board.GetTracks()):
        board.Delete(t)
    for z in [board.GetArea(i) for i in range(board.GetAreaCount())]:
        board.Delete(z)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("ImportSpecctraSES 失败")
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]

    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    board.Save(str(pcb))
    print(f"imported {ses.name}: {len(tracks)} tracks, {len(vias)} vias; GND poured on F/B.Cu")


if __name__ == "__main__":
    # route.py dsn|ses <板名> <目录>
    step, name, d = sys.argv[1], sys.argv[2], Path(sys.argv[3]).resolve()
    pcb = d / f"{name}.kicad_pcb"
    if step == "dsn":
        export_dsn(pcb, d / f"{name}.dsn")
    else:
        import_ses(pcb, d / f"{name}.ses")
