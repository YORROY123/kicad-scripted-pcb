"""把「器件 + 连线」生成为 .kicad_sch。

设计取向:**坐标由引脚几何算出来，不手填。** 放一个器件时给它的原点坐标，
连线时只说「R1 的 2 脚接 C1 的 1 脚」,由本模块查符号的引脚偏移算出实际端点。
这样改动器件位置不会悄悄把连线扯断 —— 那是 EasyEDA 那边反复踩到的坑。
"""
from __future__ import annotations

import math
import uuid as _uuid
from dataclasses import dataclass, field

import ksym

SHEET = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}


def uid() -> str:
    return str(_uuid.uuid4())


@dataclass
class Part:
    ref: str            # R1
    lib: str            # Device
    name: str           # R
    x: float
    y: float
    value: str = ""
    footprint: str = ""
    rotation: float = 0.0
    mirror: str = ""    # "" | "x" | "y"
    fields_hidden: bool = False
    _pins: dict = field(default_factory=dict, init=False)

    @property
    def libid(self) -> str:
        return f"{self.lib}:{self.name}"

    def pin_xy(self, number: str) -> tuple[float, float]:
        """引脚在图纸上的绝对坐标。

        符号库的 y 轴向上，.kicad_sch 的 y 轴向下 —— 少翻这个号，线会接到
        镜像位置上，而 ERC 只会告诉你「引脚未连接」,不会说是为什么。
        """
        if not self._pins:
            block = ksym.extract(self.lib, self.name)
            self._pins = {p["number"]: p for p in ksym.pins(block)}
        p = self._pins[number]
        px, py = p["x"], -p["y"]
        a = math.radians(self.rotation)
        rx = px * math.cos(a) - py * math.sin(a)
        ry = px * math.sin(a) + py * math.cos(a)
        if self.mirror == "y":
            rx = -rx
        elif self.mirror == "x":
            ry = -ry
        return (round(self.x + rx, 4), round(self.y + ry, 4))


@dataclass
class Wire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Label:
    """全局标签 —— 电源/地/跨区网络用它命名，省掉一堆长导线。"""
    text: str
    x: float
    y: float
    rotation: float = 0.0
    shape: str = "input"


