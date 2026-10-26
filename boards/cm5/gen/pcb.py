"""CM5 載板的正式擺件:網表 → cm5.kicad_pcb(板框、4 層、網路類別、固定孔、自檢)。

還沒佈線。座標與自動擺件在 gen/placement.py(3D 預覽 concept/ 也用同一份)。
必須用 KiCad 自帶的 python.exe 跑:
    <KiCad python> gen/pcb.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import pcbgen  # noqa: E402
import pcbnew  # noqa: E402
from pcbgen import BoardSpec, build  # noqa: E402
from placement import BOARD_HOLES, H, MODULE_HOLES, W, auto_place  # noqa: E402

BOARD = HERE.parent
pcbgen.EXTRA_FP_DIRS.append(str(BOARD / "footprints"))

# 接頭開口要切齊板邊,courtyard 本來就伸出板外;只查焊盤在板內
OVERHANG = ("J20", "J30", "J40", "J41", "J50", "J51", "J52", "J70", "SW51")

# 線寬 mm、間距 mm、網名。先求能佈通,阻抗控制(USB3/PCIe/HDMI 差分)與實際電流的線寬
# 在佈線那一步依疊層算過再改,見 README「PCB 待辦」。
NETCLASSES = (
    # 54 V 輸入與 PoE 輸出。IPC-2221 表 6-1 的 51–100 V:外層有防焊(B4)0.13 mm、無塗層(B2)0.6 mm。
    # 板子有防焊,取 0.25 mm 留餘量。0.6 mm 做不到:RJ45 腳之間只有 0.53、IP804AR(QFN 0.5)0.25。
    ("HV54", 0.5, 0.25, "+54V", "POE*", "SW"),
    # 5 V / 12 A 主電源與 3.3 V / 8 A:之後改用鋪銅,這裡先給最寬的走線
    ("Rail", 0.8, 0.2, "+5V", "+3V3", "SW3"),
)
POWER = ("GND", "CM5_3V3", "IP_3V3", "LAN0_1V2", "LAN1_1V2", "LAN0_2V5", "LAN1_2V5",
         "USBA0_VBUS", "USBA1_VBUS", "USBC_VBUS")


def placement(net_path: Path) -> dict:
    comps, pad_net = pcbgen.read_netlist(net_path)
    fps = {}
    for ref, info in comps.items():
        lib, name = info["footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(pcbgen.fp_lib_dir(lib)), name)
        if fp is None:
            raise SystemExit(f"{ref}: 载入封装失败 {info['footprint']}")
        fps[ref] = fp
    return auto_place(fps, pad_net)


def spec(place: dict) -> BoardSpec:
    holes = list(BOARD_HOLES) + [(x, y, "MountingHole:MountingHole_2.7mm_M2.5") for x, y in MODULE_HOLES]
    return BoardSpec(
        name="cm5",
        width=W,
        height=H,
        place=place,
        power_nets=POWER,
        netclasses=NETCLASSES,
        overhang=OVERHANG,
        fab_ref_libs=("Resistor_SMD", "Capacitor_SMD"),
        mounting_holes=tuple(holes),
        copper_layers=4,
    )


# 同一顆零件的焊盤之間照原廠焊盤圖,不套網路類別間距:FSUSB42(MSOP-10 0.5 mm)焊盤間只有
# 0.15 mm。0.1 mm 仍高於 JLCPCB 4 層板最小線距 0.09 mm。走線、過孔照網路類別。
DRU = """(version 1)
(rule "pads within one footprint"
  (condition "A.Type == 'Pad' && B.Type == 'Pad' && A.Parent == B.Parent")
  (constraint clearance (min 0.1mm)))
