"""USB-C 5V 输入 → 3.3V LDO + 电源指示 LED。

与 EasyEDA 那块板子同一个电路,用来做两套工具的对照。

坐标一律取 1.27mm 连接格点的整数倍(KiCad 的连接格),否则 ERC 会报
endpoint_off_grid —— 引脚落在格点外时连线看着对、实际接不上。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))  # boards/usbc-ldo/gen/board.py -> repo/lib
from schgen import Part, Schematic  # noqa: E402

G = 1.27


def g(n: float) -> float:
    """把格数换算成 mm,避免散落的魔术数字。"""
    return round(n * G, 4)


s = Schematic(title="USB-C 5V to 3V3 LDO (KiCad build)")


def power(name: str, x: float, y: float, rot: float = 0.0) -> Part:
    """power:XXX 符号。引脚在原点,所以 x/y 就是接点。"""
    p = Part(f"#PWR{len(s.parts):02d}", "power", name, x, y, value=name,
             rotation=rot, fields_hidden=True)
    return s.add(p)


def flag(x: float, y: float, rot: float = 0.0) -> Part:
    """PWR_FLAG:告诉 ERC「这个网有电源驱动」。

    +5V 来自二极管、+3V3 来自 LDO 的 power_out —— 前者在 ERC 眼里是 passive,
    不加 flag 会被判成「电源引脚未被驱动」。这不是糊弄检查:标记的是
    「电源确实从这里进来」这个事实。
    """
    return s.add(Part(f"#FLG{len(s.parts):02d}", "power", "PWR_FLAG", x, y,
                      value="PWR_FLAG", rotation=rot, fields_hidden=True))


# ── 器件 ────────────────────────────────────────────────────────────────
J1 = s.add(Part("J1", "Connector", "USB_C_Receptacle_USB2.0_16P", g(30), g(85),
                value="USB-C", footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"))

# 真板子用的是 SS34;KiCad 内建库没有 SS34,用同系列的 SS32 符号代替
# (脚位与封装相同,差别在反向耐压 20V vs 30V)。Value 仍写 SS34 以对上 BOM。
D1 = s.add(Part("D1", "Diode", "SS32", g(62), g(65), value="SS34", rotation=180,
                footprint="Diode_SMD:D_SMA"))
R1 = s.add(Part("R1", "Device", "R", g(44), g(95), value="5.1k",
                footprint="Resistor_SMD:R_0402_1005Metric"))
R2 = s.add(Part("R2", "Device", "R", g(48), g(95), value="5.1k",
                footprint="Resistor_SMD:R_0402_1005Metric"))
D2 = s.add(Part("D2", "Power_Protection", "USBLC6-2P6", g(62), g(104), value="USBLC6-2P6",
                footprint="Package_TO_SOT_SMD:SOT-23-6"))
D3 = s.add(Part("D3", "Diode", "SMAJ5.0A", g(78), g(72), value="SMAJ5.0A",
                footprint="Diode_SMD:D_SMA"))
# C2/C3 由 10µF/22µF 降到 4.7µF:USB 2.0 規定插入時注入電荷 ≤50µC,
# 舊值模擬是 124µC(見 sim/power_sim.py,v3 為 39µC)。
C2 = s.add(Part("C2", "Device", "C", g(88), g(72), value="4.7uF",
                footprint="Capacitor_SMD:C_0805_2012Metric"))
# 穩壓器由 AMS1117-3.3 換成 TI LP38693MP-3.3(SOT-223-5):
#   - AMS1117 壓差約 1.1V,USB 端電壓偏低(4.4V)時掉出穩壓;LP38693 約 0.33V @0.5A
#   - 不選 AP2112K:它輸入絕對最大 6.5V,熱插拔過衝模擬到 6.77V;LP38693 是 12V
#   - 輸入/輸出各 ≥1µF 陶瓷電容即穩定
U1 = s.add(Part("U1", "Regulator_Linear", "LP38693MP-3.3", g(108), g(65), value="LP38693MP-3.3",
                footprint="Package_TO_SOT_SMD:SOT-223-5"))
C1 = s.add(Part("C1", "Device", "C", g(94), g(72), value="100nF",
                footprint="Capacitor_SMD:C_0402_1005Metric"))
C3 = s.add(Part("C3", "Device", "C", g(128), g(72), value="4.7uF",
                footprint="Capacitor_SMD:C_0805_2012Metric"))
R3 = s.add(Part("R3", "Device", "R", g(140), g(72), value="1k",
                footprint="Resistor_SMD:R_0402_1005Metric"))
# Device:LED 的 1 脚是阴极 K、2 脚是阳极 A。转 180° 让阳极朝左接 R3、阴极朝右接地;
# 第一版把 R3 接到了 1 脚(阴极),LED 反接永远不亮,而 ERC 对此一声不吭
# —— 是做 PCB 时读网表才发现的。
# 料号与 EasyEDA 那块板子的 BOM 一致:KENTO KT-0805Y(黄光 AlGaInP,0805)。
LED1 = s.add(Part("LED1", "Device", "LED", g(140), g(84), value="KT-0805Y", rotation=180,
                  footprint="LED_SMD:LED_0805_2012Metric"))

# ── VBUS → D1 → +5V ────────────────────────────────────────────────────
# USB-C 的 A4/A9/B4/B9 共用同一坐标(冗余引脚),一条线全接上。
vbus_x, vbus_y = J1.pin_xy("A4")
# 从下方绕上来接阳极,不能让线横穿阴极 —— 那会把二极管两脚短接,
# 而 ERC 对两个 passive 引脚被连在一起一声不吭(实测踩过)。
anode = D1.pin_xy("2")
s.wire((vbus_x, vbus_y), (g(54), vbus_y))
s.wire((g(54), vbus_y), (g(54), anode[1]))
s.wire((g(54), anode[1]), anode)
s.wire(D1.pin_xy("1"), (g(70), g(65)))
p5 = power("+5V", g(70), g(61))
s.wire((g(70), g(65)), (g(70), g(61)))
flag(g(74), g(61))
rail5 = [g(70), g(74)]        # +5V 干线的分接点,最后统一画

# ── +5V 上的 TVS 与输入电容 ────────────────────────────────────────────
for part, pin_hi, pin_lo in ((D3, "2", "1"), (C2, "1", "2")):
    hi = part.pin_xy(pin_hi)
    s.wire(hi, (hi[0], g(61)))
    rail5.append(hi[0])
    lo = part.pin_xy(pin_lo)
    s.wire(lo, (lo[0], g(84)))

# ── CC 下拉 ────────────────────────────────────────────────────────────
for r, cc in ((R1, "A5"), (R2, "B5")):
    cx, cy = J1.pin_xy(cc)
    top = r.pin_xy("1")
    s.wire((cx, cy), (top[0], cy))
    s.wire((top[0], cy), top)
    bot = r.pin_xy("2")
    s.wire(bot, (bot[0], g(110)))          # R1/R2 已挪开,竖线不再扫过 D2 的引脚

# ── D+/D- 走 ESD ───────────────────────────────────────────────────────
# USB-C 正反插:A 面与 B 面的 D+/D- 必须并接,否则插反就没有数据。
for pin_a, pin_b in (("A6", "B6"), ("A7", "B7")):
    ax, ay = J1.pin_xy(pin_a)
    bx, by = J1.pin_xy(pin_b)
    s.wire((ax, ay), (g(52), ay))
    s.wire((bx, by), (g(52), by))
    s.wire((g(52), ay), (g(52), by))

# D+ 与 D- 必须各走一条车道 —— 共线重叠会被 KiCad 并成同一个网,
# 而这既不横穿引脚(守卫看不见)也不违反 ERC,只有网表能发现。
for pin_j, pin_d, lane in (("A6", "1", g(54)), ("A7", "3", g(56))):
    jx, jy = J1.pin_xy(pin_j)
    dx, dy = D2.pin_xy(pin_d)
    s.wire((g(52), jy), (lane, jy))
    s.wire((lane, jy), (lane, dy))
    s.wire((lane, dy), (dx, dy))

# SBU 本设计不用;USBLC6 的 4/6 脚与 1/3 脚在芯片内部同节点,外部不再接。
# 显式标 NC —— 否则「没接」与「漏接」在 ERC 报告里长得一样。
for pin in ("A8", "B8"):
    s.no_connect(J1, pin)
for pin in ("4", "6"):
    s.no_connect(D2, pin)

# ESD 器件自己的供电与地
d2v = D2.pin_xy("5")
s.wire(d2v, (d2v[0], g(98)))
s.wire((d2v[0], g(98)), (g(72), g(98)))
s.wire((g(72), g(98)), (g(72), g(61)))   # 自己一条上引线,不与 +5V 干线左端同列
rail5.append(g(72))

# ── U1:+5V 进、+3V3 出 ────────────────────────────────────────────────
vi = U1.pin_xy("4")                    # LP38693:4 = IN
s.wire(vi, (vi[0] - g(4), vi[1]))
s.wire((vi[0] - g(4), vi[1]), (vi[0] - g(4), g(61)))
rail5.append(vi[0] - g(4))
# EN 接 IN:有電就輸出。規格書:EN 從 IN 一起上電(起點 <0.4V)時折返限流才有效。
en = U1.pin_xy("1")
s.wire(en, (vi[0] - g(4), en[1]))
s.wire((vi[0] - g(4), en[1]), (vi[0] - g(4), vi[1]))
s.no_connect(U1, "2")                  # 2 = NC(晶片內部未連接)

vo = U1.pin_xy("3")                    # 3 = OUT
s.wire(vo, (g(122), vo[1]))
p33 = power("+3V3", g(122), g(61))
s.wire((g(122), vo[1]), (g(122), g(61)))
rail33 = [g(122)]
# +3V3 不加 PWR_FLAG:U1 的 VO 已经是 power_out,再加一个会变成两个电源输出打架。

# ── 输出电容 / LED 支路 ────────────────────────────────────────────────
for part, pin_hi, pin_lo in ((C1, "1", "2"), (C3, "1", "2"), (R3, "1", "2")):
    hi = part.pin_xy(pin_hi)
    s.wire(hi, (hi[0], g(61)))
    (rail5 if part is C1 else rail33).append(hi[0])
    lo = part.pin_xy(pin_lo)
    if part is R3:
        s.wire(lo, LED1.pin_xy("2"))    # R3 下接 LED 阳极(2 脚 = A)
    else:
        s.wire(lo, (lo[0], g(84)))

s.rail(g(61), rail5)      # +5V
s.rail(g(61), rail33)     # +3V3(两段在 y 相同但 x 区间不相交,互不影响)

# ── GND 汇总 ───────────────────────────────────────────────────────────
gnd_y = g(84)
gnd_xs = [D3.pin_xy("1")[0], C2.pin_xy("2")[0], C1.pin_xy("2")[0], C3.pin_xy("2")[0],
          U1.pin_xy("5")[0]]
u_gnd = U1.pin_xy("5")                 # 5 = GND
s.wire(u_gnd, (u_gnd[0], gnd_y))
lo, hi = min(gnd_xs), max(gnd_xs)
s.wire((lo, gnd_y), (hi, gnd_y))
gsym = power("GND", g(98), g(88))
s.wire((g(98), gnd_y), (g(98), g(88)))
# GND 上也要一个 PWR_FLAG:这条网只接到 passive 引脚,ERC 否则判「电源未被驱动」。
flag(g(94), g(88), rot=180)
s.wire((g(94), g(88)), (g(98), g(88)))

# LED 阴极 → GND
lk = LED1.pin_xy("1")                 # 1 脚 = K
s.wire(lk, (lk[0], g(92)))
s.wire((lk[0], g(92)), (g(98), g(92)))
s.wire((g(98), g(88)), (g(98), g(92)))

# USB 侧的 GND:连接器外壳 / GND 引脚 + CC 电阻下端 + ESD 的 GND
sh_x = J1.pin_xy("SH")[0]
jg = J1.pin_xy("A1")
s.wire(jg, (jg[0], g(110)))
s.wire((min(jg[0], sh_x), g(110)), (g(98), g(110)))   # 幹線要涵蓋屏蔽壳那一列
s.wire((g(98), g(92)), (g(98), g(110)))
dg = D2.pin_xy("2")
s.wire(dg, (dg[0], g(110)))
# 屏蔽壳接地 —— 不接的话 ERC 会把它算成漏接,而它确实该接。
sh = J1.pin_xy("SH")
s.wire(sh, (sh[0], g(110)))

# ── 写出前自检 ─────────────────────────────────────────────────────────
# 导线横穿引脚会静默造成短路,ERC 不报。宁可在这里失败,也不要把一张
# 「检查全过、网表是错的」图交出去。
# GND 干线扫过 ESD 的 GND 脚、电源旗标挂在电源干线上 —— 这两处是刻意的分接,
# 逐个列名豁免(不整类豁免:豁免的理由是「确认这一脚就该在这条网上」)。
bad = s.crossing_pins(allow={"D2.2", "#FLG13.1", "#FLG15.1"}) + s.overlapping_wires()
if bad:
    print(f"!! 导线横穿了 {len(bad)} 个引脚,拒绝写出:")
    for b in bad:
        print("   ", b)
    raise SystemExit(1)

# ── 输出 ───────────────────────────────────────────────────────────────
out = Path(__file__).resolve().parent.parent / "usbc-ldo.kicad_sch"
out.write_text(s.render(), encoding="utf-8", newline="\n")
print(f"wrote {out.name}: {len(s.parts)} parts, {len(s.wires)} wires")
