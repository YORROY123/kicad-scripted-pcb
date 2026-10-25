"""CM5 載板的差分線寬與間距:JLCPCB 4 層 JLC04161H-3313 疊構上,多寬多近才是 90 / 100 Ω。

    <anaconda python> boards/cm5/sim/diff_impedance.py     (要 numpy + scipy;約 12 分鐘)

目標(Raspberry Pi CM5 規格書 §2.2–2.5):
  - 90 Ω 差分:PCIe Gen 2、USB 3.0、USB 2.0
  - 100 Ω 差分:HDMI、乙太網路 MDI

疊構(jlcpcb.com/impedance,2026-10-26 讀取):JLC04161H-3313,1.6 mm,外層銅 1 oz。
  L1 銅 0.035 mm / 預浸料 3313×1 0.0994 mm(εr 4.1)/ L2 銅 0.0152 mm / 核心 1.265 mm …
差分線走外層 L1(或 L4),參考相鄰的 L2(或 L3)整片地。所以剖面是差分微帶線:
介質厚 h = 0.0994、銅厚 t = 0.035、εr = 4.1,同層沒有地銅。

場解器 lib/field2d.py(驗證見 lib/field2d_check.py)。先在單一格距上二分搜尋線寬
(只試 0.005 mm 的倍數:製作上有意義的最小單位,也讓格點對齊),再用三個格距
外推到格距 → 0 當最終值。

沒建模的(都讓實際阻抗偏低,所以結果以「略高於目標」為準):
  - 防焊漆(JLC 參數:線上 0.6 mil、線間 1.2 mil、εr 3.8),外層微帶線通常再低 1–3 Ω
  - 蝕刻後線頂比線底窄 0.7 mil(梯形),這一項反而讓阻抗略高
最後下單前要用 JLC 自己的阻抗計算器(它有建模防焊與梯形)對一次,並下單選阻抗控制。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import field2d as f  # noqa: E402

H, T, ER = 0.0994, 0.035, 4.1    # L1–L2:3313 預浸料 + 1 oz 外層銅
# 求解器要求導體邊緣落在格點上,0.0994 不是 0.005 的倍數 → 在兩個落在格點上的厚度各解一次,
# 再線性內插到 H(兩端只差 5 µm,印出來的兩端值可以看出內插量)。
H_GRID = (0.095, 0.100)
BOX = 10.0                        # 求解盒離走線 10h(≈1 mm);下面會檢查 10h 與 20h 的差
D_SCAN = 0.005                    # 二分搜尋用的格距
D_FINAL = (0.005, 0.0025, 0.00125)
STEP = 0.005                      # 線寬、間距取到 0.005 mm
JLC_MIN = 0.09                    # JLCPCB 4 層板最小線寬 / 線距(mm)

# (名稱, 目標 Ω, 間距 s mm)。間距取 ≥ 線寬左右(鬆耦合,阻抗對間距誤差較不敏感),
# 而且 ≥ 0.1 mm 留良率餘量。
PAIRS = [
    ("PCIe / USB3 / USB2", 90.0, 0.15),
    ("PCIe / USB3 / USB2(較緊)", 90.0, 0.13),
    ("HDMI / Ethernet", 100.0, 0.20),
    ("HDMI / Ethernet(較緊)", 100.0, 0.15),
]
# 同層地銅要離差分線多遠,阻抗才不被拉低 > 2%
POUR_GAPS = (0.15, 0.25, 0.4, 0.6)


def _cs(w, s, h, d, gap, box):
    gw = 0 if gap is None else None
    return f.diff_gcpw(w, s, gap or 0.0, h, T, ER, gnd_width=gw, d=d, box=box)


def _interp(z):
    (h0, h1), (z0, z1) = H_GRID, z
    return z0 + (z1 - z0) * (H - h0) / (h1 - h0)


def zdiff(w: float, s: float, d: float, gap: float | None = None, box: float = BOX) -> float:
    return _interp([f.impedance(_cs(w, s, h, d, gap, box), "odd")["Z_diff"] for h in H_GRID])


def converged(w: float, s: float, gap: float | None = None) -> tuple[float, float, float]:
    """回傳 (內插到 H 的值, h = 0.095 的值, h = 0.100 的值),都已外推到格距 → 0。"""
    z = [f.converged(lambda d, h=h: _cs(w, s, h, d, gap, BOX), D_FINAL, "odd")["Z_diff"]
         for h in H_GRID]
    return _interp(z), z[0], z[1]


def solve_width(target: float, s: float) -> float:
    """在 STEP 的整數倍上二分:線越寬阻抗越低。回傳阻抗最接近目標的線寬。"""
    lo, hi = round(JLC_MIN / STEP), round(0.4 / STEP)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if zdiff(mid * STEP, s, D_SCAN) > target:
            lo = mid
        else:
            hi = mid
    return min((lo * STEP, hi * STEP), key=lambda w: abs(zdiff(w, s, D_SCAN) - target))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"疊構 JLC04161H-3313:h = {H} mm、t = {T} mm、εr = {ER};差分微帶線,參考 L2 地")
    z10, z20 = zdiff(0.15, 0.15, D_SCAN), zdiff(0.15, 0.15, D_SCAN, box=20.0)
    print(f"求解盒 10h 對 20h:{z10:.3f} 對 {z20:.3f} Ω(差 {abs(z10 - z20) / z20:.2%})\n")

    print(f"{'用途':<26}{'目標':>6}{'線寬 w':>9}{'間距 s':>9}{'Z_diff':>9}{'誤差':>8}"
          f"   (h=0.095 / 0.100)")
    rows, ok = [], True
    for name, target, s in PAIRS:
        w = solve_width(target, s)
        z, za, zb = converged(w, s)
        err = (z - target) / target
        good = w >= JLC_MIN and abs(err) <= 0.03
        ok &= good
        rows.append((name, target, w, s, z))
        print(f"{name:<26}{target:>6.0f}{w:>9.3f}{s:>9.3f}{z:>9.2f}{err:>+8.1%}   ({za:.2f} / {zb:.2f}){'' if good else '  ✗'}")

    print("\n同層地銅(鋪銅)離差分線的間隙 g → 阻抗(第一組幾何)")
    name, target, w, s, z_free = rows[0]
    for g in POUR_GAPS:
        z = converged(w, s, gap=g)[0]
        print(f"  g = {g:.2f} mm:{z:6.2f} Ω({(z - z_free) / z_free:+.1%})")
    print("\n判據:每組誤差 ≤ ±3%、線寬與間距 ≥ JLC 最小 0.09 mm。")
    print("全部通過" if ok else "有幾何不合格(✗)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
