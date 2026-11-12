"""CM5 載板:網表 → cm5.kicad_pcb(板框、4 層、網路類別、固定孔、內層平面、電源級鋪銅、自檢)。

佈線第一、二階段:兩級降壓的鋪銅、過孔與閘極驅動(gen/power_stage.py);第三階段:差分線
(gen/diff_pairs.py)。其餘還沒佈線。
座標與自動擺件在 gen/placement.py(3D 預覽 concept/ 也用同一份)。
必須用 KiCad 自帶的 python.exe 跑:
    <KiCad python> gen/pcb.py
"""
import fnmatch
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import pcbgen  # noqa: E402
import pcbnew  # noqa: E402
import diff_pairs  # noqa: E402
import fanout  # noqa: E402
import feeds  # noqa: E402
import power_stage  # noqa: E402
from pcbgen import BoardSpec, build  # noqa: E402
from placement import BOARD_HOLES, H, MODULE_HOLES, W, auto_place, sch_positions  # noqa: E402

BOARD = HERE.parent
pcbgen.EXTRA_FP_DIRS.append(str(BOARD / "footprints"))

# 接頭開口要切齊板邊,courtyard 本來就伸出板外;只查焊盤在板內
OVERHANG = ("J20", "J30", "J40", "J41", "J50", "J51", "J52", "J70", "SW51")

# 線寬 mm、間距 mm、網名。線寬由下面 CURRENTS 的電流算(power_width_problems 檢查);
# 阻抗控制的差分線寬見 README「差分阻抗」。每個網只對到一個類別。
NETCLASSES = (
    # 54 V 輸入。IPC-2221 表 6-1 的 51–100 V:外層有防焊(B4)0.13 mm、無塗層(B2)0.6 mm。
    # 板子有防焊,取 0.25 mm 留餘量。0.6 mm 做不到:RJ45 腳之間只有 0.53、IP804AR(QFN 0.5)0.25。
    ("HV54", 1.4, 0.25, "+54V", "VIN_RAW"),
    # PoE 輸出(含變壓器線側的線對),電壓同上
    ("PoE", 0.5, 0.25, "POE*"),
    # 開關節點:鋪銅(gen/power_stage.py);這裡的線寬只給 U10 SW 腳、R13 這些小分支
    ("Switch", 0.8, 0.25, "SW", "SW3"),
    # +5V / +3V3 的大電流路徑(USB/HDMI 開關、CM5、M.2)是 gen/feeds.py 的鋪銅與過孔;這裡的線寬只給
    # 其他接點(電容、QFN 腳)到平面的過孔。+3V3 接 LAN7800 / USB2514B 的 0.25 mm、0.5 mm 腳距 QFN 腳,
    # 線寬超過 0.25 就碰到隔壁腳;+5V 最遠的是風扇 J81(0.5 A,IPC-2221 外層 0.17 mm)。
    ("Rail5", 0.4, 0.2, "+5V"),
    ("Rail3", 0.25, 0.2, "+3V3"),
    ("USB5V", 0.75, 0.2, "USBA0_VBUS", "USBA1_VBUS", "HDMI_5V", "USBC_VBUS"),
)
# Default 類別(一般訊號)。0.25/0.2 鑽不出 QFN 0.5 mm(LAN7800、IP804AR、USB2514B)與 CM5
# 連接器 0.4 mm:freerouting 扇出只拉出 58.6% 的 SMD 腳、40 輪剩 127 條以上。
# 0.15/0.15 仍高於 JLCPCB 4 層板最小線寬/線距 0.09 mm。
DEFAULT_CLASS = (0.15, 0.15)
# Power 類別(GND 與小電源)。0.25:同上,QFN 腳;這些網最大是 CM5_3V3 的 0.6 A(IPC-2221 外層 0.17 mm)
POWER_W = 0.25
POWER = ("GND", "CM5_3V3", "IP_3V3", "LAN0_1V2", "LAN1_1V2", "LAN0_2V5", "LAN1_2V5")

# ── 外層電源走線的電流(IPC-2221 §6.2 外層,1 oz,溫升 10 °C)─────────────────
# (網, 最大電流 A, 依據)。取「保護動作前能一直流的電流」:限流開關取限流上限,不是額定。
# 佈線後同一條網的最窄處都要 ≥ 算出的寬度;現在先檢查網路類別的線寬。
CURRENTS = (
    ("VIN_RAW", 3.0, "120 W ÷ UVLO 40 V(J20 → F1)"),
    ("+54V", 3.0, "同上(F1 → C10、Q10、F40/F41)"),
    ("POE0_P", 0.92, "IP804AR 限流上限(gen/board.py 區塊 6);F40 1.5 A 只在故障時斷"),
    ("POE0_N", 0.92, "同上,回流"),
    ("POE1_P", 0.92, "同上"),
    ("POE1_N", 0.92, "同上,回流"),
    # +5V(→ U62/U63/U70、CM5)與 +3V3(→ M.2)的外層大電流路徑由 gen/feeds.py 的鋪銅檢查
    ("USBA0_VBUS", 1.9, "AP2171W 限流上限"),
    ("USBA1_VBUS", 1.9, "AP2171W 限流上限"),
    ("HDMI_5V", 1.05, "TPS2051C 限流上限"),
    ("USBC_VBUS", 0.5, "USB 2.0 預設電流(燒錄口,受電端)"),
)
# 開關節點(SW、SW3)、降壓器輸出到內層平面的過孔:gen/power_stage.py 的 CORRIDORS / VIA_LINKS
OUTER_CU_MM = 0.035     # JLC04161H 外層 1 oz(jlcpcb.com/impedance)
VIA_PLATING_MM = 0.018  # JLC 孔銅最小 18 µm
CU_RESISTIVITY = 1.72e-5  # Ω·mm,20 °C


