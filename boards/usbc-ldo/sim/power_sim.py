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
* SMAJ5.0A(单向 TVS,接在 +5V 对地):规格书 VBR 6.40–7.07V @10mA、
* VC 9.2V @43.5A。取 VBR 中值 6.7V,RS =(9.2−6.7)/43.5 ≈ 0.057Ω。
.model TVS5 D(IS=1e-12 N=1 RS=0.057 BV=6.7 IBV=10m CJO=1n)
"""

# ── 两版设计 ────────────────────────────────────────────────────────────
# v1(与 EasyEDA 那块相同):AMS1117-3.3、C2 10µF、C3 22µF。
#   规格书:压差 1.1V 典型 / 1.3V 最大 @800mA,静态电流约 5mA,限流约 1.1A。
# v2:AP2112K-3.3(Diodes)、C2 4.7µF、C3 4.7µF。
#   规格书:压差 250mV 典型 / 400mV 最大 @600mA(PMOS 导通管,压差近似正比于电流),
#   静态电流 55µA,额定 600mA,输入/输出各需 ≥1µF 陶瓷电容。
#   限流取 0.8A —— 这是假设值,没有从规格书可靠读到;它只影响浪涌峰值,
#   不影响注入电荷(电荷 = ΣC·V,由电容决定)。
#   输入绝对最大值 6.5V(AMS1117 是 15V)—— 电容变小后热插拔过冲变大,浪涌分析要查 +5V 峰值。
DESIGNS = {
    "v1": dict(label="v1 AMS1117, C2=10u C3=22u", c2="10u", c3="22u", rating=0.8, vin_abs=15.0,
               vdo0_typ=0.95, vdo0_max=1.15, kdo=0.1875, iq="5m", ilim=1.1, vdo_tran=1.0),
    "v2": dict(label="v2 AP2112K, C2=4.7u C3=4.7u", c2="4.7u", c3="4.7u", rating=0.6, vin_abs=6.5,
               vdo0_typ=0.0, vdo0_max=0.0, kdo_typ=0.25 / 0.6, kdo_max=0.40 / 0.6,
               iq="55u", ilim=0.8, vdo_tran=0.1),
    # v3:LP38693MP-3.3(TI,SOT-223-5)。規格書 SNVS321O:
    #   絕對最大 12V(所有腳對 GND)、建議輸入 2.7–10V;額定 500mA;
    #   壓差 330mV 典型 / 550mV 最大 @0.5A、25°C(全溫 725mV;定義是輸出掉 100mV);
    #   接地腳電流 55µA;折返限流:VIN−VOUT < 4V 時約 850mA;輸入輸出各 ≥1µF。
    "v3": dict(label="v3 LP38693, C2=4.7u C3=4.7u", c2="4.7u", c3="4.7u", rating=0.5,
               vin_abs=12.0, vdo0_typ=0.0, vdo0_max=0.0, kdo_typ=0.33 / 0.5,
               kdo_max=0.55 / 0.5, iq="55u", ilim=0.85, vdo_tran=0.1),
}

# LDO 行为模型,两种分析各一套:
#
# DC(负载扫描):受控电压源 Vout = min(3.3, Vin − Vdo(I)),Vdo = vdo0 + kdo·I;
#   输入侧另用电流源从 +5V 抽走同样的电流 + 静态电流。负载扫描不碰限流,不建模。
# 暂态(插入浪涌):从 +5V 抽电流、推向 min(3.3, Vin − vdo) 的限流跨导级。压差取常数,
#   不引用自身电流 —— 引用的版本在 DC 工作点上 gmin / source stepping 全部失败,
#   退回暂态 op 得到一个 C3 还在充电的假解(3V3 = 1.47V),实测踩过。
LDO_DC = """
Bldo vo_i 0 V = min(3.3, max(0, V(v5) - ({vdo0} + {kdo}*I(Vsns))))
Vsns vo_i v33 0
Bin v5 0 I = max(I(Vsns), 0) + {iq}
"""
LDO_TRAN = """
Bldo v5 vo_i I = min({ilim}, max(0, (min(3.3, V(v5) - {vdo}) - V(v33)) * 100))
Vsns vo_i v33 0
Ignd v5 0 {iq}
"""


def ldo_dc(d: dict, worst: bool) -> str:
    if "kdo" in d:      # AMS1117:最坏情况压差整体多 0.2V(对应规格书 1.3V 最大值)
        return LDO_DC.format(vdo0=d["vdo0_max" if worst else "vdo0_typ"], kdo=d["kdo"], iq=d["iq"])
    return LDO_DC.format(vdo0=0, kdo=d["kdo_max" if worst else "kdo_typ"], iq=d["iq"])


def dc_circuit(d: dict, vbus: float, r_cable: float, worst: bool) -> str:
    return f"""power path DC
Vbus vsrc 0 DC {vbus}
Rcable vsrc vbus {r_cable}
D1 vbus v5 SS34
C2 v5 0 {d['c2']}
C1 v5 0 100n
{ldo_dc(d, worst)}
C3 v33 0 {d['c3']}
R3 v33 led_a 1k
DL led_a 0 LEDY
Iload v33 0 DC 0
{MODELS}
.end
"""


def inrush_circuit(d: dict, r_cable: float, l_cable: float) -> str:
    # 插入:VBUS 从 0 在 1µs 内升到 5V(机械接触的典型边沿),线缆以 R + L 表示
    tran = LDO_TRAN.format(ilim=d["ilim"], vdo=d["vdo_tran"], iq=d["iq"])
    return f"""power path inrush
