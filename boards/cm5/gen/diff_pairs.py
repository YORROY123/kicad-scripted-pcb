"""差分線(佈線第三階段)。座標 mm,板框左上為原點。

每對用一條中心線描述,程式切 45° 角、往兩側偏移成 P、N 兩條線,兩端接到起訖零件上 P、N 網的焊盤
(gen/pcb.py add_diff_pairs)。線寬與對內間距照 README「差分阻抗」(sim/diff_impedance.py)。

- 全部走 F.Cu:正下方是 In1 整片地(阻抗模擬的假設)。
- 交叉一定要換層時用 B.Cu 短暫下穿。B.Cu 的參考面是 In2(電源),所以下穿段越短越好,
  而且不跨 In2 的 +5V / +3V3 分界(+5V:x ≥ 60.25 且 y ≤ 71.75;其餘是 +3V3)。
  換層處不放地過孔:參考面從 In1(地)換到 In2(電源),地過孔接不到 In2,幫不上回流。
- 手性:兩端 P 在行進方向的哪一側必須一致(平面上不能讓 P、N 交叉)。不一致時 gen/pcb.py 失敗,
  要在原理圖上對調(只限可以反相的介面)或改走法。本階段的處理見 README「差分線」。
- 鎖定:freerouting 不動,lib/route.py 重新匯入時留下。
"""
from __future__ import annotations

import math

CLASSES = {          # 名字: (線寬, 對內間距) mm
    "90": (0.165, 0.15),    # PCIe、USB3、USB2
    "100": (0.145, 0.20),   # HDMI、乙太網路
}
CHAMFER = 0.8        # 直角切成兩個 45°,切掉的長度
VIA_PITCH = 1.0      # 換層處一對過孔的中心距
SKEW_MAX = 0.1       # 對內長度差上限 mm(CM5 規格書 2.3.1 的 PCIe 值,其他介面一併套用)
GROUP_SKEW = {"HDMI0": 25.0, "乙太網路": 50.0}  # 同一組對與對之間的長度差上限 mm(CM5 規格書 2.5.1、2.2.1)
KEEP = 0.3          # 自動擺件離差分線(含兩側)至少這麼遠
VIA_LEN = 1.6        # 一個 F.Cu ↔ B.Cu 過孔的長度 = 板厚(JLC04161H-3313)
TWIST_VIA = 0.8      # 扭轉時下穿那條的過孔離中心線


def twist_span(h: float) -> float:
    """扭轉段沿行進方向的長度。"""
    return 2 * (TWIST_VIA - h) + 2 * TWIST_VIA