def placement(net_path: Path) -> dict:
    comps, pad_net = pcbgen.read_netlist(net_path)
    fps = {}
    for ref, info in comps.items():
        lib, name = info["footprint"].split(":")
        fp = pcbnew.FootprintLoad(str(pcbgen.fp_lib_dir(lib)), name)
        if fp is None:
            raise SystemExit(f"{ref}: 载入封装失败 {info['footprint']}")
        fps[ref] = fp
    return auto_place(fps, pad_net, sch_positions(BOARD / "cm5.kicad_sch"))


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
        default_class=DEFAULT_CLASS,
        power_width=POWER_W,
        # freerouting 2.5.0 扇出時無視「關閉收窄」(上游 #973,修正已合併、未發版),會收到 0.1124 mm;
        # JLCPCB 4 層板最小線寬 0.09 mm,0.1 仍做得到
        track_min=0.1,
        # In1 整片 GND(差分線參考面)、In2 電源平面:不能讓 freerouting 在上面走線
        plane_layers=("In1.Cu", "In2.Cu"),
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
PLANE_MIN_ISLAND_MM2 = 3.0
TEMP_RISE = 10.0       # °C


def ipc2221_area_mil2(amps: float, k: float) -> float:
    """IPC-2221 §6.2:I = k·ΔT^0.44·A^0.725 → 截面積 A(mil²)。外層 k = 0.048、內層 0.024。"""
    return (amps / (k * TEMP_RISE ** 0.44)) ** (1 / 0.725)


def ipc2221_outer_width(amps: float) -> float:
    """外層走線需要的寬度 mm。"""
    return ipc2221_area_mil2(amps, 0.048) / (OUTER_CU_MM / 0.0254) * 0.0254


def via_amps() -> float:
    """一個過孔(鑽孔 VIA_DRILL、孔銅 VIA_PLATING_MM)能流的電流:孔壁截面積套內層公式(保守)。"""
    area_mm2 = math.pi * pcbgen.VIA_DRILL * VIA_PLATING_MM
    return 0.024 * TEMP_RISE ** 0.44 * (area_mm2 / 0.0254 ** 2) ** 0.725


def class_width(net: str) -> float:
    """這條網的走線寬度 mm(網路類別 → Power → 預設)。"""
    for _, width, _, *patterns in NETCLASSES:
        if any(fnmatch.fnmatchcase(net, p) for p in patterns):
            return width
    return POWER_W if net in POWER else DEFAULT_CLASS[0]


def power_width_problems(nets) -> list[str]:
    """CURRENTS 每條網的類別線寬 ≥ IPC-2221 外層寬度;回傳問題清單(空 = 通過)。"""
    problems = []
    print(f"外層電源走線(IPC-2221 外層 {OUTER_CU_MM} mm 銅、溫升 {TEMP_RISE:g} °C):")
    for net, amps, why in CURRENTS:
        if net not in nets:
            problems.append(f"CURRENTS 的 {net} 不在網表裡")
            continue
        need, have = ipc2221_outer_width(amps), class_width(net)
        tag = "OK" if have >= need else "!!"
        print(f"  {tag} {net:10} {amps:5.2f} A  線寬 {have:4.2f} mm(需要 {need:4.2f})  {why}")
        if have < need:
            problems.append(f"{net} 線寬 {have} mm < IPC-2221 {need:.2f} mm({amps} A)")
    return problems


def make_pours(board, pours) -> dict:
    """(名字, 網, 多邊形[, 層]) → 有名字的鋪銅(預設 F.Cu)。"""
    zones = {}
    for name, net, pts, *layer in pours:
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID(layer[0]) if layer else pcbnew.F_Cu)
        z.SetNet(board.FindNet(net))
        z.SetZoneName(name)
        z.SetAssignedPriority(1)  # 蓋過 lib/route.py 之後鋪的整面 GND(優先序 0)
        z.SetLocalClearance(pcbgen.mm(0.25))
        z.SetMinThickness(pcbgen.mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)  # 大電流:焊盤實心連接
        o = z.Outline()
        o.NewOutline()
        for x, y in pts:
            o.Append(pcbgen.at(x, y))
        board.Add(z)
        zones[name] = z
    return zones


def make_vias(board, zones, fields) -> dict:
    """(銅區名字, [(x, y)…]) → 鎖定的過孔,網跟銅區。"""
    vias = {}
    for name, pts in fields:
        net = board.FindNet(zones[name].GetNetname())
        for x, y in pts:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbgen.at(x, y))
            v.SetWidth(pcbgen.mm(pcbgen.VIA_D))
            v.SetDrill(pcbgen.mm(pcbgen.VIA_DRILL))
            v.SetNet(net)
            v.SetLocked(True)  # lib/route.py 重新匯入佈線時保留
            board.Add(v)
            vias.setdefault(name, []).append(v)
    return vias


def _fill(z):
    return z.GetFilledPolysList(z.GetLayer())


