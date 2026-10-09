"""电源路径模拟:USB VBUS → SS34 → +5V → AMS1117-3.3 → +3V3 → R3 + LED。

直接用 KiCad 自带的 ngspice.dll(ctypes 调共享库 API),不另装模拟器:

    python sim/power_sim.py

回答设计备注里悬而未决的三个问题:
  1. 负载多大时 3V3 掉出稳压?(VBUS 取 USB 规范的 5.25 / 5.0 / 4.75 / 4.40V)
  2. LED 实际电流多少?
  3. 插入瞬间的浪涌电流 —— USB 2.0 规定设备在 VBUS 上的电容 ≤10µF,
     本板 C2 + C1 在 VBUS 侧、C3 经 LDO 也挂在后面。

模型都是按规格书典型值搭的行为模型,不是厂商 SPICE 模型;数字用来看趋势与
量级,判断要不要改设计,不能当量产保证值。各模型的出处写在 MODELS 旁。
"""
import ctypes
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from kicad_paths import kicad_bin  # noqa: E402

KICAD_BIN = kicad_bin()

# ── 模型 ────────────────────────────────────────────────────────────────
MODELS = """
* SS34(MDD,3A/40V 肖特基):规格书 VF ≤0.5V @3A。常见通用参数,
* 推算 VF ≈0.31V @0.1A、≈0.39V @0.5A。
.model SS34 D(IS=1.4e-5 RS=0.038 N=1.036 CJO=250p M=0.5 BV=40 IBV=5e-4)
* KT-0805Y(黄光 AlGaInP):规格书 VF 典型 2.0V @20mA。用 N=2、RS=10Ω 拟合,
* 小电流时 VF ≈1.8V。
.model LEDY D(IS=1.5e-17 N=2 RS=10)
"""

# AMS1117-3.3:规格书压差 1.1V 典型 / 1.3V 最大 @800mA、静态电流约 5mA、
# 限流约 1.1A(典型)。两套行为模型,各管一种分析:
#
# DC(负载扫描):受控电压源 Vout = min(3.3, Vin − Vdo(I)),Vdo 随电流从 0.95V
#   线性升到 1.1V;输入侧另用电流源从 +5V 抽走同样的电流 + 静态电流。负载只扫到
#   0.8A,碰不到限流,所以这里不建模限流。
# 暂态(插入浪涌):从 +5V 抽电流、推向 min(3.3, Vin − 1.0) 的限流跨导级。压差取常数,
#   不引用自身电流 —— 引用的版本在 DC 工作点上 gmin / source stepping 全部失败,
#   退回暂态 op 得到一个 C3 还在充电的假解(3V3 = 1.47V),实测踩过。
LDO_DC = """
Bldo vo_i 0 V = min(3.3, max(0, V(v5) - ({vdo0} + {kdo}*I(Vsns))))
Vsns vo_i v33 0
Bin v5 0 I = max(I(Vsns), 0) + 5m
"""
LDO_TRAN = """
Bldo v5 vo_i I = min(1.1, max(0, (min(3.3, V(v5) - 1.0) - V(v33)) * 100))
Vsns vo_i v33 0
Ignd v5 0 5m
"""


def ldo(worst: bool) -> str:
    # 最坏情况:压差整体多 0.2V(对应规格书的 1.3V 最大值)
    return LDO_DC.format(vdo0=1.15 if worst else 0.95, kdo=0.1875)


def dc_circuit(vbus: float, r_cable: float, worst: bool) -> str:
    return f"""power path DC
Vbus vsrc 0 DC {vbus}
Rcable vsrc vbus {r_cable}
D1 vbus v5 SS34
C2 v5 0 10u
C1 v5 0 100n
{ldo(worst)}
C3 v33 0 22u
R3 v33 led_a 1k
DL led_a 0 LEDY
Iload v33 0 DC 0
{MODELS}
.end
"""


def inrush_circuit(r_cable: float, l_cable: float) -> str:
    # 插入:VBUS 从 0 在 1µs 内升到 5V(机械接触的典型边沿),线缆以 R + L 表示
    return f"""power path inrush
Vbus vsrc 0 PWL(0 0 1u 5 10m 5)
Lcable vsrc vl {l_cable}
Rcable vl vbus {r_cable}
D1 vbus v5 SS34
C2 v5 0 10u
C1 v5 0 100n
{LDO_TRAN}
C3 v33 0 22u
R3 v33 led_a 1k
DL led_a 0 LEDY
{MODELS}
.end
"""