# PCIe 在 J2 頂排往北出;REFCLK / TX 一路在 F.Cu,RX 在 x≈45 從 TX 底下穿過(J2 那端由北到南是
# TX、RX、CLK,插座那端要 RX、TX、CLK),再從插座南端繞到腳後(奇數腳在靠板邊那排)。
# LAN0 那組在 PCIe 北邊往西,到 x≈66–70 往南時從 PCIe 底下穿過去;USB2(LAN0_D)留在 B.Cu
# 一路到 U40 旁,從 TX 那對底下過,才能在 U40 東側排成 RX、TX、D(腳 31/32、28/29、26/27)。
# (名字, P 網, N 網, 類別, 起點零件, 終點零件, 路徑)
# 路徑:("F.Cu" | "B.Cu", [中心線點…]) 與 ("via", (x, y)) 交錯;過孔對垂直於行進方向排。
PAIRS = (
    ("PCIe REFCLK", "PCIE_CLK_P", "PCIE_CLK_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(104.5, 28.9), (104.5, 27.4), (39.6, 27.4), (37.6, 29.4), (1.6, 29.4), (1.6, 11.0),
                  (4.4, 11.0)]),
    ]),
    ("PCIe TX", "PCIE_TX_P", "PCIE_TX_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(106.9, 28.9), (106.9, 24.6), (40.6, 24.6), (37.2, 28.0), (2.6, 28.0), (2.6, 12.5),
                  (4.4, 12.5)]),
    ]),
    ("PCIe RX", "PCIE_RX_P", "PCIE_RX_N", "90", ("J2",), ("J60",), [
        ("F.Cu", [(105.7, 28.9), (105.7, 26.0), (48.7, 26.0)]),
        ("via", (48.0, 26.0)),
        ("B.Cu", [(47.3, 26.0), (46.6, 26.0), (43.8, 23.2), (43.1, 23.2)]),
        ("via", (42.8, 23.2)),
        ("F.Cu", [(42.1, 23.2), (40.0, 23.2), (36.6, 26.6), (3.6, 26.6), (3.6, 14.0), (4.4, 14.0)]),
    ]),
    ("USB3-0 RX(CM5 端)", "CM5U0_RX_P", "CM5U0_RX_N", "90", ("J2",), ("C120", "C121"), [
        ("F.Cu", [(108.1, 28.9), (108.1, 21.6), (70.4, 21.6), (70.4, 22.7)]),
        ("via", (70.4, 23.4)),
        ("B.Cu", [(70.4, 24.1), (70.4, 27.9)]),
        ("via", (70.4, 28.6)),
        ("F.Cu", [(70.4, 29.3), (70.4, 63.0), (57.8, 63.0)]),
    ]),
    ("USB3-0 TX(LAN7800 端)", "LAN0_TX_P", "LAN0_TX_N", "90", ("C120", "C121"), ("U40",), [
        ("F.Cu", [(55.2, 63.0), (50.6, 63.0)]),
    ]),
    ("USB3-0 RX(LAN7800 端)", "LAN0_RX_P", "LAN0_RX_N", "90", ("J2",), ("U40",), [
        ("F.Cu", [(110.5, 28.9), (110.5, 19.6), (66.0, 19.6), (66.0, 22.7)]),
        ("via", (66.0, 23.4)),
        ("B.Cu", [(66.0, 24.1), (66.0, 27.9)]),
        ("via", (66.0, 28.6)),
        ("F.Cu", [(66.0, 29.3), (66.0, 61.5), (50.6, 61.5)]),
    ]),
    ("USB2 LAN0", "LAN0_DP", "LAN0_DM", "90", ("J2",), ("U40",), [
        ("F.Cu", [(109.3, 28.9), (109.3, 20.6), (68.2, 20.6), (68.2, 22.7)]),
        ("via", (68.2, 23.4)),
        ("B.Cu", [(68.2, 24.1), (68.2, 64.6), (61.7, 64.6)]),
        ("via", (61.0, 64.6)),
        ("F.Cu", [(60.3, 64.6), (52.0, 64.6), (51.4, 64.0), (50.6, 64.0)]),
    ]),
    # J2 底排的 LAN1 那組往南出、在模組底下 y ≈ 35–38 往西,x ≈ 72–75 往南,y ≈ 77–81 往西進
    # C150/C151 與 U41(和 LAN0 同樣排法:U41 東側由北到南 RX、TX、D)。J2 那端由西到東是
    # CM5U1、D、RX,RX 要換到最北:在 x ≈ 105–112 從另外兩對底下穿過。
    # SS 兩對兩端手性一致(不用 ss_swap);USB2 那對兩端相反、又不能在原理圖對調(LAN7800 的
    # PORT_SWAP 要燒 OTP 才有預設值):在 U41 東邊扭轉一次。
    ("USB3-1 RX(CM5 端)", "CM5U1_RX_P", "CM5U1_RX_N", "90", ("J2",), ("C150", "C151"), [
        ("F.Cu", [(114.1, 33.1), (114.1, 37.0), (73.2, 37.0), (73.2, 79.0), (57.8, 79.0)]),
    ]),
    ("USB3-1 TX(LAN7800 端)", "LAN1_TX_P", "LAN1_TX_N", "90", ("C150", "C151"), ("U41",), [
        ("F.Cu", [(55.2, 79.0), (50.6, 79.0)]),
    ]),
    ("USB3-1 RX(LAN7800 端)", "LAN1_RX_P", "LAN1_RX_N", "90", ("J2",), ("U41",), [
        ("F.Cu", [(116.5, 33.1), (116.5, 39.8), (112.7, 39.8)]),
        ("via", (112.0, 39.8)),
        ("B.Cu", [(111.3, 39.8), (110.6, 39.8), (106.4, 35.6), (105.7, 35.6)]),
        ("via", (105.0, 35.6)),
        ("F.Cu", [(104.3, 35.6), (71.8, 35.6), (71.8, 77.5), (50.6, 77.5)]),
    ]),
    ("USB2 LAN1", "LAN1_DP", "LAN1_DM", "90", ("J2",), ("U41",), [
        ("F.Cu", [(115.3, 33.1), (115.3, 38.4), (74.6, 38.4), (74.6, 80.6), (66.0, 80.6)]),
        ("twist",),
        ("F.Cu", [(66.0 - twist_span(0.1575), 80.6), (52.0, 80.6), (51.4, 80.0), (50.6, 80.0)]),
    ]),
    # CM5 的 USB2(到 USB 切換 U60):往南時要過 LAN1 那組與 HDMI0,整段在 B.Cu 下穿(L3 為 +5V);
    # 上來後往東繞過 J1 東端、從東邊進 U60(轉 180°,讓 J1 的乙太網路可以從 J1 與 U60 之間往西)
    ("USB2 CM5", "CM5_USB_P", "CM5_USB_N", "90", ("J2",), ("U60",), [
        ("F.Cu", [(103.3, 33.1), (103.3, 33.2)]),
        ("via", (103.3, 33.9)),
        ("B.Cu", [(103.3, 34.6), (103.3, 53.9)]),
        ("via", (103.3, 54.6)),
        ("F.Cu", [(103.3, 55.3), (103.3, 56.4), (126.0, 56.4), (126.0, 75.75), (109.3, 75.75)]),
    ]),
    # U60(USB 切換)周圍三對的繞行順序和三個去向(CM5 東北、USB-C 東南、Hub 西)相反,一定有一對要換層。
    # Hub 上行那對在 U60 西邊打過孔到 B.Cu 後往回(東)走再往北:從 USB-C 那對底下穿過,
    # 往回走那一下 P/N 也左右翻過來,剛好修掉它兩端手性相反(USB2514B 的 PRT_SWAP 要 SMBus 設定)。
    ("USB2 Hub 上行", "HUB_UP_DP", "HUB_UP_DN", "90", ("U60",), ("U61",), [
        ("F.Cu", [(103.0, 76.25), (102.3, 76.25)]),
        ("via", (101.6, 76.25)),
        # B.Cu 往北到 y 72.3(不跨 L3 的 +5V / +3V3 分界 71.75)、往西到 Hub 正上方再往南;
        # 三個左轉都是 D+ 在外圈,三段直線留給補長凸起
        ("B.Cu", [(102.3, 76.25), (102.6, 76.25), (102.6, 72.3), (95.75, 72.3), (95.75, 72.9)]),
        ("via", (95.75, 73.6)),   # 離 Hub 北側腳遠一點:XI / PLLFILT(33、34 腳)的電容擺得進來
        ("F.Cu", [(95.75, 74.3), (95.75, 76.5)]),
    ]),
    # USB-C 燒錄口:往北讓開 Hub 上行的過孔,在 U60 南邊往東,經 D70 接 J50 的 B6/B7
    # (A6/A7 在 B6/B7 中間,兩端手性要用 B 那組;A、B 兩組的連接交給 freerouting)
    ("USB2 USB-C", "USBC_DP", "USBC_DN", "90", ("U60",), ("J50.B6", "J50.B7"), [
        ("F.Cu", [(103.0, 75.25), (102.8, 75.25), (102.2, 74.65), (100.6, 74.65), (100.6, 80.3),
                  (121.0, 80.3), (121.0, 105.2)]),
        ("thru", "D70"),
    ]),
    # Hub 下行兩對從 U61 西側出來往南(乙太網路東邊),經 USBLC6(D71 / D72)進 USB-A。兩對兩端手性都相反,
    # USB-A 的資料腳是貼片(只在 F.Cu),不能在接頭前換邊:和 Hub 上行一樣折返一次(兩條各一個過孔、長度不變)。
    # USB-A 0 在 U61 西邊折返往南;USB-A 1 在往東那段的盡頭折返往南。
    ("USB2 USB-A 0", "USBA0_DP", "USBA0_DN", "90", ("U61",), ("J51",), [
        ("F.Cu", [(91.4, 78.25), (88.6, 78.25)]),
        ("via", (87.9, 78.25)),
        ("B.Cu", [(88.6, 78.25), (88.9, 78.25), (88.9, 88.5)]),
        ("via", (88.9, 89.2)),
        ("F.Cu", [(88.9, 89.9), (88.9, 90.0), (88.0, 90.9), (88.0, 91.0)]),
        ("thru", "D71"),
    ]),
    ("USB2 USB-A 1", "USBA1_DP", "USBA1_DN", "90", ("U61",), ("J52",), [
        ("F.Cu", [(91.4, 79.25), (89.3, 79.25), (89.3, 86.0), (105.6, 86.0)]),
        ("via", (106.3, 86.0)),
        ("B.Cu", [(105.6, 86.0), (105.0, 86.0), (105.0, 88.6)]),
        ("via", (105.0, 89.3)),
        ("F.Cu", [(105.0, 90.0), (105.0, 91.0)]),
        ("thru", "D72"),
    ]),
    # CM5 乙太網路(J1 → U30/U31 → J30)。J1 頂排(ETH1、ETH0)往北出、繞過 J1 西端,底排(ETH3、ETH2)
    # 往南出包在裡面,四對在 J1 南邊往西,x ≈ 83–87 往南(H8 南邊、U61 西邊),y ≈ 83–89 往西時在
    # x ≈ 75–81 從 HDMI0 底下穿過(L3 為 +3V3),再往南穿過 ESD 腳下(直通式)進 J30。
    # J30 的 Pair1(4、7 腳)夾著 Pair2(5、6 腳):ETH2 在 U31 後面下到 B.Cu,直接接插件腳。
    # ETH1、ETH2 兩端手性相反,在 J30 那端對內對調(gen/board.py)。換層處過孔對相距 2 mm 的車道才放得下。
    *(("乙太網路 " + n, f"ETH{n}_P", f"ETH{n}_N", "100", ("J1",), ("J30",), [
        ("F.Cu", head + [(xc, ylane), (82.0, ylane)]),
        ("via", (81.3, ylane)),
        ("B.Cu", [(80.6, ylane), (75.7, ylane)]),
        ("via", (75.0, ylane)),
        # 過了 HDMI 車道收回 1.4 mm 間距、整組往南(U41 南側留給它的去耦電容);
        # ESD 上方兩對相距 2 mm(中間放地過孔),到 y 90.6 才併到 ESD 腳的位置
        ("F.Cu", [(74.3, ylane), *([(73.0, ylane), (73.0 - (yw - ylane), yw)] if yw != ylane else []),
                  (xs, yw), (xs, 90.6),
                  (xe, 90.6 + abs(xe - xs)), (xe, 91.7)]),
        ("thru", esd),
        *tail,
    ]) for n, head, xc, ylane, yw, xs, xe, esd, tail in (
        ("0", [(104.5, 62.9), (104.5, 59.4), (99.4, 59.4), (99.4, 68.4), (82.8, 68.4)], 82.8, 83.4, 85.2, 46.2, 46.45, "U30",
         [("F.Cu", [(46.45, 94.3), (46.45, 95.2)])]),
        ("1", [(103.3, 62.9), (103.3, 60.8), (100.8, 60.8), (100.8, 69.8), (84.2, 69.8)], 84.2, 85.4, 86.6, 48.2, 47.95, "U30",
         # 整對往東移 0.31,讓 N 正對 4 腳(48.09)
         [("F.Cu", [(47.95, 94.3), (47.95, 94.5), (48.2625, 94.8125), (48.2625, 95.4)])]),
        ("3", [(103.3, 67.1), (103.3, 71.2), (85.6, 71.2)], 85.6, 87.4, 88.0, 53.8, 54.05, "U31",
         [("F.Cu", [(54.05, 94.3), (54.05, 95.2)])]),
        ("2", [(104.5, 67.1), (104.5, 72.6), (87.0, 72.6)], 87.0, 89.4, 89.4, 55.8, 55.55, "U31",
         [("F.Cu", [(55.55, 94.3), (55.55, 94.7)]), ("via", (55.55, 95.4)),
          ("B.Cu", [(55.55, 96.1), (55.55, 97.0), (50.0, 97.0), (50.0, 98.0)])]),
    )),
    # HDMI0 在 J2 頂排東端往北出,向東繞過 J2(H5 西側)往南,從模組底下往西,到 x ≈ 76–80 往南,
    # 斜切到 J70。x ≈ 71–75 留給 LAN1 那組往南。J2 那端由西到東 D2、D1、D0、CK,
    # J70 那端由東到西 D2…CK:沿行進方向都是 D2 在左,不交叉。
    *(("HDMI0 " + lane, f"HDMI0_{lane}_P", f"HDMI0_{lane}_N", "100", ("J2",), ("J70",), [
        ("F.Cu", [(x0, 28.9), (x0, yn), (xe, yn), (xe, yw), (xd, yw), (xd, yk),
                  (xj, yk + xd - xj), (xj, 106.5)]),
    ]) for lane, x0, yn, xe, yw, xd, yk, xj in (
        ("D2", 116.5, 23.2, 129.2, 52.2, 80.2, 97.6, 73.0),
        ("D1", 117.7, 24.6, 127.8, 50.8, 78.8, 97.4, 71.5),
        ("D0", 118.9, 26.0, 126.4, 49.4, 77.4, 97.2, 70.0),
        ("CK", 120.1, 27.4, 125.0, 48.0, 76.0, 97.0, 68.5),
    )),
)
# 終點焊盤的 P、N 中間夾著別的焊盤(J70 每對中間是地腳):最後一點之後先 45° 分開到焊盤正上方再直下
FAN = {"HDMI0 D2", "HDMI0 D1", "HDMI0 D0", "HDMI0 CK",
       "乙太網路 0", "乙太網路 1", "乙太網路 2", "乙太網路 3"}

