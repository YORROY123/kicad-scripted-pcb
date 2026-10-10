"""relay8 VBUS 軟啟動模擬:AO3401A 串在 VBUS 與 D5(SS34)之間。

    python boards/relay8/sim/softstart_sim.py

只插 USB(沒接市電)時,VBUS 經 D5 → 5V_SYS(C1 1µF)→ LP38693 → +3V3(C2 10µF、C3 100nF、
模組內部約 12.3µF)。直接接的話 LDO 用限流對後端電容充電,注入電荷超過 USB 2.0 的 50µC
(lib/review.py 的 vbus-cap)。

電路與 esp32c3 相同(Q1 AO3401A、R9 100k、C6 100nF 閘-源、C7 10nF 閘-汲、C8 1µF 在 VBUS 側),
差別只在 MOSFET 汲極(VSW)與 LDO 之間多一顆 SS34,而且 VSW 本身沒有電容。
判據、模型、線纜與 Vth 範圍全部沿用 boards/esp32c3/sim/softstart_sim.py。

接市電時 5V_PS 經 D4 供 5V_SYS:D5 反偏,Q1 的本體二極體(陽極在 VSW)也被 D5 擋住,
5V 不會倒灌進電腦的 USB 口 —— 與加軟啟動前相同。
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "esp32c3" / "sim"))
sys.path.insert(0, str(HERE.parents[1] / "usbc-ldo" / "sim"))
from power_sim import NgSpice  # noqa: E402
from softstart_sim import I_RAMP, LDO_ABS, Q_LIMIT, VGS_ABS, charge, reference, softstart  # noqa: E402

CHOSEN = ("100k", "100n", "10n")


def main() -> int:
    ng = NgSpice()
    cables = ((0.2, 1e-6), (0.1, 0.5e-6))
    ref_peak = {}
    print("== 基準:VBUS 直接掛 10µF ∥ 44Ω(USB 2.0 上限負載)==")
    for r, l in cables:
        ng.load(reference(r, l))
        d = ng.run("tran 10n 400u", ["i(vbus)"])
        t, i = d[:, 0], -d[:, 1]
        ref_peak[r] = i.max()
        print(f"  線纜 R={r}Ω L={l*1e6:.1f}µH:峰值 {i.max():.2f} A,200µs 電荷 {charge(t, i)*1e6:.1f} µC")

    rg, cgs, cgd = CHOSEN
    bad = []
    print(f"\n== 軟啟動 + SS34(Rg={rg} Cgs={cgs} Cgd={cgd};Vth 典型 −0.9V 與兩個極端)==")
    for vto in (-0.9, -0.5, -1.3):
        for r, l in cables:
            ng.load(softstart(r, l, rg, cgs, cgd, vto, diode=True))
            d = ng.run("tran 1u 40m", ["i(vbus)", "v(vin)", "v(g)", "v(vbus)", "v(v33)"])
            t, i, vin, vg, vb, v33 = d[:, 0], -d[:, 1], d[:, 2], d[:, 3], d[:, 4], d[:, 5]
            q = charge(t, i)
            vgs = vg - vb
            up = t[np.argmax(v33 >= 3.3 * 0.98)] if (v33 >= 3.3 * 0.98).any() else np.inf
            late = t > 300e-6
            ok = (q <= Q_LIMIT and i.max() < ref_peak[r] and i[late].max() <= I_RAMP and abs(vgs).max() < VGS_ABS
                  and vin.max() < LDO_ABS and np.isfinite(up))
            tag = f"Vth={vto}V R={r}Ω"
            if not ok:
                bad.append(tag)
            print(f"  {tag}:200µs 電荷 {q*1e6:5.1f} µC,峰值 {i.max():5.2f} A"
                  f"(爬升段 {i[late].max()*1000:5.1f} mA),|Vgs| 最大 {abs(vgs).max():4.1f} V,"
                  f"LDO 輸入峰值 {vin.max():4.2f} V(穩態 {vin[-1]:4.2f} V),3V3 就緒 {up*1000:5.1f} ms"
                  f" {'OK' if ok else '未通過'}")
    if bad:
        print("\n!! 未通過:\n   " + "\n   ".join(bad))
        return 1
    print("\n全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