Vbus vsrc 0 PWL(0 0 1u 5 10m 5)
Lcable vsrc vl {l_cable}
Rcable vl vbus {r_cable}
D1 vbus v5 SS34
C2 v5 0 {d['c2']}
C1 v5 0 100n
D3 0 v5 TVS5
{tran}
C3 v33 0 {d['c3']}
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
Q_LIMIT = 50e-6     # USB 2.0 7.2.4.1:超过 10µF 时插入注入电荷不得超过 50µC


def load_sweep(ng: NgSpice, d: dict, vbus: float, worst: bool, r_cable: float = 0.2):
    ng.load(dc_circuit(d, vbus, r_cable, worst))
    # ngspice 内部把元件名转成小写,命令里也得写小写
    data = ng.run("dc iload 0 0.8 0.005", ["v(v5)", "v(v33)", "i(vbus)"])
    iload, v5, v33 = data[:, 0], data[:, 1], data[:, 2]
    in_reg = v33 >= 3.3 * 0.98            # 规格书负载调整 ±2% 以内算稳压
    # 只认从 0 开始连续稳压的那一段,并以器件额定电流封顶
    n = int(np.argmin(in_reg)) if not in_reg.all() else len(in_reg)
    i_max = min(iload[n - 1], d["rating"]) if n else 0.0
    return iload, v5, v33, i_max


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ng = NgSpice()
    fig, ax = plt.subplots(1, 4, figsize=(21, 4.5))
    failures = []
    for key, d in DESIGNS.items():
        print(f"######## {d['label']} ########")
        print("== 1. 3V3 稳压上限(线缆 0.2Ω,±2% 判据,以额定电流封顶)==")
        for vbus in (5.25, 5.0, 4.75, 4.40):
            for worst in (False, True):
                il, v5, v33, imax = load_sweep(ng, d, vbus, worst)
                tag = "最坏压差" if worst else "典型压差"
                print(f"  VBUS={vbus:.2f}V {tag}: 稳压到 {imax*1000:5.0f} mA"
                      f"(空载 +5V={v5[0]:.2f}V, 3V3={v33[0]:.3f}V)")
                if not worst:
                    ax[list(DESIGNS).index(key)].plot(il * 1000, v33, label=f"VBUS {vbus:.2f} V")

        print("== 2. LED 电流 ==")
        ng.load(dc_circuit(d, 5.0, 0.2, False))
        data = ng.run("dc iload 0 0.001 0.001", ["v(led_a)", "v(v33)"])
        va, v33 = data[0, 1], data[0, 2]
        print(f"  3V3={v33:.3f}V  LED VF={va:.3f}V  I_LED={(v33 - va):.2f} mA")

        print(f"== 3. 插入浪涌(USB 2.0:>10µF 时注入电荷 ≤{Q_LIMIT*1e6:.0f} µC)==")
        for r, l in ((0.2, 1e-6), (0.1, 0.5e-6)):
            ng.load(inrush_circuit(d, r, l))
            data = ng.run("tran 10n 200u", ["i(vbus)", "v(v5)", "v(vbus)"])
            t, i, v5, vb = data[:, 0], -data[:, 1], data[:, 2], data[:, 3]
            q = np.trapezoid(i, t) if hasattr(np, "trapezoid") else np.trapz(i, t)
            ok_q, ok_v = q <= Q_LIMIT, v5.max() < d["vin_abs"]
            if not ok_q:
                failures.append(f"{key} 浪涌 {q*1e6:.1f} µC @ R={r}Ω")
            if not ok_v:
                failures.append(f"{key} +5V 峰值 {v5.max():.2f} V ≥ LDO 绝对最大 {d['vin_abs']} V @ R={r}Ω")
            print(f"  线缆 R={r}Ω L={l*1e6:.1f}µH: 峰值 {i.max():.2f} A @ {t[i.argmax()]*1e6:.1f}µs,"
                  f" VBUS 过冲 {vb.max():.2f} V,+5V 峰值 {v5.max():.2f} V"
                  f"(LDO 上限 {d['vin_abs']} V){'' if ok_v else ' 超标'},"
                  f"注入电荷 {q*1e6:.1f} µC {'OK' if ok_q else '超标'}")
            if r == 0.2:
                ax[3].plot(t * 1e6, i, label=f"{key} I(VBUS)")
        print()

    for k, key in enumerate(DESIGNS):
        ax[k].axhline(3.3 * 0.98, color="gray", ls="--", lw=0.8)
        ax[k].set(xlabel="3V3 load (mA)", ylabel="3V3 (V)", ylim=(2.5, 3.4),
                  title=f"{DESIGNS[key]['label']} (typ. dropout)")
        ax[k].legend()
        ax[k].grid(alpha=0.3)
    ax[3].set(xlabel="time (µs)", ylabel="inrush current (A)", xlim=(0, 60),
              title="Hot-plug inrush (0.2 Ω, 1 µH cable)")
    ax[3].legend()
    ax[3].grid(alpha=0.3)
    fig.tight_layout()
    out = HERE / "power_sim.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out.name}")
    # 只有当前设计(最后一版)必须过;旧版留作对照
    bad = [f for f in failures if f.startswith(list(DESIGNS)[-1])]
    if bad:
        print("!! 当前设计未通过:", "; ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