"""


# ── 內層電源平面 ────────────────────────────────────────────────────────
# L2(In1.Cu)整片 GND:差分線的參考面(sim/diff_impedance.py 假設 L1 正下方是整片地)。
# L3(In2.Cu)分成兩塊:+5V 在右上(L10 降壓輸出 → CM5、40-pin、風扇),
# +3V3 是 L 形(L20 降壓輸出沿下緣往左 → Hub、LAN7800 ×2,再沿左緣往上 → M.2)。
# 座標 mm,板框左上為原點;兩塊之間留 0.5 mm。
PLANES = (
    ("GND", "In1.Cu", [(0.3, 0.3), (169.7, 0.3), (169.7, 119.7), (0.3, 119.7)]),
    ("+5V", "In2.Cu", [(60.25, 0.3), (169.7, 0.3), (169.7, 71.75), (60.25, 71.75)]),
    ("+3V3", "In2.Cu", [(0.3, 0.3), (59.75, 0.3), (59.75, 72.25), (169.7, 72.25),
                        (169.7, 119.7), (0.3, 119.7)]),
)

# 載流走廊:(網, 電流 A, 矩形 x0, y0, x1, y1, 電流方向 "x"/"y", 說明)。
# 走廊必須整塊落在該網的平面裡,且垂直電流方向的寬度 ≥ IPC-2221 算出的寬度。
# 電流:CM5 5 V 最多 5 A(CM5 規格書 §1「up to 5 A at 5 V」);40-pin 5 V 1 A、風扇 0.5 A 是估計。
# 3.3 V:M.2 NVMe 2.5 A(M.2 規範 3.3 V 上限)+ LAN7800 ×2 0.592 A(cm5-ref/區塊4)+
# USB2514B 等約 0.3 A,取 4 A。USB-A ×2 與 HDMI 的 5 V(約 1.5 A)在 +3V3 區域裡,
# 佈線時走外層,不靠平面。
CORRIDORS = (
    ("+5V", 6.5, (95.0, 0.3, 160.0, 71.75), "x", "L10 → CM5 J1、40-pin J80、風扇 J81"),
    ("+3V3", 4.0, (60.25, 72.25, 165.0, 119.7), "x", "L20 → Hub U61、LAN7800 U40/U41"),
    ("+3V3", 2.5, (0.3, 20.0, 59.75, 100.0), "y", "左緣往上 → M.2 J60"),
)
INNER_CU_MM = 0.0152   # JLC04161H 內層 0.5 oz 實際厚度(jlcpcb.com/impedance)
TEMP_RISE = 10.0       # °C


def ipc2221_inner_width(amps: float) -> float:
    """IPC-2221 §6.2 內層:I = 0.024·ΔT^0.44·A^0.725(A 為截面積 mil²)→ 需要的寬度 mm。

    這條公式對大面積平面很保守(IPC-2152 允許更小),當作下限檢查用。"""
    area_mil2 = (amps / (0.024 * TEMP_RISE ** 0.44)) ** (1 / 0.725)
    return area_mil2 / (INNER_CU_MM / 0.0254) * 0.0254


def add_planes(board) -> list[str]:
    """加內層平面並檢查載流走廊;回傳問題清單(空 = 通過)。"""
    zones = {}
    for net, layer, pts in PLANES:
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID(layer))
        z.SetNet(board.FindNet(net))
        z.SetLocalClearance(pcbgen.mm(0.3))
        z.SetMinThickness(pcbgen.mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
        # 還沒佈線,平面上沒有過孔;不刪孤島,否則整塊會被當成沒接東西而清掉
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        z.SetZoneName(f"{net} plane")
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(pcbgen.at(x, y))
        board.Add(z)
        zones.setdefault(net, []).append(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    problems = []
    for net, amps, (x0, y0, x1, y1), flow, what in CORRIDORS:
        rect = pcbnew.SHAPE_POLY_SET()
        rect.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            rect.Append(pcbgen.at(x, y))
        for z in zones[net]:
            rect.BooleanSubtract(z.Outline())
        outside = rect.Area() / 1e12  # nm² → mm²
        width = (y1 - y0) if flow == "x" else (x1 - x0)
        need = ipc2221_inner_width(amps)
        tag = "OK" if outside == 0 and width >= need else "!!"
        print(f"  {tag} {net:5} {amps:4.1f} A  寬 {width:5.1f} mm(需要 {need:4.1f})  {what}")
        if outside:
            problems.append(f"{net} 走廊「{what}」有 {outside:.1f} mm² 落在平面外")
        if width < need:
            problems.append(f"{net} 走廊「{what}」寬 {width:.1f} mm < IPC-2221 {need:.1f} mm")
    return problems


if __name__ == "__main__":
    net = BOARD / "net.txt"
    out = BOARD / "cm5.kicad_pcb"
    (BOARD / "cm5.kicad_dru").write_text(DRU, encoding="utf-8")
    build(spec(placement(net)), net, out)
    board = pcbnew.LoadBoard(str(out))
    print(f"內層平面(IPC-2221 內層 {INNER_CU_MM} mm 銅、溫升 {TEMP_RISE:g} °C):")
    bad = add_planes(board)
    if bad:
        print("!! 電源平面自檢失敗,拒絕寫出:")
        for p in bad:
            print("   ", p)
        out.unlink()  # build() 已經寫出沒有平面的板檔;不留半成品
        raise SystemExit(1)
    pcbgen.stable_uuids(board, "cm5")
    pcbnew.SaveBoard(str(out), board)