# ── ngspice 共享库 ──────────────────────────────────────────────────────
class NgSpice:
    def __init__(self):
        os.add_dll_directory(str(KICAD_BIN))
        self.lib = ctypes.CDLL(str(KICAD_BIN / "ngspice.dll"))
        self.out = []
        cb_str = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
        cb_exit = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool,
                                   ctypes.c_int, ctypes.c_void_p)
        self._printf = cb_str(lambda s, i, u: self.out.append(s.decode(errors="replace")) or 0)
        self._stat = cb_str(lambda s, i, u: 0)
        self._exit = cb_exit(lambda *a: 0)
        self.lib.ngSpice_Init(self._printf, self._stat, self._exit, None, None, None, None)

    def cmd(self, c: str) -> None:
        self.lib.ngSpice_Command(c.encode())

    def load(self, netlist: str) -> None:
        self.cmd("destroy all")
        self.cmd("remcirc")
        lines = [l for l in netlist.strip().splitlines()]
        arr = (ctypes.c_char_p * (len(lines) + 1))(*[l.encode() for l in lines], None)
        self.lib.ngSpice_Circ(arr)

    def run(self, analysis: str, vectors: list[str]) -> np.ndarray:
        self.out.clear()
        self.cmd(analysis)
        # 工作点不收敛时 ngspice 会退回「暂态 op」并照样给出数字 —— 那是假解,当错误处理
        errs = [l for l in self.out
                if re.search(r"error|singular|abort|source stepping failed", l, re.I)]
        if errs:
            raise RuntimeError("\n".join(errs))
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        self.cmd(f"wrdata {path.replace(chr(92), '/')} {' '.join(vectors)}")
        data = np.loadtxt(path)
        os.unlink(path)
        # wrdata 每个向量写一对 (扫描量, 值);只保留第一列扫描量 + 各向量值
        return np.column_stack([data[:, 0]] + [data[:, 2 * i + 1] for i in range(len(vectors))])


# ── 分析 ────────────────────────────────────────────────────────────────
def load_sweep(ng: NgSpice, vbus: float, worst: bool, r_cable: float = 0.2):
    ng.load(dc_circuit(vbus, r_cable, worst))
    # ngspice 内部把元件名转成小写,命令里也得写小写
    d = ng.run("dc iload 0 0.8 0.005", ["v(v5)", "v(v33)", "i(vbus)"])
    iload, v5, v33 = d[:, 0], d[:, 1], d[:, 2]
    in_reg = v33 >= 3.3 * 0.98            # 规格书负载调整 ±2% 以内算稳压
    i_max = iload[in_reg].max() if in_reg.any() else 0.0
    return iload, v5, v33, i_max


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ng = NgSpice()
    print("== 1. 3V3 稳压上限(线缆 0.2Ω,±2% 判据)==")
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    results = {}
    for vbus in (5.25, 5.0, 4.75, 4.40):
        for worst in (False, True):
            il, v5, v33, imax = load_sweep(ng, vbus, worst)
            results[(vbus, worst)] = imax
            tag = "最坏压差" if worst else "典型压差"
            print(f"  VBUS={vbus:.2f}V {tag}: 稳压到 {imax*1000:5.0f} mA"
                  f"(空载 +5V={v5[0]:.2f}V, 3V3={v33[0]:.3f}V)")
            if not worst:
                ax[0].plot(il * 1000, v33, label=f"VBUS {vbus:.2f} V")
    ax[0].axhline(3.3 * 0.98, color="gray", ls="--", lw=0.8)
    ax[0].set(xlabel="3V3 load (mA)", ylabel="3V3 (V)", title="AMS1117 output vs load (typ. dropout)")
    ax[0].legend()
    ax[0].grid(alpha=0.3)

    print("\n== 2. LED 电流 ==")
    ng.load(dc_circuit(5.0, 0.2, False))
    d = ng.run("dc iload 0 0.001 0.001", ["v(led_a)", "v(v33)"])
    va, v33 = d[0, 1], d[0, 2]
    i_led = (v33 - va) / 1000
    print(f"  3V3={v33:.3f}V  LED VF={va:.3f}V  I_LED={i_led*1000:.2f} mA")

    print("\n== 3. 插入浪涌(USB 2.0:设备在 VBUS 上的电容 ≤10µF)==")
    for r, l in ((0.2, 1e-6), (0.1, 0.5e-6)):
        ng.load(inrush_circuit(r, l))
        d = ng.run("tran 10n 200u", ["i(vbus)", "v(v5)", "v(vbus)"])
        t, i, v5, vb = d[:, 0], -d[:, 1], d[:, 2], d[:, 3]
        q = np.trapezoid(i, t) if hasattr(np, "trapezoid") else np.trapz(i, t)
        print(f"  线缆 R={r}Ω L={l*1e6:.1f}µH: 峰值 {i.max():.2f} A @ {t[i.argmax()]*1e6:.1f}µs,"
              f" VBUS 过冲到 {vb.max():.2f} V,200µs 内注入电荷 {q*1e6:.1f} µC")
        if r == 0.2:
            ax[1].plot(t * 1e6, i, label="I(VBUS)")
            ax2 = ax[1].twinx()
            ax2.plot(t * 1e6, vb, color="tab:orange", lw=0.8, label="V(VBUS)")
            ax2.set_ylabel("VBUS (V)")
    ax[1].set(xlabel="time (µs)", ylabel="inrush current (A)", title="Hot-plug inrush (0.2 Ω, 1 µH cable)")
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    out = HERE / "power_sim.png"
    fig.savefig(out, dpi=110)
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    sys.exit(main())
