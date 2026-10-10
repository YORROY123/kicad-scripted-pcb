"""ESP32-C3 板 VBUS 軟啟動模擬:P-MOSFET(AO3401A)串在 VBUS 與 LDO 之間。

    python boards/esp32c3/sim/softstart_sim.py

問題(sim/power_sim.py):模組內部約 12.3µF + 板上 C2 10µF 直接掛在 LDO 後面,
插入瞬間灌進約 79µC,超過 USB 2.0 的 50µC。

USB 2.0 §7.2.4.1:設備在 VBUS 上的負載上限是 10µF ∥ 44Ω;電容更多時,
設備必須自帶浪湧限流,讓它的表現「與上述負載相當」。所以判據有兩條:
  1. 插入後 200µs 內注入的電荷 ≤ 50µC(= 10µF × 5V,與 power_sim.py 同一個窗)
  2. 峰值電流不超過「VBUS 直接掛 10µF ∥ 44Ω」這個規範上限負載的峰值
  3. 線纜振鈴之後的爬升段電流 ≤ 100mA(一個 USB 單位負載;10µF ∥ 44Ω 穩態是 114mA)。
     光看 200µs 電荷不夠:軟啟動只是把電荷延後灌進去,爬升電流才看得出有沒有真的限流
並檢查:MOSFET 的 Vgs 不超過 ±12V、LDO 輸入不超過 12V、3V3 能起來。

電路:
  VBUS ─┬─ C1 1µF(留在 VBUS 側,給 ESD 與線纜一個本地電容)
        └─ S  AO3401A  D ─┬─ C5 1µF ─ LDO(LP38693)─ 3V3(C2 10µF、C3 100nF、模組約 12.3µF)
              G           │
              ├─ Cgs ─ S  │   插入瞬間把閘極「綁」在源極上,MOSFET 先保持關閉
              ├─ Cgd ─────┘   米勒電容:輸出爬升斜率 ≈ (閘極拉電流) / Cgd
              └─ Rg ─ GND     慢慢把閘極拉低,MOSFET 逐漸導通

AO3401A 模型(AOS 規格書 Rev 3.1):Vth −0.9V 典型;RDS(on) 47mΩ @ Vgs −4.5V
→ level-1 KP = 1/(0.047 × 3.6) ≈ 5.9 A/V²;Ciss 645pF、Crss 55pF → 內部
Cgs 590pF、Cgd 55pF;本體二極體陽極在汲極。只用來看趨勢與量級。
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "usbc-ldo" / "sim"))
from power_sim import MODELS, NgSpice  # noqa: E402

Q_LIMIT = 50e-6
VGS_ABS = 12.0
LDO_ABS = 12.0
I_RAMP = 0.100

FET = """
.model AO3401 PMOS(LEVEL=1 VTO={vto} KP=5.9 LAMBDA=0.01)
.model DBODY D(IS=1e-12 N=1.05 RS=0.02)
"""

# 靜態電流只在輸入有電時才抽:MOSFET 關著時 vsw 這個節點沒有任何來源,
# 定電流源會把 C5 一路抽到負幾千萬伏(第一版就這樣發散)。
LDO = """
Bldo vsw vo_i I = min(0.85, max(0, (min(3.3, V(vsw) - 0.1) - V(v33)) * 100))
Vsns vo_i v33 0
Bgnd vsw 0 I = 55u * min(1, max(0, V(vsw)))
"""


def softstart(r: float, l: float, rg: str, cgs: str, cgd: str, vto: float = -0.9,
              rload: str = "1meg") -> str:
    # 負載預設不接:插入瞬間模組還沒開機(與 power_sim.py 相同理由)
    return f"""soft-start
Vbus vsrc 0 PWL(0 0 1u 5 100m 5)
Lcable vsrc vl {l}
Rcable vl vbus {r}
C1 vbus 0 1u
M1 vsw g vbus vbus AO3401 W=1 L=1
Dbody vsw vbus DBODY
Cgsi g vbus 590p
Cgdi g vsw 55p
Cgs g vbus {cgs}
Cgd g vsw {cgd}
Rg g 0 {rg}
C5 vsw 0 1u
{LDO}
C2 v33 0 10u
C3 v33 0 100n
Cmod v33 0 12.3u
Rload v33 0 {rload}
{MODELS}
{FET.format(vto=vto)}
.end
"""


def reference(r: float, l: float) -> str:
    """USB 2.0 允許的最大負載:VBUS 直接掛 10µF ∥ 44Ω。"""
    return f"""usb reference load
Vbus vsrc 0 PWL(0 0 1u 5 100m 5)
Lcable vsrc vl {l}
Rcable vl vbus {r}
Cref vbus 0 10u
Rref vbus 0 44
.end
"""


def charge(t, i, window=200e-6):
    m = t <= window
    return np.trapezoid(i[m], t[m])


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

    bad = []
    print("\n== 軟啟動(Rg / Cgs / Cgd;Vth 典型 −0.9V 與兩個極端)==")
    # 第一組是板上採用的值,必須全過;後兩組只列出來說明為什麼不選(爬升電流超過 100mA)
    chosen = ("100k", "100n", "10n")
    for rg, cgs, cgd in (chosen, ("100k", "47n", "4.7n"), ("47k", "100n", "10n")):
        for vto in (-0.9, -0.5, -1.3):
            for r, l in cables:
                ng.load(softstart(r, l, rg, cgs, cgd, vto))
                d = ng.run("tran 1u 40m", ["i(vbus)", "v(vsw)", "v(g)", "v(vbus)", "v(v33)"])
                t, i, vsw, vg, vb, v33 = d[:, 0], -d[:, 1], d[:, 2], d[:, 3], d[:, 4], d[:, 5]
                q = charge(t, i)
                vgs = vg - vb
                up = t[np.argmax(v33 >= 3.3 * 0.98)] if (v33 >= 3.3 * 0.98).any() else np.inf
                late = t > 300e-6                 # 線纜振鈴之後的爬升段
                ok = (q <= Q_LIMIT and i.max() < ref_peak[r] and i[late].max() <= I_RAMP and abs(vgs).max() < VGS_ABS
                      and vsw.max() < LDO_ABS and np.isfinite(up))
                tag = f"Rg={rg} Cgs={cgs} Cgd={cgd} Vth={vto}V R={r}Ω"
                if not ok and (rg, cgs, cgd) == chosen:
                    bad.append(tag)
                print(f"  {tag}:200µs 電荷 {q*1e6:5.1f} µC,峰值 {i.max():5.2f} A"
                      f"(爬升段 {i[late].max()*1000:5.1f} mA),|Vgs| 最大 {abs(vgs).max():4.1f} V,"
                      f"LDO 輸入峰值 {vsw.max():4.2f} V,3V3 就緒 {up*1000:5.1f} ms"
                      f" {'OK' if ok else '未通過'}")
    if bad:
        print("\n!! 未通過:\n   " + "\n   ".join(bad))
        return 1
    print("\n全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
