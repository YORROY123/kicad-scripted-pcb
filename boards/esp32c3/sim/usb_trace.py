"""ESP32-C3 板 USB D+/D− 走線:要不要做阻抗控制?

    python boards/esp32c3/sim/usb_trace.py      (要 numpy + scipy;約 1 分鐘)

判據:走線傳播延遲 t_pd ≤ t_r / 6 時,走線可視為集總元件,阻抗不匹配造成的反射
在邊沿爬升期間就已經平息,不必做阻抗控制。USB 2.0 Full Speed(12 Mbps)驅動器
上升時間 4–20 ns(USB 2.0 表 7-9 TFR),取最快的 4 ns。
High Speed(480 Mbps,500 ps)才需要 90 Ω 差分 —— ESP32-C3 只有 FS。

幾何(都從板檔讀,不寫死):線寬、長度取自 .kicad_pcb 的 USB_DP / USB_DN 線段;
GND 鋪銅間隙 0.3 mm(lib/route.py 的 SetLocalClearance)、雙面鋪銅 → 接地共面波導。
疊構:JLCPCB 2 層 1.6 mm,FR-4 介質約 1.53 mm(扣兩面 35 µm 銅)、εr 取 4.5。
場解器 lib/field2d.py(驗證見 lib/field2d_check.py,對三個封閉公式誤差 < 0.6%)。
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import field2d as f  # noqa: E402

PCB = HERE.parent / "esp32c3.kicad_pcb"
H, T, ER = 1.53, 0.035, 4.5
GAP = 0.3            # GND 鋪銅間隙,與 lib/route.py 一致
T_RISE_FS = 4e-9     # USB FS 最快上升時間
D = 0.005            # 唯一能同時整除 0.125 / 0.3 / 0.035 / 1.53 的格距


def usb_tracks(text: str) -> dict[str, dict]:
    nets = {m.group(1): m.group(2) for m in re.finditer(r'\(net (\d+) "([^"]*)"\)', text)}
    seg = re.compile(r'\(segment\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)\s+'
                     r'\(width ([\d.]+)\)\s+\(layer "([^"]+)"\)\s+\(net (?:(\d+)|"([^"]*)")')
    out: dict[str, dict] = {}
    for m in seg.finditer(text):
        net = m.group(8) or nets.get(m.group(7))
        if net not in ("USB_DP", "USB_DN"):
            continue
        x1, y1, x2, y2, w = map(float, m.groups()[:5])
        t = out.setdefault(net, {"len": 0.0, "widths": set()})
        t["len"] += math.hypot(x2 - x1, y2 - y1)
        t["widths"].add(w)
    if set(out) != {"USB_DP", "USB_DN"}:
        raise SystemExit(f"板檔裡找不到 USB_DP / USB_DN 走線(只找到 {sorted(out)})")
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    tracks = usb_tracks(PCB.read_text(encoding="utf-8"))
    widths = set().union(*(t["widths"] for t in tracks.values()))
    if len(widths) != 1:
        raise SystemExit(f"USB 走線寬度不一致:{sorted(widths)},本腳本只處理單一線寬")
    w = widths.pop()

    r = f.impedance(f.gcpw(w, GAP, H, T, ER, d=D, box=3))
    v = 299_792_458.0 / math.sqrt(r["eps_eff"])
    longest = max(t["len"] for t in tracks.values())
    tpd = longest * 1e-3 / v
    limit = T_RISE_FS / 6
    ok = tpd <= limit

    lines = [
        f"USB 走線:線寬 {w} mm,GND 間隙 {GAP} mm,介質 {H} mm / εr {ER},銅厚 {T * 1000:.0f} µm",
        *(f"  {n}: 長 {t['len']:.1f} mm" for n, t in sorted(tracks.items())),
        f"單端 Z0 ≈ {r['Z0']:.1f} Ω(格距 {D} mm,外推會再高約 0.3 Ω),ε_eff {r['eps_eff']:.2f}",
        f"未耦合時 Z_diff ≈ 2·Z0 = {2 * r['Z0']:.0f} Ω(USB 規格 90 Ω)",
        f"最長 {longest:.1f} mm → t_pd = {tpd * 1e12:.0f} ps;FS 判據 t_r/6 = {limit * 1e12:.0f} ps"
        f" → {'PASS:電氣短,不需阻抗控制' if ok else 'FAIL:要做 90 Ω 差分'}",
        f"(換成 USB HS,t_r 500 ps → 判據 {500 / 6:.0f} ps,這段走線就必須做阻抗控制)",
    ]
    report = "\n".join(lines)
    print(report)
    (HERE / "usb_trace.txt").write_text(report + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
