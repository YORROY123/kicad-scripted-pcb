"""lib/review.py 的突變測試:每一條規則都拿真的網表故意弄錯一處,確認一定報 ERROR;
沒動過的網表必須 0 ERROR(否則規則有誤報)。

    python lib/review_test.py        (要先 build 過三塊板,有 net.txt 與 lcsc-check.json)

第一項就是 usbc-ldo 真的發生過的錯:SMAJ5.0A 接反、+5V 對地短路。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review import Netlist, Review  # noqa: E402

BOARDS = Path(__file__).resolve().parent.parent / "boards"


def load(board):
    bdir = BOARDS / board
    nl = Netlist(bdir / "net.txt")
    parts = json.loads((bdir / "lcsc-check.json").read_text(encoding="utf-8"))["parts"]
    wf = bdir / "review-waivers.json"
    waivers = json.loads(wf.read_text(encoding="utf-8")) if wf.exists() else {}
    return nl, parts, waivers


def move(nl, ref, num, net):
    """把 ref 的 num 腳改接到 net。"""
    p = nl.pins[ref][num]
    nl.nets[p.net].remove(p)
    p.net = net
    nl.nets.setdefault(net, []).append(p)


def swap(nl, ref, a, b):
    na, nb = nl.pins[ref][a].net, nl.pins[ref][b].net
    move(nl, ref, a, nb)
    move(nl, ref, b, na)


def remove(nl, ref):
    for p in nl.pins.pop(ref).values():
        nl.nets[p.net].remove(p)
    del nl.comps[ref]


def set_value(nl, ref, v):
    nl.comps[ref]["value"] = v


def by_name(nl, ref, name):
    return nl.by_name(ref, name)[0].num


# 已不在料表裡、但突變要用到的料(屬性抄自 JLCPCB 查詢結果)
EXTRA_PARTS = {
    "BLUE|LED_SMD:LED_0805_2012Metric": {"lcsc": "C84259", "attrs": {"Voltage - Forward(Vf)": "2.5V~3.6V"}},
}

CASES = [
    ("usbc-ldo", "diode-short", "D3", "TVS 接反(第一版真的這樣畫)", lambda nl: swap(nl, "D3", "1", "2")),
    ("usbc-ldo", "led-current", "LED1", "LED 限流電阻 1k → 47Ω", lambda nl: set_value(nl, "R3", "47")),
    ("esp32c3", "usb-c-sink", "J1", "CC2 併到 CC1", lambda nl: move(nl, "J1", by_name(nl, "J1", "CC2"), "CC1")),
    ("esp32c3", "usb-c-sink", "J1", "CC1 下拉改 10k", lambda nl: set_value(nl, "R1", "10k")),
    ("esp32c3", "usb-c-sink", "J1", "B 面 D+ 沒接", lambda nl: move(nl, "J1", "B6", "unconnected-x")),
    ("esp32c3", "esp32c3-usb", "U1", "GPIO18 / GPIO19 對調", lambda nl: swap(nl, "U1", "13", "14")),
    ("esp32c3", "esp32c3-en", "U1", "拿掉 EN 上拉", lambda nl: remove(nl, "R3")),
    ("esp32c3", "esp32c3-strap", "U1", "GPIO9 上拉接成下拉", lambda nl: move(nl, "R4", "1", "GND")),
    ("esp32c3", "decoupling", "U1", "3V3 的 10µF 改 1µF", lambda nl: set_value(nl, "C2", "1uF")),
    ("esp32c3", "decoupling", "U2", "拿掉 LDO 輸入電容", lambda nl: remove(nl, "C5")),
    ("esp32c3", "led-current", "D2", "黃光換回藍光(C84259,Vf 2.5–3.6V)", lambda nl: set_value(nl, "D2", "BLUE")),
    ("esp32c3", "input-float", "U2", "LDO EN 空接", lambda nl: move(nl, "U2", "1", "unconnected-en")),
    ("relay8", "inductive", "K1", "ULN2803 COM 接地(沒有續流)", lambda nl: move(nl, "U3", "10", "GND")),
    ("relay8", "cap-voltage", "C5", "電解電容反接", lambda nl: swap(nl, "C5", "1", "2")),
    ("relay8", "rail-range", "U1", "模組 3V3 接到 5V", lambda nl: move(nl, "U1", "1", "5V_PS")),
]


def errors(nl, parts, waivers):
    rv = Review(nl, parts, waivers)
    rv.run()
    return [(r, ref, m) for lvl, r, ref, m in rv.findings if lvl == "ERROR"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    bad = 0
    for board in ("usbc-ldo", "esp32c3", "relay8"):
        e = errors(*load(board))
        print(f"{'PASS' if not e else 'FAIL'}  {board}:原樣 0 ERROR" + (f",實際 {e}" if e else ""))
        bad += bool(e)
    for board, rule, ref, what, mutate in CASES:
        nl, parts, waivers = load(board)
        parts = {**parts, **EXTRA_PARTS}
        mutate(nl)
        hit = [x for x in errors(nl, parts, waivers) if x[0] == rule and x[1] == ref]
        print(f"{'PASS' if hit else 'FAIL'}  {board}:{what} → {rule} {ref}" + (f"\n        {hit[0][2]}" if hit else ""))
        bad += not hit
    print("全部通過" if not bad else f"{bad} 項未通過")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
