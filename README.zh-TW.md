# kicad-scripted-pcb

**[English](README.md)**

三塊完全用程式碼設計的 KiCad 10 電路板:原理圖、PCB 擺件、佈線(交給 [freerouting](https://github.com/freerouting/freerouting))和鋪銅,全部由 Python 腳本產生,一個指令就能從零重建,過程中不需要開 KiCad 的視窗。

重點在**驗證**。每次建置都會跑好幾道互相獨立的檢查,因為每一道都只抓得到特定類型的錯誤。下面列出的錯誤,有些就是在做這幾塊板子的過程中真的抓到的。

| | 板子 | 結果 |
|---|---|---|
| ![usbc-ldo](boards/usbc-ldo/board-top.png) | **usbc-ldo**:USB-C 5V → 3.3V LDO → LED。40 × 24 mm 雙層板,附 ngspice 電源模擬 | ERC 0、DRC 0、原理圖一致 |
| ![esp32c3](boards/esp32c3/board-top.png) | **esp32c3**:ESP32-C3 最小系統板,原生 USB、LP38693、RESET/BOOT、LED、8 pin 排針。32 × 49 mm | ERC 0、DRC 0、原理圖一致、網表逐腳比對 |
| ![relay8](boards/relay8/board-top.png) | **relay8**:ESP32-C3 + ULN2803 驅動 8 路市電繼電器,**只接一條市電線**:板上 HLK-10M05 AC-DC(100–240V)、T8A 保險絲、壓敏電阻、L/N 匯流排,每路 NO · N · NC 端子,有隔離開槽和自訂市電間距規則。232 × 110 mm。**未經安規認證** | ERC 0、DRC 錯誤 0(40 個絲印被開槽/板邊裁切的警告已列出)、原理圖一致 |

兩塊 ESP32 板都附有 `FIRMWARE.md`(給寫韌體的人看):腳位表、燒錄步驟、第一支程式;relay8 另外附市電接線說明。

## 每道檢查抓什麼、漏什麼

| 檢查 | 抓得到 | 這次漏掉、靠別的檢查才抓到的 |
|---|---|---|
| 導線橫穿引腳/共線重疊檢查 | 導線橫穿腳位造成的隱性短路、兩個網被重疊導線併在一起 | — |
| KiCad ERC | 漏接、電源沒有被驅動 | **LED 接反**:兩支被動腳接在一起,ERC 不會報。是做 PCB 讀網表時才發現的 |
| 網表逐腳比對 | 腳位接錯網、只接一支腳的孤立網 | ERC **預設忽略**「全域標籤只出現一次」,標籤打錯字不會報錯。已用突變測試(故意改錯一個標籤)證明比對會失敗 |
| 擺件自檢 | 焊盤網路對不上網表、零件出板、courtyard 重疊 | 用 courtyard 的真實多邊形判斷。ESP32 模組的 courtyard 是 T 字形,用外接矩形會把合法位置誤判成重疊 |
| DRC + 原理圖一致性 | 間距、線寬、板邊距、原理圖與 PCB 是否一致 | — |
| 自訂 DRC 規則 | 市電 ↔ 低壓 ≥ 3.0 mm、市電 ↔ 市電 ≥ 2.4 mm | 開槽繞過去的爬電距離 DRC 不檢查,要人審 |
| ngspice 模擬 | 設計餘量 | 第一塊板的 LDO 壓差 1.1V,在 USB 下限 4.40V 時會掉出穩壓;插入瞬間注入約 124 µC(USB 2.0 上限 50 µC)。三塊板現在都用 LP38693(輸入耐壓 12V):`esp32c3/sim` 顯示 VBUS 只有 1µF 時,熱插拔線纜振鈴會衝到 7.7–8.6V,超過 ESP32 板原本用的 AP2112K 的 6.5V 耐壓 |
| `lib/review.py` 設計審查(用規格書規則審網表) | **意圖本身**的錯:二極體 / TVS 方向、用真實 Vf 範圍算 LED 電流、各型號規格書的去耦與電源範圍、USB-C CC 下拉、ESP32-C3 的 EN RC / 開機腳 / GPIO18-19、繼電器續流路徑與吸合電壓、電容耐壓與極性、各電源的電流預算、LDO 接面溫度、USB VBUS 電容 | **usbc-ldo 的 SMAJ5.0A TVS 接反**:陽極接 +5V、陰極接地,一插 USB 就短路。KiCad 符號把陰極腳取名「A1」。ERC、DRC、網表比對、SPICE 模擬(模擬裡方向是對的)全都通過。另外抓到藍光 LED 接 3.3V GPIO(Vf 最高 3.6V)、綠色電源燈只有約 0.45mA。`lib/review_test.py` 把真實網表故意弄錯 20 種,每條規則都要報錯 |
| `lib/lcsc.py` + `lib/fab.py` | LCSC 料號的型號、庫存、封裝尺寸、電阻電容數值、LED 顏色;符號預設封裝 vs 實際封裝;鑽孔數;BOM / CPL / 板上位號一致 | 三塊板都用 USBLC6-2**P6**(SOT-666)的符號配 SOT-23-6 封裝:腳位相同,其他檢查都沒發現,但照值買料會買到貼不上的。SMAJ5.0A 原本選的料號庫存是 0 |

## 踩過的坑

- **freerouting-cli 2.5.0 會崩潰**([#957](https://github.com/freerouting/freerouting/issues/957)),要改用 jar,而 jar 需要 Java 25。
- freerouting 的**自動收窄**會把 0402 焊盤旁的線收到 0.125 mm,比 JLCPCB 的下限 0.127 mm 還細。要加 `--router.automatic_neckdown=false --router.neck_width_um=150`。
- DSN 不帶板邊間距,要另外傳 `--router.copper_to_edge_clearance_um`。這個參數**不管板內開槽**,開槽附近要另外放禁止區。
- 網路類別存在 `.kicad_pro`,不在 `.kicad_pcb`,要用 `pcbnew.SaveBoard()` 才會一併寫出。
- 用 Python 呼叫 `board.Remove(zone)` 可能報錯或讓 pcbnew 崩潰,要改用 `board.Delete()`。
- freerouting 在細間距封裝內報出的焊盤間「違規」,KiCad DRC 判定沒問題。根因是 KiCad 的 DSN 匯出器把圓角焊盤的**每一邊**都放大了。
- Windows PowerShell 5.1 會把沒有 BOM 的 UTF-8 腳本當成 ANSI 讀,所以這裡的建置腳本全部只用 ASCII 字元。

## 需求與快速開始

需要 Windows、[KiCad 10](https://www.kicad.org/)、Python 3.10 以上(原理圖產生與設計審查只用標準函式庫);模擬與場解器另外需要 numpy、scipy、matplotlib。freerouting 和 Java 25 由下載腳本抓取,會核對 SHA-256,只放在 `tools\`,不安裝到系統。只有 `lib/lcsc.py`(查 JLCPCB 零件庫)要連網,建置本身不連網。

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-tools.ps1
powershell -ExecutionPolicy Bypass -File boards\esp32c3\build.ps1
python lib\review_test.py          # 設計審查的突變測試;要先 build 過一次
```

建置的流程:原理圖 → ERC → 網表比對 → **設計審查** → 擺件 → freerouting → 鋪銅 → DRC → 製造檔。任何一步不過就停,不帶錯往下走。最後產出在 `boards/<板>/fab/`:

| 檔案 | 用途 |
|---|---|
| `<板>-gerber.zip` | 上傳 JLCPCB 做空板 |
| `<板>-bom.csv`、`<板>-cpl.csv` | 上傳做 SMT 貼片(LCSC 買得到的件) |
| `hand-solder.csv` | LCSC 買不到、要自購手焊的件(relay8 的市電端子、保險絲座) |
| `rotation-review.csv` | 每顆件的 CPL 角度與依據。**都沒有實物驗證**,要在 JLCPCB 貼片預覽逐顆對照 |

`boards/<板>/review.txt` 是設計審查報告(含推算出的各網電壓),`lcsc-check.json` 是對過 JLCPCB 的料號、庫存與屬性。

想加一塊板或一條審查規則?看 [CONTRIBUTING.md](CONTRIBUTING.md)(英文,中文討論也歡迎)。

## 限制

這幾塊都是雙層板,用模組、電源設計簡單。沒有阻抗控制佈線、等長佈線、BGA,也沒有 SI/PI 分析,freerouting 也不做這些(`lib/field2d.py` 可以告訴你一條線需不需要)。製造檔已經齊全到可以下單,但這些板子還沒有人實際做過:CPL 角度沒驗證,設計審查是一組規則,不是工程師。下單前請人審過。**relay8 接市電**,這一點對它尤其重要。

## 授權

MIT。freerouting(GPL-3.0)與 Temurin JRE 是在安裝時才下載的,不包含在這個 repo 裡。