# 差分網上刻意不接、留給 freerouting 的焊盤(USB-C 另一面那組資料腳)
LOOSE = {"J50.A6", "J50.A7"}
# 補長凸起的高度與兩端留白另外指定(B.Cu 段旁邊沒有別的線)
BUMP = {"USB2 Hub 上行": (0.6, 0.5)}

# 差分線旁邊的其他手佈件:(網, 層, 線寬, [點…]) 與過孔 (網, x, y)
EXTRA_TRACKS = (
    # U40 的 30 腳(LAN0_1V2)夾在 RX、TX 兩對之間,25 腳在 D 對南邊:各拉一小段打過孔,
    # 其餘(到去耦電容)交給 freerouting
    ("LAN0_1V2", "F.Cu", 0.2, [(49.6, 62.25), (51.1, 62.25)]),
    ("LAN0_1V2", "F.Cu", 0.2, [(49.6, 64.75), (50.4, 64.75), (50.4, 65.6)]),
    ("LAN1_1V2", "F.Cu", 0.2, [(49.6, 78.25), (51.1, 78.25)]),           # U41 同上(往南 16 mm)
    ("LAN1_1V2", "F.Cu", 0.2, [(49.6, 80.75), (50.4, 80.75), (50.4, 81.6)]),
    # M.2 地腳(51、45、39)→ 旁邊的地過孔
    ("GND", "F.Cu", 0.25, [(4.3, 11.75), (5.725, 11.75)]),
    ("GND", "F.Cu", 0.25, [(4.3, 13.25), (5.725, 13.25)]),
    ("GND", "F.Cu", 0.25, [(4.45, 14.75), (5.725, 14.75)]),
    # J70 夾在各對 P、N 之間的地腳(2、5、8、11)從南端拉出來打過孔
    *(("GND", "F.Cu", 0.25, [(x, 109.8), (x, 110.7)]) for x in (73.0, 71.5, 70.0, 68.5)),
    # U30/U31 的地腳(3、8)夾在兩對中間:連起來,往北拉到兩對間距 2 mm 處打地過孔
    *(("GND", "F.Cu", 0.2, [(x, 90.0), (x, 93.385)]) for x in (47.2, 54.8)),
    # USBLC6 的 GND(2 腳)、VBUS(5 腳)夾在兩條線中間:往兩條線分開處拉出來打過孔
    # (D71 / D72 轉 90°:VBUS 在北、GND 在南;D70 轉 270°:GND 在北、VBUS 在南)
    *(("GND", "F.Cu", 0.25, [(x, y0), (x, y1)]) for x, y0, y1 in ((88.0, 95.64, 96.95), (105.0, 95.64, 96.95),
                                                                  (121.0, 106.1, 107.26))),
    *((net, "F.Cu", 0.25, [(x, y0), (x, y1)]) for net, x, y0, y1 in (
        ("USBA0_VBUS", 88.0, 92.1, 93.36), ("USBA1_VBUS", 105.0, 92.1, 93.36),
        ("USBC_VBUS", 121.0, 109.54, 110.6))),
)
EXTRA_VIAS = (
    ("LAN0_1V2", 51.1, 62.25), ("LAN0_1V2", 50.4, 65.6),
    ("LAN1_1V2", 51.1, 78.25), ("LAN1_1V2", 50.4, 81.6),
    # M.2 奇數排的地腳夾在 PCIe 各對之間,外側被走線圍住:就地打到 In1
    ("GND", 4.3, 11.75), ("GND", 4.3, 13.25), ("GND", 4.45, 14.75),
    *(("GND", x, 110.7) for x in (73.0, 71.5, 70.0, 68.5)),
    *(("GND", x, 90.0) for x in (47.2, 54.8)),
    ("GND", 88.0, 96.95), ("GND", 105.0, 96.95), ("GND", 121.0, 106.1),
    ("USBA0_VBUS", 88.0, 92.1), ("USBA1_VBUS", 105.0, 92.1), ("USBC_VBUS", 121.0, 110.6),
)


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def chamfer(pts, c: float = CHAMFER) -> list:
    """直角轉角切成 45°(切的長度不超過相鄰兩段各一半);其他角度不動。"""
    out = [pts[0]]
    for a, v, b in zip(pts, pts[1:], pts[2:]):
        d1, d2 = _unit(a, v), _unit(v, b)
        if abs(d1[0] * d2[0] + d1[1] * d2[1]) > 1e-9:
            out.append(v)
            continue
        k = min(c, math.dist(a, v) / 2, math.dist(v, b) / 2)
        out += [(v[0] - d1[0] * k, v[1] - d1[1] * k), (v[0] + d2[0] * k, v[1] + d2[1] * k)]
    return out + [pts[-1]]


