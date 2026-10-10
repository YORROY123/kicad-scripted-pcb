"""電路圖設計審查:檢查「設計意圖本身對不對」,不是「有沒有照意圖畫」。

    python lib/review.py <板目錄>          (只用標準函式庫;讀 net.txt 與 lcsc-check.json)

ERC 只看腳位類型、網表比對只看有沒有照 board.py 畫。兩者都假設 board.py 是對的。
這裡用規格書的規則反過來審 board.py:

  diode-short     二極體陽極接電源、陰極接地(順偏跨在電源上 = 短路);TVS / 齊納反接
  diode-polarity  單向 TVS 的腳位名稱看不出哪腳是陰極,又不在本檔的對照表裡
  symbol-value    具體型號的符號(Diode:SS32)配了不同的值(SS34)
  decoupling      IC 電源腳的去耦電容(各型號的最小值來自規格書)
  rail-range      電源腳所在網的電壓範圍超出規格(電壓由穩壓器 / 接頭 / 二極體推算)
  input-float     輸入腳沒有任何東西驅動或上下拉
  led-current     LED 電流:(電源 − Vf − 低側壓降) / R,Vf 取 lcsc-check.json 的 JLC 規格
  usb-c-sink      CC1 / CC2 各自一顆 5.1k 下拉、A/B 兩面的 D+ / D− 併在一起
  usb-esd         USBLC6 的 VBUS 腳接到 USB 的 VBUS
  esp32c3-*       EN 的 RC、GPIO2/8/9 開機腳、GPIO18/19 = D−/D+
  inductive       繼電器線圈要有續流路徑(ULN2803 的 COM 接線圈電源,或反向二極體);吸合電壓
  cap-voltage     電容耐壓(lcsc-check.json 的 Voltage Rating)與電解電容極性

有些結論是已知、刻意的取捨:寫在 <板目錄>/review-waivers.json({"規則|位號": "理由"}),
該項降為 INFO 並印出理由。有 ERROR(沒被豁免)就回傳 1。

電壓與元件參數都是「規格書範圍」,不是量測;結論是保守估計,實物要量。
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lcsc import si_value  # noqa: E402

# ── 元件知識(每一筆都要寫出處)───────────────────────────────────────────
# 電壓源:lib_id → {腳位名稱: (最低, 標稱, 最高) V}
SOURCES = {
    # TI LP38693 規格書 SNVS321:輸出精度 ±2%(全溫度)
    "Regulator_Linear:LP38693MP-3.3": {"OUT": (3.234, 3.3, 3.366)},
    # Hi-Link HLK-10M05 規格書:5V ±0.2V
    "Converter_ACDC:HLK-10M05": {"+Vout": (4.8, 5.0, 5.2), "-Vout": (0.0, 0.0, 0.0)},
    # USB 2.0 §7.2.1:VBUS 在設備端 4.40–5.25V(低功率裝置下限)
    "Connector:USB_C_Receptacle_USB2.0_16P": {"VBUS": (4.40, 5.0, 5.25), "GND": (0.0, 0.0, 0.0)},
}
# 電源腳的容許範圍與去耦需求:lib_id → {腳位名稱: (最低 V, 最高 V, 最小總電容 F, 出處)}
SUPPLY_PINS = {
    "RF_Module:ESP32-C3-WROOM-02": {
        "3V3": (3.0, 3.6, 10e-6, "ESP32-C3-WROOM-02 規格書 §5.3 / 參考電路:3.0–3.6V,10µF + 0.1µF"),
    },
    "Regulator_Linear:LP38693MP-3.3": {
        "IN": (3.3 + 0.55, 10.0, 1e-6, "LP38693 規格書:VIN ≤ 10V(操作),壓差 550mV@0.5A,CIN ≥ 1µF"),
        "OUT": (None, None, 1e-6, "LP38693 規格書:COUT ≥ 1µF 陶瓷"),
    },
}
# 腳位名稱看不出陰極的二極體:lib_id → 陰極腳號(由符號圖形判讀)
CATHODE_PIN = {
    # Diode.kicad_sym 的 SM6T6V8A(SMAJ5.0A 繼承它):橫桿(陰極)在 x = −1.27,
    # 那一側是 1 號腳(名稱寫 A1,其實是陰極)。D_SMA 封裝 1 號焊盤是色環端。
    "Diode:SMAJ5.0A": "1",
}
SCHOTTKY_VF = (0.3, 0.4, 0.5)          # SS34 規格書:0.5V@3A,小電流約 0.3–0.4V
GPIO_VOH = (3.1, 3.2, 3.3)             # ESP32-C3 在數 mA 時的 VOH(規格書只保證 0.8×VDD@40mA)
OPEN_COLLECTOR_VCE = {                 # 導通時集極對地壓降
    "Transistor_Array:ULN2803A": (0.7, 0.9, 1.1),   # TI ULN2803A:VCE(sat) 0.9–1.1V @100mA
}
INDUCTIVE = {
    # Songle SRD-05VDC-SL-C:線圈 5V / 70Ω,吸合電壓 ≤ 75% 額定
    "Relay:SANYOU_SRD_Form_C": {"coil": ("2", "5"), "rated": 5.0, "pickup": 0.75},
}
SPECIFIC_LIBS = ("Diode", "Regulator_Linear", "Power_Protection", "Transistor_FET", "Transistor_Array")
LED_MIN_MA, LED_MAX_MA = 0.5, 20.0


# ── 網表 ────────────────────────────────────────────────────────────────
def sexpr(text: str):
    tok = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')
    stack: list[list] = [[]]
    for m in tok.finditer(text):
        t = m.group()
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    k = kids(node, name)
    return k[0][1] if k and len(k[0]) > 1 else None


@dataclass
class Pin:
    ref: str
    num: str
    name: str      # 腳位名稱(pinfunction 去掉 _腳號 後綴)
    type: str
    net: str


class Netlist:
    def __init__(self, path: Path):
        root = sexpr(path.read_text(encoding="utf-8"))
        self.comps: dict[str, dict] = {}
        for c in kids(kids(root, "components")[0], "comp"):
            ls = kids(c, "libsource")[0]
            self.comps[kid(c, "ref")] = {"value": kid(c, "value"), "footprint": kid(c, "footprint"),
                                         "lib_id": f"{kid(ls, 'lib')}:{kid(ls, 'part')}"}
        self.desc = {f"{kid(p, 'lib')}:{kid(p, 'part')}": (kid(p, "description") or "")
                     for p in kids(kids(root, "libparts")[0], "libpart")}
        self.pins: dict[str, dict[str, Pin]] = {}
        self.nets: dict[str, list[Pin]] = {}
        for n in kids(kids(root, "nets")[0], "net"):
            name = kid(n, "name")
            for nd in kids(n, "node"):
                ref, num = kid(nd, "ref"), kid(nd, "pin")
                fn = kid(nd, "pinfunction") or ""
                pin = Pin(ref, num, fn[: -len(num) - 1] if fn.endswith("_" + num) else fn, kid(nd, "pintype"), name)
                self.pins.setdefault(ref, {})[num] = pin
                self.nets.setdefault(name, []).append(pin)

    def lib(self, ref):
        return self.comps[ref]["lib_id"]

    def description(self, ref):
        return self.desc.get(self.lib(ref), "")

    def by_name(self, ref, name) -> list[Pin]:
        return [p for p in self.pins.get(ref, {}).values() if p.name == name]

    def two_pin(self, ref, net) -> str | None:
        """兩腳元件一腳在 net 上時,回傳另一腳的網。"""
        ps = list(self.pins.get(ref, {}).values())
        if len(ps) != 2:
            return None
        if ps[0].net == net:
            return ps[1].net
        if ps[1].net == net:
            return ps[0].net
        return None

    def parts_between(self, net_a, net_b, prefix) -> list[str]:
        return sorted({p.ref for p in self.nets.get(net_a, []) if p.ref.startswith(prefix)
                       and self.two_pin(p.ref, net_a) == net_b and len(self.pins[p.ref]) == 2},
                      key=natural)


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def fmt_v(v):
    return f"{v[0]:.2f}–{v[2]:.2f}V" if v[0] != v[2] else f"{v[0]:.2f}V"


def range_attr(s: str | None):
    """'2.5V~3.6V' → (2.5, 3.05, 3.6);'1.7V' → (1.7, 1.7, 1.7)。"""
    if not s:
        return None
    xs = [float(x) for x in re.findall(r"[\d.]+", s.split("@")[0])]
    if not xs:
        return None
    lo, hi = min(xs), max(xs)
    return (lo, (lo + hi) / 2, hi)


# ── 審查 ────────────────────────────────────────────────────────────────
class Review:
    def __init__(self, nl: Netlist, parts: dict, waivers: dict):
        self.nl, self.parts, self.waivers = nl, parts, waivers
        self.findings: list[tuple[str, str, str, str]] = []   # (等級, 規則, 位號, 訊息)
        self.v: dict[str, tuple] = {}

    def add(self, level, rule, ref, msg):
        w = self.waivers.get(f"{rule}|{ref}")
        if w:
            level, msg = "INFO", f"{msg}  [豁免:{w}]"
        self.findings.append((level, rule, ref, msg))

    def attrs(self, ref) -> dict:
        c = self.nl.comps[ref]
        return self.parts.get(f"{c['value']}|{c['footprint']}", {}).get("attrs") or {}

    def value(self, ref) -> float | None:
        return si_value(self.nl.comps[ref]["value"])

    # 電壓推算 ───────────────────────────────────────────────────────────
    def voltages(self):
        nl = self.nl
        v: dict[str, list] = {}

        def put(net, r):
            v.setdefault(net, []).append(r)

        if "GND" in nl.nets:
            put("GND", (0.0, 0.0, 0.0))
        for ref, c in nl.comps.items():
            for name, r in SOURCES.get(c["lib_id"], {}).items():
                for p in nl.by_name(ref, name):
                    put(p.net, r)
        for _ in range(8):   # 經過二極體 / P-MOS 傳遞,直到不再變
            cur = {n: merge(rs) for n, rs in v.items()}
            changed = False
            for ref in nl.comps:
                desc = nl.description(ref).lower()
                k, a = self.cathode(ref), self.anode(ref)
                if k and a and ("schottky" in desc or "rectifier" in desc) and a.net in cur:
                    va = cur[a.net]
                    r = (va[0] - SCHOTTKY_VF[2], va[1] - SCHOTTKY_VF[1], va[2] - SCHOTTKY_VF[0])
                    if r not in v.get(k.net, []):
                        put(k.net, r)
                        changed = True
                s, d = nl.by_name(ref, "S"), nl.by_name(ref, "D")
                if s and d and "p-channel" in desc and s[0].net in cur and cur[s[0].net] not in v.get(d[0].net, []):
                    put(d[0].net, cur[s[0].net])
                    changed = True
            if not changed:
                break
        self.v = {n: merge(rs) for n, rs in v.items()}

    def cathode(self, ref) -> Pin | None:
        k = self.nl.by_name(ref, "K")
        if k:
            return k[0]
        num = CATHODE_PIN.get(self.nl.lib(ref))
        return self.nl.pins[ref].get(num) if num else None

    def anode(self, ref) -> Pin | None:
        a = self.nl.by_name(ref, "A")
        if a:
            return a[0]
        k = self.cathode(ref)
        if k and len(self.nl.pins[ref]) == 2:
            return next(p for p in self.nl.pins[ref].values() if p is not k)
        return None

    # 規則 ───────────────────────────────────────────────────────────────
    def run(self):
        self.voltages()
        for f in (self.diodes, self.symbol_value, self.supplies, self.inputs, self.leds, self.usb_c,
                  self.usb_esd, self.esp32c3, self.inductive, self.caps):
            f()

    def diodes(self):
        nl = self.nl
        for ref, c in nl.comps.items():
            if not ref.startswith("D") or len(nl.pins[ref]) != 2:
                continue
            desc = nl.description(ref).lower()
            k, a = self.cathode(ref), self.anode(ref)
            if not k:
                if "unidirectional" in desc:
                    self.add("ERROR", "diode-polarity", ref,
                             f"{c['lib_id']} 是單向元件,但腳位名稱看不出哪腳是陰極;查符號圖形後加進 review.py 的 CATHODE_PIN")
                continue
            if self.is_led(ref):
                continue
            va, vk = self.v.get(a.net), self.v.get(k.net)
            if va and vk and va[1] > vk[1] + 0.2:
                clamp = any(w in desc for w in ("tvs", "transil", "zener", "suppressor"))
                if clamp or vk[1] == 0.0:
                    self.add("ERROR", "diode-short", ref,
                             f"陽極接 {a.net}({fmt_v(va)})、陰極接 {k.net}({fmt_v(vk)}):二極體順偏跨在電源上 = 短路"
                             + ("。單向 TVS 應該陰極接電源、陽極接地" if clamp else ""))

    def symbol_value(self):
        for ref, c in self.nl.comps.items():
            lib, part = c["lib_id"].split(":", 1)
            if lib in SPECIFIC_LIBS and part.upper() not in c["value"].upper():
                self.add("WARN", "symbol-value", ref,
                         f"符號是 {part},值寫 {c['value']}:型號不同的符號,腳位或參數可能不一樣")

    def caps_to_gnd(self, net) -> list[tuple[str, float]]:
        out = []
        for r in self.nl.parts_between(net, "GND", "C"):
            val = self.value(r)
            if val:
                out.append((r, val))
        return out

    def supplies(self):
        nl = self.nl
        for ref, c in nl.comps.items():
            spec = SUPPLY_PINS.get(c["lib_id"], {})
            for p in nl.pins[ref].values():
                rule = spec.get(p.name)
                if p.type != "power_in" or p.net == "GND" or not (rule or ref.startswith("U")):
                    continue
                v = self.v.get(p.net)
                if rule:
                    lo, hi, cmin, src = rule
                    if v is None:
                        self.add("WARN", "rail-range", ref, f"{p.name}({p.net})的電壓推算不出來,無法檢查 {src}")
                    else:
                        if lo is not None and v[0] < lo:
                            self.add("ERROR", "rail-range", ref, f"{p.name} 在 {p.net} 最低 {v[0]:.2f}V < {lo:.2f}V({src})")
                        if hi is not None and v[2] > hi:
                            self.add("ERROR", "rail-range", ref, f"{p.name} 在 {p.net} 最高 {v[2]:.2f}V > {hi:.2f}V({src})")
                caps = self.caps_to_gnd(p.net)
                total = sum(x for _, x in caps)
                need = rule[2] if rule else None
                names = ", ".join(f"{r} {nl.comps[r]['value']}" for r, _ in caps) or "無"
                if not caps:
                    self.add("ERROR" if rule else "WARN", "decoupling", ref, f"{p.name}({p.net})沒有對地電容")
                elif need and total < need * 0.999:
                    self.add("ERROR", "decoupling", ref,
                             f"{p.name}({p.net})對地電容共 {total * 1e6:.2f}µF < {need * 1e6:g}µF({names};{rule[3]})")
                else:
                    self.add("OK", "decoupling", ref, f"{p.name}({p.net}"
                             + (f",{fmt_v(v)}" if v else "") + f")對地 {total * 1e6:.2f}µF:{names}")
                if c["lib_id"].startswith("RF_Module:ESP32") and caps and min(x for _, x in caps) > 1e-6:
                    self.add("WARN", "decoupling", ref, f"{p.name} 只有大電容({names}),缺一顆 0.1µF 高頻去耦")

    def inputs(self):
        nl = self.nl
        for ref in nl.comps:
            for p in nl.pins[ref].values():
                if p.type != "input":
                    continue
                others = [q for q in nl.nets[p.net] if q is not p]
                if p.net.startswith("unconnected-") or not others:
                    self.add("ERROR", "input-float", ref, f"輸入腳 {p.name or p.num} 沒有接任何東西")
                elif all(q.type == "input" for q in others) and p.net not in self.v:
                    self.add("ERROR", "input-float", ref,
                             f"輸入腳 {p.name or p.num}({p.net})只接到其他輸入腳,沒有驅動或上下拉")

    def high_side(self, net, exclude) -> tuple | None:
        """LED/電阻高側的電壓:已知電源網,或 MCU 的 GPIO(取 VOH)。"""
        if net in self.v:
            return self.v[net]
        if any(q.ref.startswith("U") and re.fullmatch(r"IO\d+", q.name) and q.ref not in exclude
               for q in self.nl.nets.get(net, [])):
            return GPIO_VOH
        return None

    def is_led(self, ref):
        return "light emitting" in self.nl.description(ref).lower() or self.nl.lib(ref).startswith("Device:LED")

    def leds(self):
        nl = self.nl
        for ref in nl.comps:
            if not self.is_led(ref) or not self.cathode(ref):
                continue
            k, a = self.cathode(ref), self.anode(ref)
            rs = [r for r in nl.nets[a.net] if r.ref.startswith("R") and len(nl.pins[r.ref]) == 2]
            if len(rs) != 1:
                self.add("WARN", "led-current", ref, f"陽極網 {a.net} 上有 {len(rs)} 顆電阻,算不出電流")
                continue
            r = rs[0].ref
            vs = self.high_side(nl.two_pin(r, a.net), {ref})
            if k.net == "GND":
                vl = (0.0, 0.0, 0.0)
            else:
                drv = [q for q in nl.nets[k.net] if q.type == "open_collector"]
                vl = OPEN_COLLECTOR_VCE.get(nl.lib(drv[0].ref)) if drv else None
            vf = range_attr(self.attrs(ref).get("Voltage - Forward(Vf)"))
            rv = self.value(r)
            if vs is None or vl is None or vf is None or not rv:
                miss = [n for n, x in (("電源電壓", vs), ("低側壓降", vl), ("Vf(lcsc-check.json)", vf), ("電阻值", rv)) if not x]
                self.add("WARN", "led-current", ref, f"缺 {'、'.join(miss)},算不出電流")
                continue
            i_lo = (vs[0] - vf[2] - vl[2]) / rv * 1e3
            i_mid = (vs[1] - vf[1] - vl[1]) / rv * 1e3
            i_hi = (vs[2] - vf[0] - vl[0]) / rv * 1e3
            msg = (f"{nl.comps[ref]['value']} 經 {r} {nl.comps[r]['value']}:電流 {max(i_lo, 0):.2f} / {i_mid:.2f} / "
                   f"{i_hi:.2f} mA(最壞 / 中間 / 最大;電源 {fmt_v(vs)}、Vf {vf[0]}–{vf[2]}V、低側 {fmt_v(vl)})")
            if i_mid < LED_MIN_MA:
                self.add("ERROR", "led-current", ref, msg + f" → 中間值 < {LED_MIN_MA}mA,幾乎不亮"
                         "(Vf 是規格測試電流下的值,小電流時略低,實際會亮一點但仍很暗;換低 Vf 的顏色或減小電阻)")
            elif i_lo < LED_MIN_MA:
                self.add("WARN", "led-current", ref, msg + " → 最壞情況可能不亮(Vf 是規格測試電流下的值,實際偏保守)")
            elif i_hi > LED_MAX_MA:
                self.add("ERROR", "led-current", ref, msg + f" → 超過 {LED_MAX_MA}mA")
            else:
                self.add("OK", "led-current", ref, msg)

    def usb_c(self):
        nl = self.nl
        for ref, c in nl.comps.items():
            if not c["lib_id"].startswith("Connector:USB_C_Receptacle"):
                continue
            for name in ("D+", "D-", "VBUS", "GND"):
                nets = {p.net for p in nl.by_name(ref, name)}
                if len(nets) > 1:
                    self.add("ERROR", "usb-c-sink", ref, f"{name} 的腳分在 {sorted(nets)}:USB-C 只有一面插得通")
            cc = {n: nl.by_name(ref, n)[0].net for n in ("CC1", "CC2") if nl.by_name(ref, n)}
            if len(cc) == 2 and cc["CC1"] == cc["CC2"]:
                self.add("ERROR", "usb-c-sink", ref,
                         "CC1 和 CC2 接在同一個網:共用一顆下拉在 USB-C 對 C 線上會被當成不合規裝置(要各自一顆 5.1k)")
                continue
            for name, net in cc.items():
                if any(q.ref.startswith("U") for q in nl.nets[net]):
                    continue                       # 接 PD 控制器,不在這條規則範圍
                rs = nl.parts_between(net, "GND", "R")
                vals = [self.value(r) for r in rs]
                if len(rs) != 1 or not vals[0] or abs(vals[0] / 5100 - 1) > 0.1:
                    self.add("ERROR", "usb-c-sink", ref,
                             f"{name}({net})對地下拉 {[nl.comps[r]['value'] for r in rs]},USB-C 受電端要剛好一顆 5.1k")
                else:
                    self.add("OK", "usb-c-sink", ref, f"{name} → {rs[0]} 5.1k 對地")

    def usb_esd(self):
        nl = self.nl
        vbus = {p.net for r, c in nl.comps.items() if c["lib_id"].startswith("Connector:USB_C")
                for p in nl.by_name(r, "VBUS")}
        for ref, c in nl.comps.items():
            if not c["lib_id"].startswith("Power_Protection:USBLC6"):
                continue
            pv, pg = nl.by_name(ref, "VBUS"), nl.by_name(ref, "GND")
            if pg and pg[0].net != "GND":
                self.add("ERROR", "usb-esd", ref, f"GND 腳接到 {pg[0].net}")
            if pv and vbus and pv[0].net not in vbus:
                self.add("WARN", "usb-esd", ref, f"VBUS 腳接 {pv[0].net},不是 USB 接頭的 VBUS {sorted(vbus)}")

    def esp32c3(self):
        nl = self.nl
        for ref, c in nl.comps.items():
            if not c["lib_id"].startswith("RF_Module:ESP32-C3"):
                continue
            net = {p.name: p.net for p in nl.pins[ref].values()}
            rail = net.get("3V3")

            def pulls(n, to):
                return [r for r in nl.parts_between(n, to, "R")] if n else []

            en = net.get("EN")
            up, cap = pulls(en, rail), nl.parts_between(en, "GND", "C")
            if not up:
                self.add("ERROR", "esp32c3-en", ref, "EN 沒有上拉到 3V3:晶片不會啟動")
            elif not cap:
                self.add("WARN", "esp32c3-en", ref, "EN 沒有對地電容:上電時 EN 比電源先起來,可能啟動失敗(Espressif 建議 10k + 1µF)")
            else:
                tau = self.value(up[0]) * self.value(cap[0])
                lvl = "OK" if tau >= 1e-3 else "WARN"
                self.add(lvl, "esp32c3-en", ref, f"EN RC = {up[0]} {nl.comps[up[0]]['value']} × {cap[0]} "
                         f"{nl.comps[cap[0]]['value']} = {tau * 1e3:.1f} ms(Espressif 建議 10k × 1µF = 10 ms)")
            # 開機腳(ESP32-C3 規格書 §3.3 Strapping Pins)
            for io, need_up in (("IO9", False), ("IO8", True), ("IO2", True)):
                n = next((v for k, v in net.items() if k.split("/")[0] == io), None)
                if n is None:
                    continue
                if n == "GND" or pulls(n, "GND"):
                    self.add("ERROR", "esp32c3-strap", ref, f"{io}({n})被拉低:{io} 是開機腳,上電為 0 會進錯模式")
                elif need_up and not pulls(n, rail):
                    self.add("WARN", "esp32c3-strap", ref, f"{io}({n})沒有外部上拉:{io} 是開機腳,下載模式要求為 1")
                loads = [q.ref for q in nl.nets[n] if q.ref != ref and not q.ref.startswith(("R", "SW", "J"))]
                if loads:
                    self.add("WARN", "esp32c3-strap", ref, f"{io} 是開機腳,還接了 {loads}:上電時這些負載會改變開機模式")
            # 原生 USB:GPIO18 = D−、GPIO19 = D+
            usb = {name: p.net for r, cc in nl.comps.items() if cc["lib_id"].startswith("Connector:USB")
                   for name in ("D+", "D-") for p in nl.by_name(r, name)}
            for io, d in (("IO18", "D-"), ("IO19", "D+")):
                n = next((v for k, v in net.items() if k.split("/")[0] == io), None)
                if usb and n and d in usb:
                    if n != usb[d]:
                        self.add("ERROR", "esp32c3-usb", ref, f"{io} 接 {n},但 USB 的 {d} 是 {usb[d]}(GPIO18 = D−、GPIO19 = D+)")
                    else:
                        self.add("OK", "esp32c3-usb", ref, f"{io} = USB {d}")

    def inductive(self):
        nl = self.nl
        for ref, c in nl.comps.items():
            spec = INDUCTIVE.get(c["lib_id"])
            if not spec:
                continue
            n1, n2 = (nl.pins[ref][p].net for p in spec["coil"])
            supply, drive = (n1, n2) if n1 in self.v else (n2, n1)
            if supply not in self.v:
                self.add("WARN", "inductive", ref, f"線圈兩端 {n1} / {n2} 都不是已知電源")
                continue
            oc = [q for q in nl.nets[drive] if q.type == "open_collector"]
            diodes = [r for r in nl.parts_between(drive, supply, "D")
                      if self.cathode(r) and self.cathode(r).net == supply]
            ok = bool(diodes)
            vce = (0.0, 0.0, 0.0)
            for q in oc:
                com = nl.by_name(q.ref, "COM")
                ok |= bool(com) and com[0].net == supply
                vce = OPEN_COLLECTOR_VCE.get(nl.lib(q.ref), vce)
            if not ok:
                self.add("ERROR", "inductive", ref, f"線圈({supply} ↔ {drive})沒有續流路徑:驅動關斷時的反電動勢會打壞驅動器"
                         "(ULN2803 的 COM 接線圈電源,或線圈並聯反向二極體)")
            vs = self.v[supply]
            worst, typ = vs[0] - vce[2], vs[1] - vce[1]
            need = spec["pickup"] * spec["rated"]
            msg = f"線圈電壓 最壞 {worst:.2f}V / 典型 {typ:.2f}V,吸合要 ≥ {need:.2f}V(電源 {fmt_v(vs)} − 驅動壓降 {fmt_v(vce)})"
            if typ < need:
                self.add("ERROR", "inductive", ref, msg)
            elif worst < need:
                self.add("WARN", "inductive", ref, msg + " → 最壞組合可能吸不住")
            elif ok:
                self.add("OK", "inductive", ref, msg)

    def caps(self):
        nl = self.nl
        for ref in nl.comps:
            if not ref.startswith("C") or len(nl.pins[ref]) != 2:
                continue
            p1, p2 = nl.pins[ref].get("1"), nl.pins[ref].get("2")
            v1, v2 = self.v.get(p1.net), self.v.get(p2.net)
            if v1 is None or v2 is None:
                continue
            span = max(abs(v1[2] - v2[0]), abs(v2[2] - v1[0]))
            if "polarized" in nl.description(ref).lower() and v1[1] < v2[1]:
                self.add("ERROR", "cap-voltage", ref, f"電解電容反接:+ 腳在 {p1.net}({fmt_v(v1)}),− 腳在 {p2.net}({fmt_v(v2)})")
            rating = si_value((self.attrs(ref).get("Voltage Rating") or "").replace("V", ""))
            if rating is None:
                continue
            if span > rating:
                self.add("ERROR", "cap-voltage", ref, f"跨壓最高 {span:.2f}V > 耐壓 {rating:g}V")
            elif span > 0.8 * rating:
                self.add("WARN", "cap-voltage", ref, f"跨壓最高 {span:.2f}V > 耐壓 {rating:g}V 的 80%")


def merge(rs):
    """同一個網有多個來源(例如兩路二極體 OR):取包絡。"""
    return (min(r[0] for r in rs), max(r[1] for r in rs), max(r[2] for r in rs))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    bdir = Path(sys.argv[1]).resolve()
    netfile = Path(sys.argv[2]) if len(sys.argv) > 2 else bdir / "net.txt"
    nl = Netlist(netfile)
    chk = bdir / "lcsc-check.json"
    parts = json.loads(chk.read_text(encoding="utf-8"))["parts"] if chk.exists() else {}
    wf = bdir / "review-waivers.json"
    waivers = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else {}
    rv = Review(nl, parts, waivers)
    rv.run()
    used = {f"{r}|{ref}" for _, r, ref, _ in rv.findings}
    for k in sorted(set(waivers) - used):
        rv.findings.append(("WARN", "waiver", "-", f"review-waivers.json 的 {k} 沒有對應任何發現(已經修掉?刪掉這筆)"))
    order = {"ERROR": 0, "WARN": 1, "INFO": 2, "OK": 3}
    rv.findings.sort(key=lambda f: (order[f[0]], f[1], natural(f[2])))
    lines = [f"{lvl:5s} {rule:15s} {ref:5s} {msg}" for lvl, rule, ref, msg in rv.findings]
    count = {k: sum(1 for f in rv.findings if f[0] == k) for k in order}
    lines.append(f"設計審查:ERROR {count['ERROR']}、WARN {count['WARN']}、INFO {count['INFO']}、OK {count['OK']}")
    lines.append("推算出的網電壓:" + "、".join(f"{n} {fmt_v(v)}" for n, v in sorted(rv.v.items())))
    text = "\n".join(lines)
    print("\n".join(x for x in lines if not x.startswith(("OK", "推算"))))
    if netfile == bdir / "net.txt":
        (bdir / "review.txt").write_text(text + "\n", encoding="utf-8")
    return 1 if count["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