def check_pours(zones, vias, corridors, via_links, also=()) -> list[str]:
    """填充後:鋪銅不空、過孔在銅上(also:另一層的鋪銅也要)、載流截面、過孔數。印報告,回傳問題。"""
    problems = []
    for name, z in zones.items():
        if _fill(z).Area() == 0:
            problems.append(f"鋪銅「{name}」填充後是空的")
    for name, vs in vias.items():
        targets = [name] + [b for a, b in also if a == name]
        for t in targets:
            off = [v for v in vs if not _fill(zones[t]).Contains(v.GetPosition())]
            if off:
                problems.append(f"「{name}」有 {len(off)} 個過孔不在「{t}」的銅上")

    print(f"  載流截面(IPC-2221 外層;短頸 ≤ {power_stage.SHORT_NECK_MM:g} mm 改算 I²R):")
    for name, amps, (x0, y0, x1, y1), flow, what in corridors:
        rect = pcbnew.SHAPE_POLY_SET()
        rect.NewOutline()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            rect.Append(pcbgen.at(x, y))
        rect.BooleanSubtract(_fill(zones[name]))
        outside = rect.Area() / 1e12  # nm² → mm²
        width, length = ((x1 - x0), (y1 - y0)) if flow == "y" else ((y1 - y0), (x1 - x0))
        need = ipc2221_outer_width(amps)
        loss = amps ** 2 * CU_RESISTIVITY * length / (width * OUTER_CU_MM)
        neck_ok = length <= power_stage.SHORT_NECK_MM and loss <= power_stage.NECK_LOSS_MAX_W
        ok = outside < 1e-3 and (width >= need or neck_ok)
        note = "" if width >= need else f";短頸 {length:.2f} mm,I²R {loss * 1000:.0f} mW"
        print(f"  {'OK' if ok else '!!'} {name:12} {amps:5.1f} A  寬 {width:4.2f} mm(IPC-2221 {need:4.2f}){note}  {what}")
        if outside >= 1e-3:
            problems.append(f"「{name}」截面「{what}」有 {outside:.2f} mm² 沒鋪到銅")
        elif not ok:
            problems.append(f"「{name}」截面「{what}」寬 {width:.2f} mm < IPC-2221 {need:.2f} mm,"
                            f"且不是短頸(長 {length:.2f} mm、I²R {loss:.2f} W)")

    per_via = via_amps()
    print(f"  過孔(鑽 {pcbgen.VIA_DRILL} mm、孔銅 {VIA_PLATING_MM * 1000:g} µm):每個 {per_via:.2f} A")
    for name, amps, why in via_links:
        need, have = math.ceil(amps / per_via), len(vias.get(name, []))
        print(f"  {'OK' if have >= need else '!!'} {name:12} {amps:4.1f} A  {have} 個(至少 {need})  {why}")
        if have < need:
            problems.append(f"「{name}」過孔 {have} 個 < {need}({amps} A)")
    return problems


def add_power_stage(board) -> list[str]:
    """電源級的外層鋪銅與鎖定過孔(gen/power_stage.py),填充後檢查;回傳問題清單(空 = 通過)。"""
    zones = make_pours(board, power_stage.POURS)
    vias = make_vias(board, zones, power_stage.VIA_FIELDS)
    for net, layer, w, pts in power_stage.TRACKS:
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetLayer(board.GetLayerID(layer))
            t.SetStart(pcbgen.at(*a))
            t.SetEnd(pcbgen.at(*b))
            t.SetWidth(pcbgen.mm(w))
            t.SetNet(board.FindNet(net))
            t.SetLocked(True)
            board.Add(t)
    for net, x, y in power_stage.TRACK_VIAS:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbgen.at(x, y))
        v.SetWidth(pcbgen.mm(pcbgen.VIA_D))
        v.SetDrill(pcbgen.mm(pcbgen.VIA_DRILL))
        v.SetNet(board.FindNet(net))
        v.SetLocked(True)
        board.Add(v)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    problems = []
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    for net in power_stage.ROUTED_NETS:
        pads = [p for p in board.GetPads() if p.GetNetname() == net]
        # GetConnectedItems 回傳整個連通群(含自己);SWIG 每次給新的包裝物件,用名字比
        reached = {pad_name(x) for x in conn.GetConnectedItems(pads[0]) if x.GetClass() == "PAD"} if pads else set()
        loose = [pad_name(p) for p in pads if pad_name(p) not in reached]
        if not pads or loose:
            problems.append(f"手佈的網 {net} 沒接通:{', '.join(loose) or '沒有焊盤'}")
    print("電源級鋪銅(F.Cu):")
    problems += check_pours(zones, vias, power_stage.CORRIDORS, power_stage.VIA_LINKS)
    return problems


def pad_name(p) -> str:
    return f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}"


def class_clearance(net: str) -> float:
    for _, _, clearance, *patterns in NETCLASSES:
        if any(fnmatch.fnmatchcase(net, p) for p in patterns):
            return clearance
    return pcbgen.CLEARANCE if net in POWER else DEFAULT_CLASS[1]


# 晶振的兩支 GND 腳(2、4,斜對角)在晶振底下用一段線接起來,只留一個過孔:扇出原本兩支腳各打一個,
# 往外的那個剛好落在 XI 或 XO 繞過去的路上(LAN7800 的 XO 從晶振西南角繞上去、Hub 的 XI 從東南角往西)。
# 過孔自己放(扇出只在散熱焊盤之後重算連線,2 腳打的過孔 4 腳看不到,會再打一個):(位號, 哪支 GND 腳外側, 偏移 mm)
CRYSTAL_GND = (("Y40", "2", (0.9, -0.6)), ("Y41", "2", (0.9, -0.6)), ("Y60", "4", (-0.9, -0.25)))


