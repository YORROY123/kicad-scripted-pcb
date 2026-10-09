"""usbc-ldo 测试板的摆放。必须用 KiCad 自带的 python.exe 跑。"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from pcbgen import BoardSpec, build  # noqa: E402

# ── usbc-ldo 测试板 ──────────────────────────────────────────────────────
# 信号从左往右流:USB-C → CC 电阻 / ESD → 肖特基 → TVS、输入电容 → LDO →
# 输出电容 → LED。J1 开口贴左边缘。
USBC_LDO = BoardSpec(
    name="usbc-ldo",
    width=40.0,
    height=24.0,
    place={
        # ref: (x, y, rot)。HRO 封装开口朝 +y;转 -90° 后开口朝 -x(板左缘)。
        "J1": (4.2, 12.0, -90),
        "R1": (11.5, 5.0, 90),      # CC 下拉,贴着 J1 的 CC 脚上下两侧
        "R2": (11.5, 19.0, 90),
        "D2": (13.5, 12.0, 0),      # ESD 紧贴 D+/D- 脚
        "D1": (20.0, 4.5, 0),       # 肖特基:VBUS → +5V
        "D3": (20.0, 19.5, 180),    # TVS
        "C2": (21.5, 12.0, 90),     # 输入大电容
        "C1": (24.0, 15.0, 90),     # 100nF 贴 U1.VIN
        "U1": (30.0, 12.0, 0),      # VIN 在左下、GND 左上、VOUT/散热片在右
        "C3": (37.0, 9.0, 90),      # 输出电容贴 VOUT
        "R3": (37.0, 14.0, 90),
        "LED1": (37.0, 18.0, 90),
    },
    # 电源网单独一类加粗。不加的话 freerouting 会把 VBUS 也走成 0.19mm 细线。
    power_nets=("GND", "+5V", "+3V3", "Net-(D1-A)"),  # Net-(D1-A) 即 VBUS
    overhang=("J1",),
)


if __name__ == "__main__":
    root = HERE.parent
    build(USBC_LDO, root / "net.txt", root / "usbc-ldo.kicad_pcb")
