"""CM5 載板的正式擺件:網表 → cm5.kicad_pcb(板框、4 層、網路類別、固定孔、自檢)。

還沒佈線。座標與自動擺件在 gen/placement.py(3D 預覽 concept/ 也用同一份)。
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
    # 開關節點:電流太大,佈線時改鋪銅(見 POURS);這裡的線寬只是佈線器的起點
    ("Switch", 0.8, 0.25, "SW", "SW3"),
    # +5V 外層:平面 → U20 與 USB/HDMI 開關;+3V3 外層:平面 → M.2
    ("Rail5", 2.7, 0.2, "+5V"),
    ("Rail3", 1.1, 0.2, "+3V3"),
    ("USB5V", 0.75, 0.2, "USBA0_VBUS", "USBA1_VBUS", "HDMI_5V", "USBC_VBUS"),
)
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
    ("+5V", 4.85, "外層:平面 → U62/U63(AP2171W 限流上限 1.9 A ×2,Diodes DS31564 Rev 9-2)"
                  "+ U70(TPS2051C 0.5 A 檔 IOS 上限 1.05 A,TI SLVSAU6I §6.7,−40–125 °C);平面 → U20 約 2.9 A 較小"),
    ("+3V3", 2.5, "外層:平面 → M.2 J60(M.2 規範 3.3 V 上限)"),
    ("USBA0_VBUS", 1.9, "AP2171W 限流上限"),
    ("USBA1_VBUS", 1.9, "AP2171W 限流上限"),
    ("HDMI_5V", 1.05, "TPS2051C 限流上限"),
    ("USBC_VBUS", 0.5, "USB 2.0 預設電流(燒錄口,受電端)"),
)
# 電流太大、要鋪銅的網(佈線那一步做):(網, 電流 A, 說明)
POURS = (
    ("SW", 12.0, "LM5146 開關節點:Q10 源極 / Q11 汲極 → L10(輸出 12 A)"),
    ("SW3", 8.0, "TPS568230 開關節點 → L20(輸出 8 A)"),
)
# 降壓器輸出 → 內層平面的過孔:(網, 電流 A, 說明)。佈線後檢查 L10/L20 旁的過孔數。
VIA_LINKS = (
    ("+5V", 6.5, "L10 → In2 +5V 平面(CM5、40-pin、風扇;見 CORRIDORS)"),
    ("+3V3", 4.0, "L20 → In2 +3V3 平面(Hub、LAN7800、M.2;見 CORRIDORS)"),
)
OUTER_CU_MM = 0.035     # JLC04161H 外層 1 oz(jlcpcb.com/impedance)
VIA_PLATING_MM = 0.018  # JLC 孔銅最小 18 µm


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
    return pcbgen.POWER_W if net in POWER else pcbgen.TRACK_W


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
    for net, amps, why in POURS:
        print(f"  鋪銅 {net:8} {amps:5.1f} A  需要 {ipc2221_outer_width(amps):4.1f} mm 寬的銅  {why}")
    per_via = via_amps()
    print(f"過孔(鑽 {pcbgen.VIA_DRILL} mm、孔銅 {VIA_PLATING_MM * 1000:g} µm):每個 {per_via:.2f} A")
    for net, amps, why in VIA_LINKS:
        print(f"  {net:5} {amps:4.1f} A → 至少 {math.ceil(amps / per_via)} 個過孔  {why}")
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
    (BOARD / "cm5.kicad_dru").write_text(DRU, encoding="utf-8")
    build(spec(placement(net)), net, out)
    board = pcbnew.LoadBoard(str(out))
    print(f"內層平面(IPC-2221 內層 {INNER_CU_MM} mm 銅、溫升 {TEMP_RISE:g} °C):")
    bad = add_planes(board)
    bad += power_width_problems({n.GetNetname() for n in board.GetNetsByName().values()})
    if bad:
        print("!! 電源自檢失敗,拒絕寫出:")
        for p in bad:
            print("   ", p)
        out.unlink()  # build() 已經寫出沒有平面的板檔;不留半成品
        raise SystemExit(1)
    decap_report(board)
    pcbgen.stable_uuids(board, "cm5")
    pcbnew.SaveBoard(str(out), board)
