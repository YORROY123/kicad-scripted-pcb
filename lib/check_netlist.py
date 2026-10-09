"""网表比对:kicad-cli 导出的网表 vs board.py 写下的设计意图(expected_nets.json)。

抓 ERC 抓不到的三类错:
  1. 引脚接错网(标签打错字、接错脚)
  2. 只接了一个引脚的网(孤立网 —— ERC 默认忽略「全局标签只出现一次」)
  3. 设计里写了、网表里却没有的引脚(或反过来)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pcbgen import read_netlist  # noqa: E402

# 用法:check_netlist.py <专案目录>(内含 net.txt 与 expected_nets.json)
root = Path(sys.argv[1]).resolve()
expected = json.loads((root / "expected_nets.json").read_text(encoding="utf-8"))
_, pad_net = read_netlist(root / "net.txt")
actual = {f"{r}.{p}": n for (r, p), n in pad_net.items()}

problems = []
for key, want in sorted(expected.items()):
    got = actual.get(key)
    if want is None:
        if got is not None and not got.startswith("unconnected-"):
            problems.append(f"{key}: 应为 NC,网表里接到了 {got!r}")
    elif got != want:
        problems.append(f"{key}: 应接 {want!r},网表是 {got!r}")
for key in sorted(set(actual) - set(expected)):
    if not key.startswith("#"):
        problems.append(f"{key}: 网表里有,设计意图里没写({actual[key]!r})")

members: dict = {}
for key, net in actual.items():
    members.setdefault(net, []).append(key)
for net, pins in sorted(members.items()):
    if len(pins) < 2 and not net.startswith("unconnected-"):
        problems.append(f"网 {net!r} 只接了 {pins} —— 孤立网")

if problems:
    print(f"!! 网表比对失败 {len(problems)} 项:")
    for p in problems:
        print("   ", p)
    raise SystemExit(1)
nets = {n for n in members if not n.startswith("unconnected-")}
print(f"网表比对通过:{len(expected)} 个引脚逐一相符,{len(nets)} 个网都至少接 2 个引脚")
