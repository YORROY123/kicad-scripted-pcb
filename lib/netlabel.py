"""网络标签式原理图:每个引脚沿「离开器件」的方向拉一小段线,挂一个全局标签。

电路本身就是一张「引脚 → 网络」对照表,审查时逐行对 datasheet。
同时把对照表记进 NetLabeler.expected,写成 expected_nets.json 交给 check_netlist.py
和 kicad-cli 导出的网表逐脚比对 —— ERC 默认不报「全局标签只出现一次」,
标签名打错字会变成一个孤立的网,只有比对网表才抓得到。
"""
import json
import math
from pathlib import Path

from schgen import Part, Schematic

G = 1.27
STUB = 2 * G

# 标签朝向:文字顺着短线方向往外长,不压在器件上
LABEL_ROT = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}


def g(n: float) -> float:
    """格数 → mm(1.27mm 连接格)。"""
    return round(n * G, 4)


def outward(part: Part, pin: str) -> tuple[int, int]:
    """引脚「离开器件」的单位方向(图纸坐标,y 向下)。

    符号库里引脚的 angle 指向器件本体;反过来就是向外。还要套上器件的旋转。
    """
    part.pin_xy(pin)                       # 确保 _pins 已载入
    a = math.radians(part._pins[pin]["angle"] + 180)
    vx, vy = math.cos(a), -math.sin(a)     # 符号库 y 向上 → 图纸 y 向下
    r = math.radians(part.rotation)
    rx = vx * math.cos(r) - vy * math.sin(r)
    ry = vx * math.sin(r) + vy * math.cos(r)
    return round(rx), round(ry)


class NetLabeler:
    def __init__(self, sch: Schematic):
        self.s = sch
        self.expected: dict = {}

    def attach(self, part: Part, pins: dict) -> Part:
        """按「引脚 → 网络」接线;网络为 None 表示刻意不接(打 NC 记号)。

        同一坐标上的堆叠引脚(USB-C 的 A4/A9/B4/B9 等)只挂一次标签。
        """
        seen = set()
        for pin, net in pins.items():
            if not part.ref.startswith("#"):
                self.expected[f"{part.ref}.{pin}"] = net
            xy = part.pin_xy(pin)
            if xy in seen:
                continue
            seen.add(xy)
            if net is None:
                self.s.no_connect(part, pin)
                continue
            ox, oy = outward(part, pin)
            self.s.label(net, part, pin, dx=ox * STUB, dy=oy * STUB,
                         rotation=LABEL_ROT[(ox, oy)])
        return part

    def add(self, ref, lib, name, x, y, value, footprint, pins, rot=0.0) -> Part:
        """x, y 以格数给(×1.27mm),保证引脚落在连接格上。"""
        p = self.s.add(Part(ref, lib, name, g(x), g(y), value=value, footprint=footprint,
                            rotation=rot))
        return self.attach(p, pins)

    def flag(self, net: str, x: float, y: float) -> None:
        """PWR_FLAG:告诉 ERC 这个网确实由外部供电。"""
        p = self.s.add(Part(f"#FLG{len(self.s.parts):02d}", "power", "PWR_FLAG", g(x), g(y),
                            value="PWR_FLAG", fields_hidden=True))
        self.attach(p, {"1": net})

    def write(self, out: Path) -> None:
        """自检通过才写出原理图与 expected_nets.json。"""
        bad = self.s.crossing_pins() + self.s.overlapping_wires()
        if bad:
            print(f"!! 自检失败 {len(bad)} 项,拒绝写出:")
            for b in bad:
                print("   ", b)
            raise SystemExit(1)
        (out.parent / "expected_nets.json").write_text(
            json.dumps(self.expected, indent=1, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")
        out.write_text(self.s.render(), encoding="utf-8", newline="\n")
        print(f"wrote {out.name}: {len(self.s.parts)} parts, {len(self.s.labels)} labels")
