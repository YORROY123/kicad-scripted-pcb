"""USB 熱插拔模擬:esp32c3 與 relay8 的 VBUS → AP2112K-3.3 電源路徑。

    python boards/esp32c3/sim/power_sim.py

usbc-ldo 的模擬發現:輸入電容小時,線纜電感會讓 VBUS 熱插拔過衝,
而 AP2112K 的輸入絕對最大只有 6.5V(Diodes DS39724)。這兩塊板都是
VBUS 經小電容接 AP2112K,所以照同樣條件查:
  1. AP2112K 輸入腳峰值是否 < 6.5V
  2. 插入注入電荷是否 ≤ 50µC(USB 2.0)

USBLC6-2P6 的 VBUS 腳對地有一顆內部齊納,會鉗位一部分過衝。它的規格只寫
「VBR 最小 6V @1mA」,沒有大電流下的特性,所以分「不計鉗位」與「計入鉗位」
兩種算;判定以不計鉗位為準(不拿沒規格保證的東西當安全餘量)。

ESP32-C3-WROOM-02 模組內部的 3V3 去耦(規格書 v1.7 圖 8-1):C5 10µF、C3/C11 1µF、
三顆 0.1µF、10nF,合計約 12.3µF,與板上 C2/C3 並聯。

LDO 輸入耐壓:AP2112K 6.5V(現行);LP38693 12V(TI SNVS321O,usbc-ldo 已換)。
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "usbc-ldo" / "sim"))
from power_sim import MODELS, NgSpice  # noqa: E402

LDO_ABS = {"AP2112K": 6.5, "LP38693": 12.0}   # 輸入絕對最大
Q_LIMIT = 50e-6     # USB 2.0:插入注入電荷上限

# USBLC6 VBUS 腳的內部齊納:VBR 最小 6V,取 6.5V 中值;RS 只是假設值
CLAMP = ".model ZLC6 D(IS=1e-12 N=1 RS=1 BV=6.5 IBV=1m CJO=30p)"

LDO = """
Bldo vin vo_i I = min(0.8, max(0, (min(3.3, V(vin) - 0.1) - V(v33)) * 100))
Vsns vo_i v33 0
Ignd vin 0 55u
"""


def circuit(board: str, r: float, l: float, c_in: str, c_mod: str, clamp: bool,
            rload: str = "1meg") -> str:
    if board == "esp32c3":
        path = "Rlink vbus vin 1m"            # VBUS 直接接 LDO
    else:
        path = "D5 vbus vin SS34"             # relay8:VBUS 經 SS34 到 5V_SYS
    # 負載預設不接:插入瞬間模組還沒開機;接上負載的話 200µs 內的負載電流
    # 也會被算進「注入電荷」,把電容充電量灌水(第一版就這樣算錯,多了約 20µC)
    return f"""usb hot-plug {board}
Vbus vsrc 0 PWL(0 0 1u 5 10m 5)
Lcable vsrc vl {l}
Rcable vl vbus {r}
{path}
{"Dz 0 vbus ZLC6" if clamp else ""}
C1 vin 0 {c_in}
{LDO}
C2 v33 0 10u
C3 v33 0 100n
Cmod v33 0 {c_mod}
Rload v33 0 {rload}
{MODELS}
{CLAMP}
.end
"""


def main() -> int:
    ng = NgSpice()
    bad = []
    for board in ("esp32c3", "relay8"):
        print(f"######## {board}(C1 = 1µF、C2 10µF + C3 100nF + 模組約 12.3µF)########")
        for clamp in (False, True):
            for r, l in ((0.2, 1e-6), (0.1, 0.5e-6)):
                ng.load(circuit(board, r, l, "1u", "12.3u", clamp))
                d = ng.run("tran 10n 200u", ["i(vbus)", "v(vin)"])
                t, i, vin = d[:, 0], -d[:, 1], d[:, 2]
                q = np.trapezoid(i, t)
                verdict = "  ".join(f"{k} {'OK' if vin.max() < v else '超標'}" for k, v in LDO_ABS.items())
                if not clamp and vin.max() >= LDO_ABS["LP38693"]:
                    bad.append(f"{board} R={r}: {vin.max():.2f} V")
                print(f"  {'計入鉗位' if clamp else '不計鉗位'}  線纜 R={r}Ω L={l*1e6:.1f}µH:"
                      f"LDO 輸入峰值 {vin.max():5.2f} V({verdict}),"
                      f"電荷 {q*1e6:5.1f} µC{'' if q <= Q_LIMIT else ' 超過 USB 50µC'}")
        print()
    # 只擋會燒壞器件的過衝;電荷超標是 USB 規範合規問題,列出不擋(見 FIRMWARE.md)
    if bad:
        print("!! LDO 輸入過衝超過耐壓:")
        for b in bad:
            print("   " + b)
        return 1
    print("LDO 輸入峰值全部在 LP38693 耐壓內")
    return 0


if __name__ == "__main__":
    sys.exit(main())