def add_crystal_ground(board) -> list[str]:
    gnd = board.FindNet("GND")
    for ref, via_pad, off in CRYSTAL_GND:
        fp = board.FindFootprintByReference(ref)
        pads = {p.GetNumber(): p for p in fp.Pads()}
        if pads["2"].GetNetname() != "GND" or pads["4"].GetNetname() != "GND":
            return [f"{ref} 的 2、4 腳不是 GND"]
        ends = [(pads["2"].GetPosition(), pads["4"].GetPosition())]
        at = pads[via_pad].GetPosition() + pcbnew.VECTOR2I(pcbgen.mm(off[0]), pcbgen.mm(off[1]))
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(at)
        v.SetWidth(pcbgen.mm(pcbgen.VIA_D))
        v.SetDrill(pcbgen.mm(pcbgen.VIA_DRILL))
        v.SetNet(gnd)
        v.SetLocked(True)
        board.Add(v)
        ends.append((pads[via_pad].GetPosition(), at))
        for a, b in ends:
            t = pcbnew.PCB_TRACK(board)
            t.SetLayer(pcbnew.F_Cu)
            t.SetStart(a)
            t.SetEnd(b)
            t.SetWidth(pcbgen.mm(0.25))
            t.SetNet(gnd)
            t.SetLocked(True)
            board.Add(t)
    return []


# LAN7800 北側手佈(gen/placement.py 的擺法):晶振轉 90°,XI(1 腳)在右下、XO(3 腳)在左上。
# - XI:40 腳直上進晶振 1 腳,再往東接負載電容。
# - XO:41 腳直上,在 1.2V 電容的 GND 過孔上方往西,沿晶振西側上去接 3 腳與負載電容 —— 不和 XI 交叉。
# - 42、44 腳(1.2V)在 43 腳上方用一段橫線接起來,1.2V 電容的 1 腳就壓在這段線上;
#   43 腳(PME_MODE,接地)往內接散熱焊盤,不必往外拉線。
# - 1.2V 電容的 GND 過孔手放(扇出會放在 XO 要走的地方)。
# (晶片, 晶振, XI 負載電容, XO 負載電容, 1.2V 電容)
LAN_NORTH = (("U40", "Y40", "C118", "C119", "C114"), ("U41", "Y41", "C148", "C149", "C143"))
XO_WEST_X = -0.9    # XO 往上那段:晶振 3 腳中心往西 mm(離晶振 GND 腳 0.25、C109 的 GND 過孔 0.375)
CAP_VIA_DY = -0.72  # 1.2V 電容 GND 過孔:2 腳中心往北 mm
XO_ABOVE_VIA = 0.6  # XO 往西那段:過孔中心再往北 mm(過孔半徑 0.3 + GND 的 Power 類間距 0.2 + 半線寬 0.075)
LINK_DY = -0.85     # 42–44 橫線:腳中心往北 mm(離 43 腳焊盤 0.33)


def add_lan_north(board) -> list[str]:
    from pcbnew import VECTOR2I as V

    def track(net, pts, w, layer=pcbnew.F_Cu):
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetLayer(layer)
            t.SetStart(a)
            t.SetEnd(b)
            t.SetWidth(pcbgen.mm(w))
            t.SetNet(board.FindNet(net))
            t.SetLocked(True)
            board.Add(t)

    def pad(ref, num):
        return {p.GetNumber(): p for p in board.FindFootprintByReference(ref).Pads()}[num]

    def xy(p):
        return p.GetPosition()

    bad = []
    for u, y, cxi, cxo, c12 in LAN_NORTH:
        p40, p41, p42, p43, p44 = (pad(u, n) for n in ("40", "41", "42", "43", "44"))
        xi, xo = pad(y, "1"), pad(y, "3")
        want = ((p40, "_XI"), (p41, "_XO"), (xi, "_XI"), (xo, "_XO"), (p42, "_1V2"), (p44, "_1V2"))
        for p, suffix in want:
            if not p.GetNetname().endswith(suffix):
                bad.append(f"{u} 北側手佈:{p.GetParentFootprint().GetReference()}.{p.GetNumber()} 是 {p.GetNetname()}")
        if p43.GetNetname() != "GND" or pad(c12, "2").GetNetname() != "GND":
            bad.append(f"{u} 北側手佈:43 腳或 {c12}.2 不是 GND")
        if bad:
            return bad
        net = lambda p: p.GetNetname()  # noqa: E731
        # XI:40 腳直上到晶振 1 腳的高度,再往東經 1 腳中心到負載電容
        track(net(p40), [xy(p40), V(xy(p40).x, xy(xi).y), xy(xi), xy(pad(cxi, "1"))], 0.15)
        # 1.2V 電容 GND 過孔
        c2 = xy(pad(c12, "2"))
        via_at = V(c2.x, c2.y + pcbgen.mm(CAP_VIA_DY))
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(via_at)
        v.SetWidth(pcbgen.mm(pcbgen.VIA_D))
        v.SetDrill(pcbgen.mm(pcbgen.VIA_DRILL))
        v.SetNet(board.FindNet("GND"))
        v.SetLocked(True)
        board.Add(v)
        track("GND", [c2, via_at], 0.25)
        # XO
        yj = via_at.y - pcbgen.mm(XO_ABOVE_VIA)
        xw = xy(xo).x + pcbgen.mm(XO_WEST_X)
        track(net(p41), [xy(p41), V(xy(p41).x, yj), V(xw, yj), V(xw, xy(xo).y), xy(xo)], 0.15)
        track(net(p41), [V(xw, xy(xo).y), xy(pad(cxo, "1"))], 0.15)
        # 42–44 橫線 + 1.2V 電容 1 腳
        yl = xy(p42).y + pcbgen.mm(LINK_DY)
        c1 = xy(pad(c12, "1"))
        track(net(p42), [xy(p44), V(xy(p44).x, yl), V(xy(p42).x, yl), xy(p42)], 0.2)
        track(net(p42), [V(c1.x, yl), c1], 0.2)
        # 43 腳往內接散熱焊盤
        ep = xy(pad(u, "49"))
        track("GND", [xy(p43), V(xy(p43).x, xy(p43).y + (pcbgen.mm(1.2) if ep.y > xy(p43).y else -pcbgen.mm(1.2)))], 0.2)
        bad += lan_rest(u, pad, track)
    return bad