class Schematic:
    def __init__(self, paper: str = "A4", title: str = ""):
        self.paper = paper
        self.title = title
        self.parts: list[Part] = []
        self.wires: list[Wire] = []
        self.labels: list[Label] = []
        self.junctions: list[tuple[float, float]] = []
        self.nc: list[tuple[float, float]] = []
        self.uuid = uid()

    def add(self, part: Part) -> Part:
        self.parts.append(part)
        return part

    def no_connect(self, part: Part, pin: str) -> None:
        """显式标记「这脚就是不接」—— KiCad 版的 NC。

        不标的话 ERC 会报 pin_not_connected,而「没接」与「忘了接」在报告里
        长得一模一样,真正的漏接就被淹掉了。
        """
        self.nc.append(part.pin_xy(pin))

    def autojunction(self) -> None:
        """在 T 形交会处补 junction。

        **KiCad 不会把「线端点落在另一条线中间」当成连接** —— 必须有 junction。
        这是本生成器踩到的最大一个坑:线画得完全正确、图上看起来接着,
        ERC 却报一片 pin_not_connected,因为整条 GND 干线上的每个接点都缺这一点。

        判据:某条线的端点严格落在另一条线的内部(不含另一条线自己的端点),
        或三条以上线端重合 —— 两条线首尾相接是拐角,不需要 junction。
        """
        def on_segment(px, py, w) -> bool:
            if abs(w.x1 - w.x2) < 1e-9:                      # 垂直
                if abs(px - w.x1) > 1e-6:
                    return False
                lo, hi = sorted((w.y1, w.y2))
                return lo - 1e-6 < py < hi + 1e-6
            if abs(w.y1 - w.y2) < 1e-9:                      # 水平
                if abs(py - w.y1) > 1e-6:
                    return False
                lo, hi = sorted((w.x1, w.x2))
                return lo - 1e-6 < px < hi + 1e-6
            return False

        from collections import Counter
        ends = Counter()
        for w in self.wires:
            ends[(round(w.x1, 4), round(w.y1, 4))] += 1
            ends[(round(w.x2, 4), round(w.y2, 4))] += 1

        found: set[tuple[float, float]] = set()
        for pt, n in ends.items():
            if n >= 3:                                        # 三线交会
                found.add(pt)
                continue
            for w in self.wires:                              # 端点落在别的线中间
                if (round(w.x1, 4), round(w.y1, 4)) == pt or (round(w.x2, 4), round(w.y2, 4)) == pt:
                    continue
                if on_segment(pt[0], pt[1], w):
                    found.add(pt)
                    break
        self.junctions = sorted(found)

    def wire(self, a: tuple[float, float], b: tuple[float, float]) -> None:
        self.wires.append(Wire(a[0], a[1], b[0], b[1]))

    def crossing_pins(self, allow: set[str] | None = None) -> list[str]:
        """找出「导线从某个引脚身上横穿过去」的地方。

        **KiCad 只要线经过引脚就算接上,而 ERC 不会报这种短路** —— 两端都是
        passive 时它一声不吭,只有导出网表逐条看才发现。实测踩到两次:
        VBUS 进二极管的线穿过它另一只脚(二极管被短路)、CC 下拉的竖线穿过
        ESD 的 I/O 脚(D+ 被拉到地)。两次 ERC 都是干净的。

        判据:引脚落在某条线的**内部**(不含端点),且这条线不是为它画的。
        端点重合是正常连接,不报。

        allow 是**刻意**被干线分接的引脚(例如 GND 干线扫过某个 GND 脚、
        电源旗标挂在电源干线上)。必须逐个列名,不能整类豁免 ——
        豁免的理由是「我确认这一脚就该在这条网上」,不是「这类一般没事」。
        """
        allow = allow or set()
        pins: list[tuple[float, float, str]] = []
        for p in self.parts:
            block = ksym.extract(p.lib, p.name)
            for pin in ksym.pins(block):
                x, y = p.pin_xy(pin["number"])
                pins.append((x, y, f"{p.ref}.{pin['number']}"))

        bad: list[str] = []
        for x, y, tag in pins:
            if tag in allow:
                continue
            for w in self.wires:
                ends = ((round(w.x1, 4), round(w.y1, 4)), (round(w.x2, 4), round(w.y2, 4)))
                if (round(x, 4), round(y, 4)) in ends:
                    continue                                  # 线就是接在这只脚上
                if abs(w.x1 - w.x2) < 1e-9 and abs(x - w.x1) < 1e-6:
                    lo, hi = sorted((w.y1, w.y2))
                    if lo + 1e-6 < y < hi - 1e-6:
                        bad.append(f"{tag} @({x},{y}) 被竖线 ({w.x1},{w.y1})-({w.x2},{w.y2}) 横穿")
                elif abs(w.y1 - w.y2) < 1e-9 and abs(y - w.y1) < 1e-6:
                    lo, hi = sorted((w.x1, w.x2))
                    if lo + 1e-6 < x < hi - 1e-6:
                        bad.append(f"{tag} @({x},{y}) 被横线 ({w.x1},{w.y1})-({w.x2},{w.y2}) 横穿")
        return bad

    def rail(self, y: float, xs: list[float]) -> None:
        """在 y 上画一条干线,按分接点切成连续段。

        不要从同一个起点反复画长线到不同的 x:那些线彼此重叠,虽然同属一个网
        不影响电气,但会让「共线重叠」这个守卫失去意义 —— 真正的跨网重叠
        (D+ 与 D- 走同一条车道)就淹没在噪声里了。
        """
        pts = sorted(set(round(x, 4) for x in xs))
        for a, b in zip(pts, pts[1:]):
            self.wire((a, y), (b, y))

    def overlapping_wires(self) -> list[str]:
        """找出共线且重叠的导线对。

        两条本该属于不同网的线如果走同一条「车道」并且区间相交,KiCad 会把它们
        并成一个网 —— 这不会横穿任何引脚,所以 crossing_pins 抓不到,ERC 也不报。
        实测踩过:D+ 与 D- 的引线都走 x=68.58,结果两条数据线被短在一起,
        而网表要逐条看才发现。
        """
        bad: list[str] = []
        for i, a in enumerate(self.wires):
            for b in self.wires[i + 1:]:
                if abs(a.x1 - a.x2) < 1e-9 and abs(b.x1 - b.x2) < 1e-9 and abs(a.x1 - b.x1) < 1e-6:
                    lo1, hi1 = sorted((a.y1, a.y2)); lo2, hi2 = sorted((b.y1, b.y2))
                    axis, fixed = "x", a.x1
                elif abs(a.y1 - a.y2) < 1e-9 and abs(b.y1 - b.y2) < 1e-9 and abs(a.y1 - b.y1) < 1e-6:
                    lo1, hi1 = sorted((a.x1, a.x2)); lo2, hi2 = sorted((b.x1, b.x2))
                    axis, fixed = "y", a.y1
                else:
                    continue
                ovl = min(hi1, hi2) - max(lo1, lo2)
                if ovl > 1e-6:                      # 仅端点相接(ovl≈0)是正常的首尾相连
                    bad.append(f"{axis}={fixed} 上两段重叠 {ovl:.2f}mm: "
                               f"[{lo1:.2f},{hi1:.2f}] 与 [{lo2:.2f},{hi2:.2f}]")
        return bad

    def connect(self, p1: Part, n1: str, p2: Part, n2: str, *, via_x: float | None = None) -> None:
        """按引脚编号连两个器件。默认走 L 形(先水平后垂直)，via_x 可指定折点。

        端点一律取自 pin_xy —— 连线永远落在真实引脚上，不存在「坐标重合但没接上」。
        """
        a, b = p1.pin_xy(n1), p2.pin_xy(n2)
        if abs(a[1] - b[1]) < 1e-6 or abs(a[0] - b[0]) < 1e-6:
            self.wire(a, b)
            return
        mx = via_x if via_x is not None else b[0]
        self.wire(a, (mx, a[1]))
        self.wire((mx, a[1]), b)

    def label(self, text: str, part: Part, pin: str, *, dx: float = 0.0, dy: float = 0.0,
              rotation: float = 0.0) -> None:
        """在引脚上挂一个全局标签,并用一小段导线接上去(坐标重合不算连接)。"""
        x, y = part.pin_xy(pin)
        tx, ty = x + dx, y + dy
        if (dx, dy) != (0.0, 0.0):
            self.wire((x, y), (tx, ty))
        self.labels.append(Label(text, tx, ty, rotation))

    # ── 渲染 ────────────────────────────────────────────────────────────
    def _lib_symbols(self) -> str:
        seen: dict[str, str] = {}
        for p in self.parts:
            if p.libid not in seen:
                seen[p.libid] = ksym.extract(p.lib, p.name)
        return "\n".join(seen[k] for k in sorted(seen))

    def _instance(self, p: Part) -> str:
        pid = uid()
        mirror = f"\n\t\t(mirror {p.mirror})" if p.mirror else ""
        pin_uuids = "\n".join(
            f'\t\t(pin "{n}" (uuid {uid()}))'
            for n in (p._pins or {k["number"]: k for k in ksym.pins(ksym.extract(p.lib, p.name))})
        )
        hide = "\n\t\t\t\t(hide yes)" if p.fields_hidden else ""
        return f"""	(symbol
		(lib_id "{p.libid}")
		(at {p.x} {p.y} {p.rotation:g}){mirror}
		(unit 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(fields_autoplaced yes)
		(uuid {pid})
		(property "Reference" "{p.ref}"
			(at {p.x + 2.54} {p.y - 2.54} 0)
			(effects (font (size 1.27 1.27)) (justify left))
		)
		(property "Value" "{p.value or p.name}"
			(at {p.x + 2.54} {p.y} 0)
			(effects (font (size 1.27 1.27)) (justify left){hide})
		)
		(property "Footprint" "{p.footprint}"
			(at {p.x} {p.y} 0)
			(effects (font (size 1.27 1.27)) (hide yes))
		)
{pin_uuids}
		(instances
			(project ""
				(path "/{self.uuid}"
					(reference "{p.ref}")
					(unit 1)
				)
			)
		)
	)"""

    def render(self) -> str:
        self.autojunction()
        w, h = SHEET[self.paper]
        parts = "\n".join(self._instance(p) for p in self.parts)
        wires = "\n".join(
            f"""	(wire
		(pts (xy {x.x1} {x.y1}) (xy {x.x2} {x.y2}))
		(stroke (width 0) (type default))
		(uuid {uid()})
	)""" for x in self.wires)
        labels = "\n".join(
            f"""	(global_label "{l.text}"
		(shape {l.shape})
		(at {l.x} {l.y} {l.rotation:g})
		(effects (font (size 1.27 1.27)) (justify left))
		(uuid {uid()})
	)""" for l in self.labels)
        juncs = "\n".join(
            f"""	(junction
		(at {x} {y})
		(diameter 0)
		(color 0 0 0 0)
		(uuid {uid()})
	)""" for x, y in self.junctions)
        ncs = "\n".join(
            f"""	(no_connect
		(at {x} {y})
		(uuid {uid()})
	)""" for x, y in self.nc)
        title = f'\n\t\t(title "{self.title}")' if self.title else ""
        return f"""(kicad_sch
	(version 20250114)
	(generator "schgen")
	(generator_version "9.0")
	(uuid {self.uuid})
	(paper "{self.paper}")
	(title_block{title}
	)
	(lib_symbols
{self._lib_symbols()}
	)
{wires}
{juncs}
{ncs}
{labels}
{parts}
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
)
"""
