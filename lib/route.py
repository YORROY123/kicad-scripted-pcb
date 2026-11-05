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


def export_dsn(pcb: Path, dsn: Path) -> None:
    board = pcbnew.LoadBoard(str(pcb))
    stable_uuids(board, pcb.stem)  # DSN 照 UUID 排序:汇出前统一
    board.Save(str(pcb))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("ExportSpecctraDSN 失败")
    planes = [board.GetLayerName(lid) for lid in board.GetEnabledLayers().CuStack()
              if board.GetLayerType(lid) == pcbnew.LT_POWER]
    if planes:
        signal = [board.GetLayerName(lid) for lid in board.GetEnabledLayers().CuStack()
                  if board.GetLayerType(lid) != pcbnew.LT_POWER]
        dsn.write_text(plane_layers_off(dsn.read_text(encoding="utf-8"), planes, signal), encoding="utf-8")
        print(f"  {', '.join(planes)}:只接平面、不走线(use_layer {' '.join(signal)})")
    print(f"wrote {dsn.name}")


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


def import_ses(pcb: Path, ses: Path) -> None:
    board = pcbnew.LoadBoard(str(pcb))
    # 重复执行时先清掉上一轮的结果,避免叠加
    clear_routing(board)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("ImportSpecctraSES 失败")
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]

    gnd_pour(board, pcbnew.F_Cu)
    gnd_pour(board, pcbnew.B_Cu)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    stable_uuids(board, pcb.stem)
    board.Save(str(pcb))
    kept = sum(1 for z in board.Zones() if not is_own_pour(board, z))
    print(f"imported {ses.name}: {len(tracks)} tracks, {len(vias)} vias; GND poured on F/B.Cu"
          + (f"; kept {kept} existing zones" if kept else ""))


if __name__ == "__main__":
    # route.py dsn|ses <板名> <目录>
    step, name, d = sys.argv[1], sys.argv[2], Path(sys.argv[3]).resolve()
    pcb = d / f"{name}.kicad_pcb"
    if step == "dsn":
        export_dsn(pcb, d / f"{name}.dsn")
    else:
        import_ses(pcb, d / f"{name}.ses")