def add_u10_ss(board) -> list[str]:
    """LM5146 SS(3 腳)直上 C18 1 腳(gen/placement.py 擺在 3 腳正上方)。不先佈的話 COMP 會從 4 腳往上再往東繞回來把它關住。"""
    pads = {q.GetNumber(): q for q in board.FindFootprintByReference("U10").Pads()}
    c1 = {q.GetNumber(): q for q in board.FindFootprintByReference("C18").Pads()}["1"]
    p3 = pads["3"]
    if p3.GetNetname() != "SS" or c1.GetNetname() != "SS":
        return [f"U10 SS 手佈:U10.3 是 {p3.GetNetname()}、C18.1 是 {c1.GetNetname()}"]
    a, b = p3.GetPosition(), c1.GetPosition()
    d = abs(b.x - a.x)
    pts = [a, pcbnew.VECTOR2I(a.x, b.y + pcbgen.mm(0.58) + d), pcbnew.VECTOR2I(b.x, b.y + pcbgen.mm(0.58)), b]
    for u, v in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(pcbnew.F_Cu)
        t.SetStart(u)
        t.SetEnd(v)
        t.SetWidth(pcbgen.mm(0.15))
        t.SetNet(board.FindNet("SS"))
        t.SetLocked(True)
        board.Add(t)
    return []


HUB_XI_JOG = 0.18   # XI(U61 33 腳)往東偏,讓開 C207(PLLFILT)的焊盤
HUB_XI_DY = 1.05    # XI 橫線在晶振 1 腳中心往南 mm(C209 焊盤與 C207 焊盤之間)


def add_hub_xi(board) -> list[str]:
    """Hub 晶振 XI:33 腳往上、在晶振南邊往西、上到晶振 1 腳再接 C208。freerouting 常把 XO 繞到 33 腳上方把它關住。"""
    def pad(ref, num):
        return {q.GetNumber(): q for q in board.FindFootprintByReference(ref).Pads()}[num]

    def mmxy(q):
        return (q.GetPosition().x / 1e6 - pcbgen.ORIGIN[0], q.GetPosition().y / 1e6 - pcbgen.ORIGIN[1])

    p33, y1, c1 = pad("U61", "33"), pad("Y60", "1"), pad("C208", "1")
    bad = [f"Hub XI 手佈:{q.GetParentFootprint().GetReference()}.{q.GetNumber()} 是 {q.GetNetname()}"
           for q in (p33, y1, c1) if q.GetNetname() != "HUB_XI"]
    if bad:
        return bad
    (x, y), (xy1, yy1) = mmxy(p33), mmxy(y1)
    xj, yl = x + HUB_XI_JOG, yy1 + HUB_XI_DY
    pts = [(x, y), (x, y - 0.51), (xj, y - 0.51 - HUB_XI_JOG), (xj, yl), (xy1, yl), (xy1, yy1), mmxy(c1)]
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbgen.at(*a))
        t.SetEnd(pcbgen.at(*b))
        t.SetWidth(pcbgen.mm(0.15))
        t.SetNet(board.FindNet("HUB_XI"))
        t.SetLocked(True)
        board.Add(t)
    return bad


VCC3_DY = 1.0       # VCC3 橫線在 17 腳中心往南 mm(避開 16 腳)


def add_u20_vcc(board) -> list[str]:
    """TPS568230 的 VCC3(17 腳)→ 橫線 → R23 1 腳、C48 1 腳;MODE3(15 腳)→ R23 2 腳。先手佈再扇出。"""
    def pad(ref, num):
        return {q.GetNumber(): q for q in board.FindFootprintByReference(ref).Pads()}[num]

    def mmxy(q):
        return (q.GetPosition().x / 1e6 - pcbgen.ORIGIN[0], q.GetPosition().y / 1e6 - pcbgen.ORIGIN[1])

    p15, p17, r1, r2, c1 = pad("U20", "15"), pad("U20", "17"), pad("R23", "1"), pad("R23", "2"), pad("C48", "1")
    bad = [f"U20 VCC3 手佈:{q.GetParentFootprint().GetReference()}.{q.GetNumber()} 是 {q.GetNetname()}"
           for q, n in ((p15, "MODE3"), (r2, "MODE3"), (p17, "VCC3"), (r1, "VCC3"), (c1, "VCC3")) if q.GetNetname() != n]
    if bad:
        return bad

    def track(net, pts, w):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetLayer(pcbnew.F_Cu)
            t.SetStart(pcbgen.at(*a))
            t.SetEnd(pcbgen.at(*b))
            t.SetWidth(pcbgen.mm(w))
            t.SetNet(board.FindNet(net))
            t.SetLocked(True)
            board.Add(t)

    (x17, y17), (xr1, yr1), (xc, yc) = mmxy(p17), mmxy(r1), mmxy(c1)
    yl = y17 + VCC3_DY
    track("VCC3", [(x17, y17), (x17, yl), (min(xr1, xc), yl)], 0.3)
    track("VCC3", [(xr1, yl), (xr1, yr1)], 0.3)
    track("VCC3", [(xc, yl), (xc, yc)], 0.3)
    track("MODE3", [mmxy(p15), mmxy(r2)], 0.2)
    return bad


