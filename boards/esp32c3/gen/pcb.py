"""ESP32-C3 板的摆放。共用逻辑(读网表、放件、规则、自检)在 lib/pcbgen.py。

必须用 KiCad 自带的 python.exe 跑。坐标是 mm,板框左上角为原点,32 × 49 mm(加軟啟動時由 46 加長 3mm,下半部整體下移)。

模块(RF_Module:ESP32-C3-WROOM-02)的几何,以模块中心为原点:
  - courtyard 是 T 形:天线区 y −18.34…−6.86、宽 ±14.24;本体 y −6.86…7.14、宽 ±9.74
  - 封装自带禁止区(无铜、无走线、无过孔)y −18.1…−7.1、x ±14
  - 左排焊盘 x = −8.8:1 3V3、2 EN、3–6 IO4–7、7 IO8、8 IO9、9 GND(y −6 起每 1.5mm)
  - 右排焊盘 x = +8.8:18 IO0、17 IO1、16 IO2、15 IO3、14 IO19/D+、13 IO18/D−、
    12 TXD、11 RXD、10 IO10(同样 y −6 起)
模块中心放在 (16, 18.64):天线区上沿离板子上缘 0.3mm,禁止区落在板内 y 0.54…11.54。
本体两侧各剩一条约 6mm 宽的空间,放紧贴对应引脚的小件。
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from pcbgen import BoardSpec, build  # noqa: E402

H = 49.0
MX, MY = 16.0, 18.64          # 模块中心(天线区上沿离板缘 0.3mm:贴齐时 courtyard 线宽会超出板框)


def pin_y(n: int) -> float:
    """左排第 n 脚(1–9)的 y;右排 18…10 与左排 1…9 同高。"""
    return MY - 6.0 + 1.5 * (n - 1)


ESP32C3 = BoardSpec(
    name="esp32c3",
    width=32.0,
    height=H,
    place={
        "U1": (MX, MY, 0),
        # 左条(本体左缘 x 6.26):排针靠板边,上拉/RC 贴着对应引脚
        "J2": (2.4, 14.1, 0),               # 1×8 排针,往 +y 延伸到 ~33.7
        "C3": (5.2, pin_y(1) + 0.3, 90),    # 100nF 贴 3V3 脚
        "R3": (5.2, pin_y(2) + 0.8, 90),    # EN 上拉
        "C4": (5.2, pin_y(2) + 2.8, 90),    # EN 延时电容
        "R5": (5.2, pin_y(7), 90),          # IO8 上拉
        "R4": (5.2, pin_y(8) + 0.5, 90),    # IO9 上拉
        # 右条(本体右缘 x 25.74)
        "R6": (27.5, pin_y(3), 90),         # IO2 上拉
        "R7": (27.5, pin_y(9), 90),         # 用户 LED 限流
        "D2": (29.5, 27.5, 0),              # 用户 LED
        "R8": (28.0, 30.5, 0),              # 电源 LED 限流
        "D3": (28.0, 33.0, 0),              # 电源 LED
        # 下半部:USB-C 开口朝下贴下缘,ESD 在接头与模块 USB 脚之间
        "J1": (16.0, H - 4.2, 0),
        "D1": (22.0, 34.0, 0),              # USBLC6
        "R1": (13.5, 37.5, 90),             # CC1 5.1k
        "R2": (19.0, 36.5, 90),             # CC2 5.1k
        # LDO 一组在左下
        # LP38693 SOT-223-5 轉 180°:四支腳朝右(由上而下 IN/OUT/NC/EN),散熱片 GND 朝左
        "U2": (8.6, 30.0, 180),
        "C5": (14.3, 27.0, 0),              # 1µF 輸入(VSW),貼 IN 腳
        # 軟啟動:VBUS → Q1 → VSW,閘極元件圍在 Q1 旁
        # x≈3.7 留給 EN(SW1 → 模組)往上走的通道
        "Q1": (7.2, 37.5, 180),
        "R9": (5.8, 40.6, 0),
        "C6": (8.2, 40.6, 0),
        "C7": (10.4, 36.0, 0),
        "C1": (9.8, 38.9, 90),              # 1µF 留在 VBUS 側
        "C2": (14.0, 30.2, 90),             # 10µF 輸出,貼 OUT 腳
        # 按键在两个下角
        "SW1": (5.0, 45.5, 0),              # RESET
        "SW2": (27.0, 45.5, 0),             # BOOT
    },
    power_nets=("GND", "VBUS", "+3V3"),
    overhang=("J1",),
    min_hole=0.2,           # 模块散热焊盘下的导热孔是 0.2mm(Espressif 官方封装,不改)
    fab_ref_libs=("Resistor_SMD", "Capacitor_SMD"),
)

if __name__ == "__main__":
    root = HERE.parent
    build(ESP32C3, root / "net.txt", root / "esp32c3.kicad_pcb")
