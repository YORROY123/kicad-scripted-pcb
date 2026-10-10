"""二維準靜態電場求解器:算 PCB 走線剖面的特性阻抗(單端 / 差分)。

為什麼自己寫:高速走線要知道「多寬、多近」才是 90Ω / 100Ω。公式只涵蓋
標準形狀(微帶線、帶狀線),而 2 層板上真正用的是「旁邊有地銅的差分對」
(差分 GCPW),沒有好用的封閉公式。

原理(準 TEM):在剖面上解拉普拉斯方程 ∇·(ε∇V) = 0,
  - 導體是固定電位的格點(走線、底層地、同層地銅)
  - 由電場能量求單位長度電容 C:W = ½ΣCV² = ½∫ε|E|²dA
  - 同一幾何把介電常數換成 1 再解一次得 C₀(空氣)
  - Z = 1 / (c·√(C·C₀)),ε_eff = C / C₀
差分(奇模):兩條線 +1V / −1V,Z_odd 是單條線對地的阻抗,Z_diff = 2·Z_odd。

離散:電位在格點,ε 在格子中心;相鄰兩格點之間的耦合 = 兩側格子 ε 的平均 × (dy/dx)。
能量用同一套耦合加總,與解出來的線性系統完全一致。

限制(誠實列出):
  - 準靜態,不含頻率相依的損耗與色散(USB 2.0 / PCIe Gen2 等級夠用)
  - 防焊漆沒建模(實際會讓阻抗低約 1–3Ω)
  - 外框是接地的盒子,盒子要夠大(預設各方向 ≥ 5 倍介質厚度)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

EPS0 = 8.8541878128e-12
C0 = 299_792_458.0


@dataclass
class Rect:
    """導體矩形,座標 mm。y = 0 是底層地平面上緣。"""
    x0: float
    x1: float
    y0: float
    y1: float
    volt: float


@dataclass
class CrossSection:
    h: float                   # 介質厚度(mm)
    er: float                  # 介質相對介電常數
    width: float               # 求解區寬度(mm)
    height: float              # 求解區高度(mm,含介質上方的空氣)
    conductors: list[Rect] = field(default_factory=list)
    d: float = 0.01            # 格距(mm)


def _solve(cs: CrossSection, er: float) -> float:
    """回傳 ½∫ε|E|²dA(單位 F/m,已乘 ε₀),即 W 對應的電容量。"""
    d = cs.d
    # 格點以 x = 0、y = 0 為原點(xs = k·d),導體邊緣必須剛好落在格點上;
    # 否則導體實際寬度會隨格距變動(第一版就是這樣:d = 0.04 時 0.3 mm 線只剩 0.24 mm)。
    half_n = int(round(cs.width / 2 / d))
    nx = 2 * half_n + 1
    ny = int(round(cs.height / d)) + 1
    xs = (np.arange(nx) - half_n) * d
    ys = np.arange(ny) * d
    for r in cs.conductors:
        for name, v in (("x0", r.x0), ("x1", r.x1), ("y0", r.y0), ("y1", r.y1)):
            if abs(v / d - round(v / d)) > 1e-6 and abs(v) < cs.width / 2 - 1e-9:
                raise ValueError(f"導體 {name}={v} mm 不在格點上(格距 {d} mm),換一個能整除的格距")
    if abs(cs.h / d - round(cs.h / d)) > 1e-6:
        raise ValueError(f"介質厚度 {cs.h} mm 不在格點上(格距 {d} mm)")

    # 格子中心的 ε:介質在 y < h
    yc = (ys[:-1] + ys[1:]) / 2
    eps_cell = np.where(yc < cs.h, er, 1.0)[:, None] * np.ones((1, nx - 1))   # (ny-1, nx-1)

    # 固定電位:外框 0V(底邊就是地平面),再疊上導體
    fixed = np.zeros((ny, nx), bool)
    volt = np.zeros((ny, nx))
    fixed[0, :] = fixed[-1, :] = True
    fixed[:, 0] = fixed[:, -1] = True
    for r in cs.conductors:
        ix = (xs >= r.x0 - 1e-9) & (xs <= r.x1 + 1e-9)
        iy = (ys >= r.y0 - 1e-9) & (ys <= r.y1 + 1e-9)
        m = iy[:, None] & ix[None, :]
        if not m.any():
            raise ValueError(f"導體 {r} 比格距還小,沒有落到任何格點")
        fixed |= m
        volt[m] = r.volt

    # 邊耦合(dx = dy,幾何因子為 1):水平邊用上下兩格的 ε 平均,垂直邊用左右兩格
    eps_pad = np.pad(eps_cell, ((1, 1), (1, 1)), mode="edge")       # (ny+1, nx+1)
    gx = (eps_pad[:-1, 1:-1] + eps_pad[1:, 1:-1]) / 2               # 邊 (j, i)-(j, i+1):(ny, nx-1)
    gy = (eps_pad[1:-1, :-1] + eps_pad[1:-1, 1:]) / 2               # 邊 (j, i)-(j+1, i):(ny-1, nx)

    idx = -np.ones((ny, nx), int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    n = int(free.sum())
    rows, cols, vals = [], [], []
    rhs = np.zeros(n)
    diag = np.zeros(n)

    def couple(a_j, a_i, b_j, b_i, g):
        """把一組邊(陣列)加進矩陣:a、b 兩端,耦合 g。"""
        ia, ib = idx[a_j, a_i], idx[b_j, b_i]
        for p, q, vq in ((ia, ib, volt[b_j, b_i]), (ib, ia, volt[a_j, a_i])):
            sel = p >= 0
            np.add.at(diag, p[sel], g[sel])
            both = sel & (q >= 0)
            rows.append(p[both]); cols.append(q[both]); vals.append(-g[both])
            fixed_q = sel & (q < 0)
            np.add.at(rhs, p[fixed_q], g[fixed_q] * vq[fixed_q])

    J, I = np.mgrid[0:ny, 0:nx - 1]
    couple(J.ravel(), I.ravel(), J.ravel(), I.ravel() + 1, gx.ravel())
    J, I = np.mgrid[0:ny - 1, 0:nx]
    couple(J.ravel(), I.ravel(), J.ravel() + 1, I.ravel(), gy.ravel())

    A = sp.csr_matrix((np.concatenate(vals + [diag]),
                       (np.concatenate(rows + [np.arange(n)]), np.concatenate(cols + [np.arange(n)]))),
                      shape=(n, n))
    v = volt.copy()
    v[free] = spla.spsolve(A.tocsc(), rhs)

    # ½ΣCV² 等於 ½Σ g·ΔV²(同一套離散,能量與解一致)
    w = 0.5 * (np.sum(gx * np.diff(v, axis=1) ** 2) + np.sum(gy * np.diff(v, axis=0) ** 2))
    return w * EPS0


def impedance(cs: CrossSection, mode: str = "single") -> dict:
    """mode="single":一條線 1V,其他導體 0V;"odd":兩條線 ±1V(差分)。

    回傳 Z(單端)或 Z_diff、以及 ε_eff。
    """
    w = _solve(cs, cs.er)
    w0 = _solve(cs, 1.0)
    # 單端:W = ½CV² → C = 2W;奇模:W = ½(C·1² + C·1²) → C_odd = W
    k = 2.0 if mode == "single" else 1.0
    c, c0 = k * w, k * w0
    z = 1.0 / (C0 * np.sqrt(c * c0))
    out = {"eps_eff": c / c0}
    if mode == "single":
        out["Z0"] = z
    else:
        out["Z_odd"] = z
        out["Z_diff"] = 2 * z
    return out


def converged(build, ds: tuple[float, float, float], mode: str = "single") -> dict:
    """用三個格距(由粗到細,逐次減半)解同一個幾何,Richardson 外推到格距 → 0。

    build(d) 回傳 CrossSection。實測收斂階 p ≈ 1(導體邊緣的奇異性);
    p 偏離 0.7–1.5 表示還沒進入漸近區,外推不可信 → 拋錯。
    """
    key = "Z0" if mode == "single" else "Z_diff"
    rs = [impedance(build(d), mode) for d in ds]
    z = [r[key] for r in rs]
    p = np.log((z[1] - z[0]) / (z[2] - z[1])) / np.log(2)
    if not 0.7 <= p <= 1.5:
        raise RuntimeError(f"格距收斂階 p = {p:.2f},不在 0.7–1.5:{z},格子太粗")
    zinf = z[2] + (z[2] - z[1]) / (2 ** p - 1)
    return {key: zinf, "eps_eff": rs[2]["eps_eff"], "order": p, "raw": z}


# ── 幾何產生器 ──────────────────────────────────────────────────────────
def microstrip(w: float, h: float, t: float, er: float, d: float = 0.01,
               box: float = 10.0) -> CrossSection:
    """box:接地外框離走線的距離,以介質厚度 h 的倍數計(左右與上方都是)。"""
    span = 2 * box * h + w
    return CrossSection(h, er, span, h + t + box * h, [Rect(-w / 2, w / 2, h, h + t, 1.0)], d)


def gcpw(w: float, g: float, h: float, t: float, er: float, d: float = 0.01,
         box: float = 4.0) -> CrossSection:
    """單端接地共面波導:寬 w 的線,左右隔 g 是延伸到邊界的同層地銅,底下是地平面。

    同層地銅把場鎖在間隙裡,盒子 3h 與 4h 只差 0.03%(h = 1.6、g = 0.3 實測)。
    """
    span = w + 2 * g + 2 * box * h
    half = span / 2
    return CrossSection(h, er, span, h + t + box * h, [
        Rect(-w / 2, w / 2, h, h + t, 1.0),
        Rect(w / 2 + g, half, h, h + t, 0.0), Rect(-half, -w / 2 - g, h, h + t, 0.0)], d)


def diff_gcpw(w: float, s: float, g: float, h: float, t: float, er: float,
              gnd_width: float | None = None, d: float = 0.01,
              box: float = 10.0) -> CrossSection:
    """兩條寬 w、間距 s 的差分線,左右各隔 g 有同層地銅;底下是地平面。

    gnd_width=None 表示同層地銅一路延伸到求解區邊緣;設 0 等於沒有同層地(差分微帶線)。
    """
    span = 2 * w + s + 2 * g + 2 * box * h
    half = span / 2
    xp = s / 2
    cond = [Rect(xp, xp + w, h, h + t, 1.0), Rect(-xp - w, -xp, h, h + t, -1.0)]
    if gnd_width is None or gnd_width > 0:
        edge = xp + w + g
        far = half if gnd_width is None else min(half, edge + gnd_width)
        cond += [Rect(edge, far, h, h + t, 0.0), Rect(-far, -edge, h, h + t, 0.0)]
    return CrossSection(h, er, span, h + t + box * h, cond, d)


# ── 驗證用的封閉公式 ────────────────────────────────────────────────────
def _hj_z01(u: float) -> float:
    f = 6 + (2 * np.pi - 6) * np.exp(-((30.666 / u) ** 0.7528))
    return 60 * np.log(f / u + np.sqrt(1 + (2 / u) ** 2))


def _hj_eeff(u: float, er: float) -> float:
    a = 1 + np.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + np.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    return (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)


def hammerstad_microstrip(w: float, h: float, er: float, t: float = 0.0) -> float:
    """Hammerstad & Jensen(1980)微帶線,誤差 < 0.2%(0.01 ≤ w/h ≤ 100);t > 0 時含厚度修正。"""
    u = w / h
    if t <= 0:
        return _hj_z01(u) / np.sqrt(_hj_eeff(u, er))
    tn = t / h
    du1 = tn / np.pi * np.log(1 + 4 * np.e / (tn / np.tanh(np.sqrt(6.517 * u)) ** 2))  # t·coth²(√6.517u)
    dur = 0.5 * (1 + 1 / np.cosh(np.sqrt(er - 1))) * du1
    u1, ur = u + du1, u + dur
    eeff = _hj_eeff(ur, er) * (_hj_z01(u1) / _hj_z01(ur)) ** 2
    # Z = Z01(u1)/√εeff ≡ Z01(ur)/√εeff(ur)(兩種寫法等價;拿 Z01(ur) 配修正後的 εeff 會偏高約 3%)
    return _hj_z01(u1) / np.sqrt(eeff)


def wadell_gcpw(w: float, g: float, h: float, er: float) -> float:
    """Wadell《Transmission Line Design Handbook》2.4.3,零厚度接地共面波導(保角映射)。"""
    from scipy.special import ellipk

    def kr(k):  # K(k)/K(k'),scipy 的 ellipk 吃 m = k²
        return ellipk(k * k) / ellipk(1 - k * k)

    k = w / (w + 2 * g)
    k3 = np.tanh(np.pi * w / (4 * h)) / np.tanh(np.pi * (w + 2 * g) / (4 * h))
    q = kr(k3) / kr(k)
    eeff = (1 + er * q) / (1 + q)
    return 60 * np.pi / np.sqrt(eeff) / (kr(k) + kr(k3))