# REXT 電阻、FILT 與北側 2.5V 電容(gen/placement.py)
LAN_REST = {"U40": ("R100", "C117", "C109"), "U41": ("R130", "C147", "C139")}
REXT_X = 0.15        # REXT 線在 FILT、2.5V 兩顆電容之間:47 腳往東偏 mm
V45_DY = -1.25       # 45 腳(2.5V)正上方的過孔:離腳中心 mm(避開 44 腳往北那段)
V21_DY = 1.0         # 21 腳(1.2V)正下方的過孔


def lan_rest(u, pad, track) -> list[str]:
    """北側 47 腳(REXT)、48 腳(FILT)、45 腳(2.5V)與南側 21 腳(1.2V)先手佈,扇出才不會把 +3V3 過孔打在出口上。

    45 腳經過孔在 B.Cu 接西側 3、6、9、12 腳的過孔(gen/diff_pairs.py V2V5_X);21 腳經過孔在 B.Cu 接 25 腳那個過孔。"""
    from pcbnew import VECTOR2I as V
    rext, cfilt, c25 = LAN_REST[u]
    p = {n: pad(u, n) for n in ("12", "15", "21", "25", "45", "47", "48")}
    want = ((p["47"], "_REXT"), (pad(rext, "1"), "_REXT"), (p["48"], "_FILT"), (pad(cfilt, "1"), "_FILT"),
            (p["45"], "_2V5"), (pad(c25, "1"), "_2V5"), (p["12"], "_2V5"), (p["15"], "_1V2"), (p["21"], "_1V2"), (p["25"], "_1V2"))
    bad = [f"{u} 手佈:{q.GetParentFootprint().GetReference()}.{q.GetNumber()} 是 {q.GetNetname()}"
           for q, suf in want if not q.GetNetname().endswith(suf)]
    if bad:
        return bad
    xy = lambda q: q.GetPosition()  # noqa: E731
    mm = pcbgen.mm

    def via(net, at):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(at)
        v.SetWidth(mm(pcbgen.VIA_D))
        v.SetDrill(mm(pcbgen.VIA_DRILL))
        v.SetNet(board.FindNet(net))
        v.SetLocked(True)
        board.Add(v)

    board = p["47"].GetBoard()
    # REXT:47 腳往上,斜到兩顆電容中間再直上電阻 1 腳
    r1, a = xy(pad(rext, "1")), xy(p["47"])
    xr = a.x + mm(REXT_X)
    track(p["47"].GetNetname(), [a, V(a.x, a.y - mm(0.65)), V(xr, a.y - mm(0.65) - mm(REXT_X)), V(xr, r1.y), r1], 0.15)
    # FILT:48 腳直上電容 1 腳
    f1 = xy(pad(cfilt, "1"))
    track(p["48"].GetNetname(), [xy(p["48"]), V(xy(p["48"]).x, f1.y), f1], 0.2)
    # 2.5V:45 腳 → 過孔 → 電容 1 腳;B.Cu 從這個過孔往西接到西側那排過孔(V2V5_X),一路到 12 腳那個
    n25 = p["45"].GetNetname()
    v45 = V(xy(p["45"]).x, xy(p["45"]).y + mm(V45_DY))
    via(n25, v45)
    track(n25, [xy(p["45"]), v45, xy(pad(c25, "1"))], 0.25)
    xb = mm(diff_pairs.V2V5_X + pcbgen.ORIGIN[0])
    top = xy(p["12"]).y - mm(4.5)          # 3 腳那個過孔
    track(n25, [v45, V(xb + mm(1.05), v45.y), V(xb, v45.y + mm(1.05)), V(xb, xy(p["12"]).y)], 0.3, pcbnew.B_Cu)
    if v45.y + mm(1.05) > top:
        bad.append(f"{u} 2.5V B.Cu 線轉角低於 3 腳的過孔")
    # 1.2V:21 腳 → 正下方過孔 → B.Cu 接 25 腳的過孔(gen/diff_pairs.py EXTRA_VIAS)
    n12 = p["21"].GetNetname()
    v21 = V(xy(p["21"]).x, xy(p["21"]).y + mm(V21_DY))
    via(n12, v21)
    track(n12, [xy(p["21"]), v21], 0.25)
    v25 = V(xy(p["25"]).x + mm(0.95), xy(p["25"]).y + mm(0.85))      # (50.4, 65.6):25 腳往東南那個
    track(n12, [v21, V(v25.x - (v21.y - v25.y), v21.y), v25], 0.3, pcbnew.B_Cu)
    # 15 腳(1.2V)夾在 14 腳(+3V3 扇出過孔)與 17–19 腳中間:同樣正下方打過孔,B.Cu 接 21 腳那個
    v15 = V(xy(p["15"]).x, v21.y)
    via(n12, v15)
    track(n12, [xy(p["15"]), v15], 0.25)
    track(n12, [v15, v21], 0.3, pcbnew.B_Cu)
    return bad


# 平面網路 → 內層。這些網的 SMD 焊盤由 lib/fanout.py 先打好過孔(freerouting 不在平面層走線,也就不扇出)
PLANE_NETS = {"GND": pcbnew.In1_Cu, "+3V3": pcbnew.In2_Cu, "+5V": pcbnew.In2_Cu}


