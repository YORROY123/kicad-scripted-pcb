"""field2d 的驗證:對三個獨立的封閉公式,任一項超出容差就回傳 1。

    python lib/field2d_check.py      (要 numpy + scipy;約 15 分鐘,最細格距那幾項最慢)

容差 1%:封閉公式本身約 0.2–1%,外推剩下的格距誤差約 0.3%,盒子大小約 0.15%。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field2d as f  # noqa: E402

TOL = 1.0  # %
DS = (0.02, 0.01, 0.005)


def check(name: str, got: float, ref: float, tol: float = TOL) -> bool:
    err = 100 * (got / ref - 1)
    ok = abs(err) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name:46s} FD {got:7.2f}  參考 {ref:7.2f}  {err:+.2f}%")
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    # 1. 零厚度微帶線 vs Hammerstad-Jensen(< 0.2%)
    for w, h, er in ((0.2, 0.2, 4.5), (1.0, 0.2, 4.5), (0.4, 0.2, 1.0)):
        z = f.converged(lambda d: f.microstrip(w, h, 0.0, er, d=d, box=20), DS)["Z0"]
        ok &= check(f"微帶線 t=0 w={w} h={h} er={er} vs HJ", z, f.hammerstad_microstrip(w, h, er))
    # 2. 有厚度的微帶線 vs HJ 厚度修正
    for w in (0.2, 1.0):
        z = f.converged(lambda d: f.microstrip(w, 0.2, 0.04, 4.5, d=d, box=20), (0.01, 0.005, 0.0025))["Z0"]
        ok &= check(f"微帶線 t=0.04 w={w} h=0.2 vs HJ(含厚度)", z, f.hammerstad_microstrip(w, 0.2, 4.5, 0.04))
    # 3. 零厚度 GCPW vs Wadell
    for w, g, h in ((0.3, 0.15, 0.2), (0.5, 0.1, 0.2)):
        z = f.converged(lambda d: f.gcpw(w, g, h, 0.0, 4.5, d=d, box=20), DS[1:] + (0.0025,))["Z0"]
        ok &= check(f"GCPW t=0 w={w} g={g} h={h} vs Wadell", z, f.wadell_gcpw(w, g, h, 4.5))
    # 4. 差分對拉開 → Z_diff → 2·Z0
    z0 = f.converged(lambda d: f.microstrip(0.4, 0.2, 0.0, 4.5, d=d, box=20), DS)["Z0"]
    zd = f.converged(lambda d: f.diff_gcpw(0.4, 3.0, 0, 0.2, 0.0, 4.5, gnd_width=0, d=d, box=20),
                     DS, "odd")["Z_diff"]
    ok &= check("差分微帶 s=3.0(弱耦合)vs 2·Z0", zd, 2 * z0, 0.5)
    print("全部通過" if ok else "有項目未通過")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