def offset(pts, h: float) -> list:
    """往行進方向左側偏移 h(畫面座標 y 朝下:往東走時左側是北);轉角用斜接。"""
    out = []
    for i, v in enumerate(pts):
        ns = []
        if i > 0:
            d = _unit(pts[i - 1], v)
            ns.append((d[1], -d[0]))
        if i < len(pts) - 1:
            d = _unit(v, pts[i + 1])
            ns.append((d[1], -d[0]))
        if len(ns) == 1:
            n, s = ns[0], 1.0
        else:
            n = (ns[0][0] + ns[1][0], ns[0][1] + ns[1][1])
            s = 1 / (1 + ns[0][0] * ns[1][0] + ns[0][1] * ns[1][1])
        out.append((v[0] + h * n[0] * s, v[1] + h * n[1] * s))
    return out


def _knee(a, pad, d):
    """從 a 沿 d 斜 45° 走到焊盤正上方(之後沿 d 直進焊盤)。"""
    n = (d[1], -d[0])
    lat = (pad[0] - a[0]) * n[0] + (pad[1] - a[1]) * n[1]
    return (a[0] + d[0] * abs(lat) + n[0] * lat, a[1] + d[1] * abs(lat) + n[1] * lat)


def _knee_out(pad, b, d):
    """_knee 反過來:從焊盤沿 d 直走,再 45° 斜到 b。"""
    along = (b[0] - pad[0]) * d[0] + (b[1] - pad[1]) * d[1]
    lat = math.dist(b, (pad[0] + d[0] * along, pad[1] + d[1] * along))
    return (pad[0] + d[0] * (along - lat), pad[1] + d[1] * (along - lat))


