"""从 KiCad 安装目录的 .kicad_sym 里抽出符号定义,供内嵌进 .kicad_sch 的 lib_symbols。

为什么需要它:.kicad_sch 不引用外部库,它把用到的符号**整段抄进文件里**。
手抄不现实(一个 USB-C 插座上千行),所以按括号配对精确切出来。
"""
from __future__ import annotations

import re

from kicad_paths import kicad_share

SYMBOL_DIR = kicad_share() / "symbols"


def _block_at(text: str, start: int) -> str:
    """从 start 处的 '(' 起，按括号配对返回完整的一段 S-expression。

    必须跳过字符串字面量里的括号与转义 —— 符号的 property 里就有带括号的说明文字，
    单纯数括号会在那里断掉，切出半截定义，而 ERC 只会含糊地报解析失败。
    """
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise ValueError("unbalanced S-expression")


def _raw(lib: str, name: str) -> str:
    """库文件里那一段原样的 (symbol "name" ...)。"""
    path = SYMBOL_DIR / f"{lib}.kicad_sym"
    text = path.read_text(encoding="utf-8")
    m = re.search(r'^\t\(symbol "' + re.escape(name) + r'"', text, re.M)
    if not m:
        raise KeyError(f"{lib}:{name} not found in {path.name}")
    return _block_at(text, m.start())


def _units(block: str, owner: str) -> list[str]:
    """符号的「单元」子块 —— 图形与引脚都在这里面，名字形如 Owner_0_1 / Owner_1_1。"""
    out = []
    for m in re.finditer(r'\n\t\t\(symbol "' + re.escape(owner) + r'_\d+_\d+"', block):
        out.append(_block_at(block, m.start() + 1))
    return out


def extract(lib: str, name: str) -> str:
    """返回可直接内嵌进 lib_symbols 的符号定义，id 改写成 'Lib:Name'。

    **派生符号必须展平。** 库里 AMS1117-3.3 只写 (extends "AP1117-15")，
    图形和引脚都在父符号那边；而真实的 .kicad_sch 里不存在 extends
    (KiCad 自带的 demos 全部如此)。所以这里把父符号的单元子块搬过来并改名，
    保留子符号自己的 property —— 否则内嵌进去的会是一个 0 引脚的空壳，
    ERC 照样能跑，只是所有连接都对不上。
    """
    block = _raw(lib, name)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:
        parent = ext.group(1)
        pblock = _raw(lib, parent)
        # 子符号:去掉 extends 行,保留它自己的 property
        body = re.sub(r'\n\s*\(extends "[^"]+"\)', "", block, count=1)
        # 父符号的单元子块(图形+引脚)改名后并入
        units = "\n".join(u.replace(f'"{parent}_', f'"{name}_') for u in _units(pblock, parent))
        # 父符号上这些开关子符号自己没有声明时要继承,否则渲染/网表行为会变
        inherited = "".join(
            f"\n\t\t{m.group(0)}"
            for key in ("pin_names", "pin_numbers", "exclude_from_sim", "in_bom", "on_board")
            for m in [re.search(r"\(" + key + r"[^()]*(?:\([^()]*\)[^()]*)*\)", pblock)]
            if m and f"({key}" not in body
        )
        body = body.rstrip()
        assert body.endswith(")")
        block = body[:-1].rstrip() + inherited + "\n" + units + "\n\t)"
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)


def pins(block: str) -> list[dict]:
    """列出符号的引脚:编号、名称、位置、朝向。连线要按这些坐标算，不能猜。"""
    out = []
    for m in re.finditer(r"\(pin\s+(\w+)\s+(\w+)\s*\n\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)", block):
        seg = _block_at(block, m.start())
        num = re.search(r'\(number "([^"]*)"', seg)
        nm = re.search(r'\(name "([^"]*)"', seg)
        out.append({
            "electrical": m.group(1), "shape": m.group(2),
            "x": float(m.group(3)), "y": float(m.group(4)), "angle": float(m.group(5)),
            "number": num.group(1) if num else "?",
            "name": nm.group(1) if nm else "",
        })
    return out


if __name__ == "__main__":
    import sys
    lib, name = sys.argv[1], sys.argv[2]
    b = extract(lib, name)
    print(f"{lib}:{name}  {len(b)} chars, {len(pins(b))} pins")
    for p in pins(b):
        print(f"  pin {p['number']:>4}  {p['name']:<10} @({p['x']:>7.2f},{p['y']:>7.2f}) {p['angle']:>5.0f}deg  {p['electrical']}")