def add_fanout(board) -> list[str]:
    """平面網路焊盤的扇出過孔;找不到位置的列出(交給 freerouting,不擋流程)。"""
    r = fanout.fanout(board, PLANE_NETS, pcbgen.VIA_D, pcbgen.VIA_DRILL, class_width, class_clearance)
    print(f"平面網路扇出(lib/fanout.py):放了 {r['placed']} 個過孔;找不到位置 {len(r['skipped'])} 個:"
          f"{' '.join(r['skipped'])}")
    return []


def add_feeds(board) -> list[str]:
    """外層供電支線(gen/feeds.py):鋪銅、過孔,填充後檢查;最後每支目標腳要接到同網的 In2 平面。"""
    zones = make_pours(board, feeds.POURS)
    vias = make_vias(board, zones, feeds.VIA_FIELDS)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print("外層供電支線(gen/feeds.py):")
    problems = check_pours(zones, vias, feeds.CORRIDORS, feeds.VIA_LINKS, feeds.VIA_ALSO)
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    for ref, *nums in feeds.PLANE_PADS:
        for p in board.FindFootprintByReference(ref).Pads():
            if p.GetNumber() not in nums:
                continue
            planes = [z for z in conn.GetConnectedItems(p) if z.GetClass() == "ZONE"
                      and z.GetLayer() == pcbnew.In2_Cu and z.GetNetname() == p.GetNetname()]
            if not planes:
                problems.append(f"{pad_name(p)}({p.GetNetname()})沒接到 In2 平面")
    return problems


def add_diff_pairs(board) -> list[str]:
    """差分線(gen/diff_pairs.py):鎖定的走線與過孔;檢查手性、對內長度差、每條網接通。回傳問題清單。"""
    problems = []

    def at_mm(p):
        return (p.GetPosition().x / 1e6 - pcbgen.ORIGIN[0], p.GetPosition().y / 1e6 - pcbgen.ORIGIN[1])

    def ends(refs, pnet, nnet):
        """refs 裡可寫 "J50.B6":只用那支腳(USB-C 每條資料線有兩支腳)。"""
        pads = {p.GetNetname(): at_mm(p) for r in refs
                for p in board.FindFootprintByReference(r.split(".")[0]).Pads()
                if p.GetNetname() in (pnet, nnet) and ("." not in r or p.GetNumber() == r.split(".")[1])}
        return {"P": pads.get(pnet), "N": pads.get(nnet)}

    def pads_of(ref, net):
        return [at_mm(p) for p in board.FindFootprintByReference(ref).Pads() if p.GetNetname() == net]

    def via(net, x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbgen.at(x, y))
        v.SetWidth(pcbgen.mm(pcbgen.VIA_D))
        v.SetDrill(pcbgen.mm(pcbgen.VIA_DRILL))
        v.SetNet(board.FindNet(net))
        v.SetLocked(True)
        board.Add(v)

    def track(net, layer, w, pts):
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1e-4:
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetLayer(board.GetLayerID(layer))
            t.SetStart(pcbgen.at(*a))
            t.SetEnd(pcbgen.at(*b))
            t.SetWidth(pcbgen.mm(w))
            t.SetNet(board.FindNet(net))
            t.SetLocked(True)
            board.Add(t)

    print(f"差分線(對內長度差上限 {diff_pairs.SKEW_MAX} mm):")
    lengths = {}
    for pair in diff_pairs.PAIRS:
        name, pnet, nnet, cls, src, dst = pair[:6]
        start, end = ends(src, pnet, nnet), ends(dst, pnet, nnet)
        if None in (*start.values(), *end.values()):
            problems.append(f"{name}:起訖零件上找不到 {pnet} / {nnet} 的焊盤")
            continue
        tracks, vias, length, probs = diff_pairs.route(pair, start, end, pads_of)
        problems += probs
        for t in tracks:
            track(*t)
        for v in vias:
            via(*v)
        skew = abs(length["P"] - length["N"])
        lengths[name] = length["P"]
        print(f"  {'OK' if not probs else '!!'} {name:22} {cls} Ω  長 {length['P']:6.1f} mm  "
              f"差 {skew:.3f} mm  換層 {(sum(it[0] == 'via' for it in pair[6]) + 1) // 2} 次"
              + (f"  扭轉 {sum(it[0] == 'twist' for it in pair[6])} 次" if any(it[0] == "twist" for it in pair[6]) else ""))
    for group, limit in diff_pairs.GROUP_SKEW.items():
        got = [v for k, v in lengths.items() if k.startswith(group + " ")]
        spread = max(got) - min(got)
        print(f"  {'OK' if spread <= limit else '!!'} {group} 對與對之間差 {spread:.1f} mm(上限 {limit:g})")
        if spread > limit:
            problems.append(f"{group}:對與對之間長度差 {spread:.1f} mm > {limit:g} mm")
    stitch_tracks, stitch_vias = diff_pairs.stitch_copper()
    for t in (*diff_pairs.EXTRA_TRACKS, *stitch_tracks):
        track(*t)
    for v in (*diff_pairs.EXTRA_VIAS, *stitch_vias):
        via(*v)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())  # 平面與電源級鋪銅要讓開新的過孔

    board.BuildConnectivity()
    conn = board.GetConnectivity()
    pad_name = lambda p: f"{p.GetParentFootprint().GetReference()}.{p.GetNumber()}"  # noqa: E731
    for net in [n for pair in diff_pairs.PAIRS for n in pair[1:3]]:
        pads = [p for p in board.GetPads() if p.GetNetname() == net and pad_name(p) not in diff_pairs.LOOSE]
        reached = {pad_name(x) for x in conn.GetConnectedItems(pads[0]) if x.GetClass() == "PAD"} if pads else set()
        loose = [pad_name(p) for p in pads if pad_name(p) not in reached]
        if not pads or loose:
            problems.append(f"差分線 {net} 沒接通:{', '.join(loose) or '沒有焊盤'}")
    return problems