def _length(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _closer(p, n, a, b) -> bool:
    """端子 p、n 對到 a、b(而不是 b、a)比較近。"""
    return math.dist(p, a) + math.dist(n, b) <= math.dist(p, b) + math.dist(n, a)


def route(pair, start: dict, end: dict, pads=None):
    """start / end:{"P": (x, y), "N": (x, y)}(焊盤中心)。pads(位號, 網) → 該零件上這條網的焊盤中心
    (路徑裡有 ("thru", 位號) 時用:直通式零件,線從進來那側的焊盤穿過腳下到另一側)。
    回傳 (走線 [(網, 層, 線寬, [點…])], 過孔 [(網, x, y)], 長度 {"P", "N"}, 問題 [str])。"""
    name, pnet, nnet, cls, _, _, path = pair
    w, gap = CLASSES[cls]
    h = (w + gap) / 2
    tracks, vias, problems = [], [], []
    length = {"P": 0.0, "N": 0.0}
    via_len = {"P": 0.0, "N": 0.0}   # 只算扭轉多出來的過孔(換層時 P、N 各兩個,互相抵掉)
    term = start
    after_thru = False
    for k, item in enumerate(path):
        if item[0] in ("via", "twist", "thru", "tail"):
            continue
        layer, pts = item
        pts = chamfer(pts)
        left, right = offset(pts, h), offset(pts, -h)
        sp, sn = (left, right) if _closer(term["P"], term["N"], left[0], right[0]) else (right, left)
        if k + 1 < len(path) and path[k + 1][0] == "twist":
            d = _unit(pts[-2], pts[-1])
            p_left = sp is left
            tw_tracks, tw_vias, after = twist(pts[-1], d, h, w)
            # twist() 的 "L" 是進來時在左側那條
            role = {"P": "L" if p_left else "R", "N": "R" if p_left else "L"}
            for key, net, side in (("P", pnet, sp), ("N", nnet, sn)):
                line = [term[key]] + side
                tracks.append((net, layer, w, line))
                length[key] += _length(line)
                for lay, pl in tw_tracks[role[key]]:
                    tracks.append((net, lay, w, pl))
                    length[key] += _length(pl)
                vias += [(net, *v) for v in tw_vias[role[key]]]
                via_len[key] += VIA_LEN * len(tw_vias[role[key]])
            term = {key: after[role[key]] for key in ("P", "N")}
            continue
        if k + 1 < len(path) and path[k + 1][0] == "thru":
            ref = path[k + 1][1]
            near = {key: min(pads(ref, net), key=lambda q: math.dist(q, side[-1]))
                    for key, net, side in (("P", pnet, sp), ("N", nnet, sn))}
            if not _closer(near["P"], near["N"], sp[-1], sn[-1]):
                problems.append(f"{name}:{ref} 進來那側的 P/N 在行進方向的另一側")
            far = {key: max(pads(ref, net), key=lambda q: math.dist(q, near[key]))
                   for key, net in (("P", pnet), ("N", nnet))}
            d = _unit(pts[-2], pts[-1])
            for key, net, side in (("P", pnet, sp), ("N", nnet, sn)):
                line = [term[key]] + side + [_knee(side[-1], near[key], d), near[key], far[key]]
                tracks.append((net, layer, w, line))
                length[key] += _length(line)
            term = far
            after_thru = True
            continue
        if k + 1 < len(path):
            cx, cy = path[k + 1][1]
            d = _unit(pts[-2], pts[-1])
            u = (d[1] * VIA_PITCH / 2, -d[0] * VIA_PITCH / 2)  # 過孔對垂直於行進方向
            a, b = (cx + u[0], cy + u[1]), (cx - u[0], cy - u[1])
            nxt = {"P": a, "N": b} if _closer(sp[-1], sn[-1], a, b) else {"P": b, "N": a}
            vias += [(pnet, *nxt["P"]), (nnet, *nxt["N"])]
        else:
            nxt = end
            if not _closer(end["P"], end["N"], sp[-1], sn[-1]):
                problems.append(f"{name}:終點的 P/N 在行進方向的另一側(兩端手性相反,要扭轉)")
        for key, net, side in (("P", pnet, sp), ("N", nnet, sn)):
            knee = [_knee(side[-1], nxt[key], _unit(pts[-2], pts[-1]))] if nxt is end and name in FAN else []
            # 剛穿過直通式零件:先沿行進方向直出焊盤,再 45° 併到這段的位置
            out = [_knee_out(term[key], side[0], _unit(pts[0], pts[1]))] if after_thru else []
            line = [term[key]] + out + side + knee + [nxt[key]]
            tracks.append((net, layer, w, line))
            length[key] += _length(line)
        term = nxt
        after_thru = False
    if path[-1][0] == "thru":       # 最後穿過直通式零件:從另一側的焊盤直接接終點
        if not _closer(end["P"], end["N"], term["P"], term["N"]):
            problems.append(f"{name}:終點的 P/N 在行進方向的另一側(兩端手性相反,要扭轉)")
        for key, net in (("P", pnet), ("N", nnet)):
            tracks.append((net, "F.Cu", w, [term[key], end[key]]))
            length[key] += math.dist(term[key], end[key])
    elif path[-1][0] == "tail":     # 兩條各自指定的尾段(要在接頭前換邊時)
        for key, net in (("P", pnet), ("N", nnet)):
            cur, layer = term[key], "F.Cu"
            for it in path[-1][1][key]:
                if it[0] == "via":
                    vias.append((net, *it[1]))
                    via_len[key] += VIA_LEN
                    continue
                layer, line = it[0], [cur] + list(it[1])
                tracks.append((net, layer, w, line))
                length[key] += _length(line)
                cur = line[-1]
            if math.dist(cur, end[key]) > 1e-6:
                tracks.append((net, layer, w, [cur, end[key]]))
                length[key] += math.dist(cur, end[key])
    length = {k: length[k] + via_len[k] for k in length}
    skew = abs(length["P"] - length["N"])
    if skew > SKEW_MAX:
        short = pnet if length["P"] < length["N"] else nnet
        if _compensate(tracks, short, pnet if short == nnet else nnet, skew, *BUMP.get(name, (BUMP_MAX, 1.0))):
            length = {k: sum(_length(t[3]) for t in tracks if t[0] == net) + via_len[k]
                      for k, net in (("P", pnet), ("N", nnet))}
            skew = abs(length["P"] - length["N"])
        if skew > SKEW_MAX:
            problems.append(f"{name}:對內長度差 {skew:.3f} mm > {SKEW_MAX} mm")
    return tracks, vias, length, problems


def twist(a, d, h: float, w: float):
    """從中心線點 a 沿 d 扭轉一次(P、N 換邊),給只能這樣修手性的介面(USB2)。

    右側那條先 45° 外移到過孔、在 B.Cu 斜穿到另一側再上來;左側那條留在 F.Cu,在中間 45° 換到右側。
    過孔離中心線 TWIST_VIA,左側那條離它們 ≥ 0.5 mm。回傳 ({"L"/"R": [(層, [點…])]},
    {"L"/"R": [過孔…]}, {"L"/"R": 扭轉後的端點});"L" 是進來時在左側那條。"""
    n = (d[1], -d[0])
    W = lambda s, t: (a[0] + d[0] * s + n[0] * t, a[1] + d[1] * s + n[1] * t)  # noqa: E731
    v, S = TWIST_VIA, twist_span(h)
    e = v - h
    tracks = {
        "R": [("F.Cu", [W(0, -h), W(e, -v)]), ("B.Cu", [W(e, -v), W(e + 2 * v, v)]),
              ("F.Cu", [W(e + 2 * v, v), W(S, h)])],
        "L": [("F.Cu", [W(0, h), W(S / 2 - h, h), W(S / 2 + h, -h), W(S, -h)])],
    }
    vias = {"R": [W(e, -v), W(e + 2 * v, v)], "L": []}
    return tracks, vias, {"L": W(S, -h), "R": W(S, h)}


BUMP_MAX = 0.25     # 補長凸起的高度上限(對與對之間至少 0.52 mm,凸起後仍 ≥ 0.27)
BUMP_TOP = 0.5       # 凸起頂部長度
BUMP_GAP = 0.6       # 凸起之間


def _dist_to_line(p, line) -> float:
    best = math.inf
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
        best = min(best, math.dist(p, (a[0] + t * dx, a[1] + t * dy)))
    return best


def _compensate(tracks, short: str, other: str, skew: float, bump: float = 0.25, margin: float = 1.0) -> bool:
    """在較短那條線的水平 / 垂直段上加 45° 梯形凸起(朝遠離另一條的方向)補長度。

    每個凸起多出 2a(√2 − 1)(a 為高度,≤ BUMP_MAX)。從最長那段開始放,一段放不下就接著放次長的,
    最後一批的 a 算到剛好補齊。回傳有沒有加。"""
    per = 2 * (math.sqrt(2) - 1)
    pitch = 2 * bump + BUMP_TOP + BUMP_GAP
    rem, done = skew, False
    while rem > 1e-6:
        best = None
        for ti, (net, layer, w, line) in enumerate(tracks):
            if net != short:
                continue
            partner = [p for t in tracks if t[0] == other and t[1] == layer for p in t[3]]
            for si, (p, q) in enumerate(zip(line, line[1:])):
                L = math.dist(p, q)
                axis = abs(p[0] - q[0]) < 1e-9 or abs(p[1] - q[1]) < 1e-9
                if axis and L >= pitch - BUMP_GAP + 2 * margin and partner and (best is None or L > best[0]):
                    best = (L, ti, si, partner)
        if best is None:
            return done
        L, ti, si, partner = best
        n_need = math.ceil(rem / (per * bump))
        n = min(n_need, int((L - 2 * margin + BUMP_GAP) // pitch))  # 兩端各留 margin
        a = rem / (n * per) if n == n_need else bump
        net, layer, w, line = tracks[ti]
        p, q = line[si], line[si + 1]
        d = _unit(p, q)
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        nrm = (d[1], -d[0])
        probe = lambda s: _dist_to_line((mid[0] + s * nrm[0] * 0.5, mid[1] + s * nrm[1] * 0.5), partner)  # noqa: E731
        if probe(1) < probe(-1):
            nrm = (-nrm[0], -nrm[1])
        span = n * (2 * a + BUMP_TOP) + (n - 1) * BUMP_GAP
        s0 = (L - span) / 2
        pts = []
        for i in range(n):
            s = s0 + i * (2 * a + BUMP_TOP + BUMP_GAP)
            for along, out in ((s, 0), (s + a, a), (s + a + BUMP_TOP, a), (s + 2 * a + BUMP_TOP, 0)):
                pts.append((p[0] + d[0] * along + nrm[0] * out, p[1] + d[1] * along + nrm[1] * out))
        tracks[ti] = (net, layer, w, line[:si + 1] + pts + line[si + 1:])
        rem -= n * per * a
        done = True
    return done


def dru() -> str:
    """對內間距比網路類別的 0.2 mm 小:每一對加一條規則(座標取到 nm 會有捨入,下限留 0.01 mm)。
    100 Ω 的線寬 0.145 比網路類別的差分線寬 0.15 窄:再加一條線寬規則。"""
    out = []
    for name, p, n, cls, *_ in PAIRS:
        w, gap = CLASSES[cls]
        out.append(f'(rule "diff pair {name}"\n'
                   f'  (condition "(A.NetName == \'{p}\' && B.NetName == \'{n}\') || '
                   f'(A.NetName == \'{n}\' && B.NetName == \'{p}\')")\n'
                   f'  (constraint clearance (min {gap - 0.01:g}mm)))\n')
        if w < 0.15:
            out.append(f'(rule "diff pair {name} width"\n'
                       f'  (condition "A.NetName == \'{p}\' || A.NetName == \'{n}\'")\n'
                       f'  (constraint track_width (min {w:g}mm)))\n')
    return "".join(out)


def keepouts() -> list:
    """自動擺件的禁區:F.Cu 上每段中心線(含兩側)的外接框、每個過孔周圍。"""
    out = []
    vias = [(x, y) for _, x, y in EXTRA_VIAS]
    for name, pnet, nnet, cls, _, _, path in PAIRS:
        w, gap = CLASSES[cls]
        r = gap / 2 + w + KEEP
        for k, item in enumerate(path):
            if item[0] == "via":
                vias.append(item[1])
            elif item[0] == "F.Cu":
                for (xa, ya), (xb, yb) in zip(item[1], item[1][1:]):
                    out.append((min(xa, xb) - r, min(ya, yb) - r, max(xa, xb) + r, max(ya, yb) + r))
            elif item[0] == "tail":
                for its in item[1].values():
                    for it in its:
                        if it[0] == "via":
                            vias.append(it[1])
                        elif it[0] == "F.Cu":
                            for (xa, ya), (xb, yb) in zip(it[1], it[1][1:]):
                                out.append((min(xa, xb) - r, min(ya, yb) - r, max(xa, xb) + r, max(ya, yb) + r))
            elif item[0] == "twist":
                a, b = path[k - 1][1][-1], path[k + 1][1][0]
                rt = TWIST_VIA + 0.3 + KEEP
                out.append((min(a[0], b[0]) - rt, min(a[1], b[1]) - rt, max(a[0], b[0]) + rt, max(a[1], b[1]) + rt))
    for _, layer, w, pts in EXTRA_TRACKS:
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            r = w / 2 + KEEP
            out.append((min(xa, xb) - r, min(ya, yb) - r, max(xa, xb) + r, max(ya, yb) + r))
    r = VIA_PITCH / 2 + 0.3 + KEEP
    out += [(x - r, y - r, x + r, y + r) for x, y in vias]
    return out