def ipc2221_inner_width(amps: float) -> float:
    """IPC-2221 §6.2 內層:I = 0.024·ΔT^0.44·A^0.725(A 為截面積 mil²)→ 需要的寬度 mm。

    這條公式對大面積平面很保守(IPC-2152 允許更小),當作下限檢查用。"""
    return ipc2221_area_mil2(amps, 0.024) / (INNER_CU_MM / 0.0254) * 0.0254


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
        # 還沒佈線,大塊平面可能還沒接到焊盤:只刪小於 PLANE_MIN_ISLAND_MM2 的孤島
        # (40-pin 排針腳之間約 2.2 mm²、過孔陣列之間 < 0.5 mm²),整塊平面留著
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
        z.SetMinIslandArea(int(PLANE_MIN_ISLAND_MM2 * 1e12))  # nm²
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


def tidy_silk(board) -> None:
    """位號超出板框、或壓到任何絲印圖形(含自己的)時移到 F.Fab(不印)。
    原則同 pcbgen.move_clashing_refs:不印總比印一半好。

    接頭(OVERHANG)本體的絲印伸出板邊是刻意的(開口切齊板邊),板廠會裁掉,DRC 的
    silk_edge_clearance 警告留著;不刪封裝裡的線,否則封裝和庫不一致(lib_footprint_mismatch)。"""
    edge = board.GetBoardEdgesBoundingBox()
    silk = [g for fp in board.GetFootprints() for g in fp.GraphicalItems()
            if g.GetLayer() == pcbnew.F_SilkS and g.Type() != pcbnew.PCB_TEXT_T]
    moved = []
    for fp in board.GetFootprints():
        ref = fp.Reference()
        if ref.GetLayer() != pcbnew.F_SilkS:
            continue
        # 用字形的實際外形比,不用外接框:外接框會把一堆其實沒碰到的位號也移走
        shape = ref.GetEffectiveShape(pcbnew.F_SilkS)
        if (not edge.Contains(shape.BBox())
                or any(shape.Collide(g.GetEffectiveShape(pcbnew.F_SilkS), 0) for g in silk)):
            ref.SetLayer(pcbnew.F_Fab)
            moved.append(fp.GetReference())
    if moved:
        print(f"位號出板或壓到絲印,移到 F.Fab: {', '.join(sorted(moved))}")


def decap_report(board, worst: int = 5) -> None:
    """IC 腳 → 同一條網上最近的對地電容(焊盤中心距離)。只報告,不擋:清單也包含 EN 這類不需要
    去耦的腳,哪些該去耦以 review.py 的 decoupling 規則為準。"""
    caps = {}  # 網 -> [(位號, x, y)]
    for fp in board.GetFootprints():
        nets = {p.GetNetname() for p in fp.Pads()}
        if fp.GetReference().startswith("C") and "GND" in nets and len(nets) == 2:
            for p in fp.Pads():
                if p.GetNetname() != "GND":
                    c = p.GetPosition()
                    caps.setdefault(p.GetNetname(), []).append((fp.GetReference(), c.x, c.y))
    far = {}  # (IC, 網) -> (距離 mm, 腳, 電容)
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("U"):
            continue
        for p in fp.Pads():
            n, c = p.GetNetname(), p.GetPosition()
            if n in caps:
                d, cref = min((math.hypot(c.x - x, c.y - y) / 1e6, r) for r, x, y in caps[n])
                k = (fp.GetReference(), n)
                if k not in far or d > far[k][0]:
                    far[k] = (d, p.GetNumber(), cref)
    ds = sorted(far.items(), key=lambda kv: -kv[1][0])
    n3 = sum(d <= 3 for d, *_ in far.values())
    n6 = sum(3 < d <= 6 for d, *_ in far.values())
    print(f"去耦電容(IC 腳 → 最近的對地電容):≤ 3 mm {n3}、3–6 mm {n6}、> 6 mm {len(far) - n3 - n6};最遠:")
    for (ic, n), (d, pin, cref) in ds[:worst]:
        print(f"  {d:5.1f} mm  {ic}.{pin} {n} → {cref}")


if __name__ == "__main__":
    net = BOARD / "net.txt"
    out = BOARD / "cm5.kicad_pcb"
    (BOARD / "cm5.kicad_dru").write_text(DRU + diff_pairs.dru(), encoding="utf-8")
    build(spec(placement(net)), net, out)
    board = pcbnew.LoadBoard(str(out))
    print(f"內層平面(IPC-2221 內層 {INNER_CU_MM} mm 銅、溫升 {TEMP_RISE:g} °C):")
    bad = add_planes(board)
    bad += power_width_problems({n.GetNetname() for n in board.GetNetsByName().values()})
    bad += add_power_stage(board)
    bad += add_diff_pairs(board)
    bad += add_feeds(board)
    bad += add_lan_north(board)
    bad += add_crystal_ground(board)
    bad += add_u20_vcc(board)
    bad += add_hub_xi(board)
    bad += add_u10_ss(board)
    bad += add_fanout(board)
    if bad:
        print("!! 電源 / 差分線自檢失敗,拒絕寫出:")
        for p in bad:
            print("   ", p)
        out.unlink()  # build() 已經寫出沒有平面、鋪銅的板檔;不留半成品
        raise SystemExit(1)
    decap_report(board)
    tidy_silk(board)
    pcbgen.stable_uuids(board, "cm5")
    pcbnew.SaveBoard(str(out), board)
