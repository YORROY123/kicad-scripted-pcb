# kicad-scripted-pcb

**[English](README.md)**

三塊完全用程式碼設計的 KiCad 10 電路板:原理圖、PCB 擺件、佈線(交給 [freerouting](https://github.com/freerouting/freerouting))和鋪銅,全部由 Python 腳本產生,一個指令就能從零重建,過程中不需要開 KiCad 的視窗。

重點在**驗證**。每次建置都會跑好幾道互相獨立的檢查,因為每一道都只抓得到特定類型的錯誤。下面列出的錯誤,有些就是在做這幾塊板子的過程中真的抓到的。

| | 板子 | 結果 |
|---|---|---|
| ![usbc-ldo](boards/usbc-ldo/board-top.png) | **usbc-ldo**:USB-C 5V → 3.3V LDO → LED。40 × 24 mm 雙層板,附 ngspice 電源模擬 | ERC 0、DRC 0、原理圖一致 |
| ![esp32c3](boards/esp32c3/board-top.png) | **esp32c3**:ESP32-C3 最小系統板,原生 USB、AP2112K、RESET/BOOT、LED、8 pin 排針。32 × 46 mm | ERC 0、DRC 0、原理圖一致、網表逐腳比對 |
| ![relay8](boards/relay8/board-top.png) | **relay8**:ESP32-C3 + ULN2803 驅動 8 路市電繼電器(NO/COM/NC 端子),有隔離開槽和自訂市電間距規則。150 × 95 mm。**未經安規認證** | ERC 0、DRC 錯誤 0(43 個絲印被開槽/板邊裁切的警告已列出)、原理圖一致 |

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
| ngspice 模擬 | 設計餘量 | 第一塊板的 LDO 壓差 1.1V,在 USB 下限 4.40V 時會掉出穩壓;插入瞬間注入約 124 µC(USB 2.0 上限 50 µC)。兩塊 ESP32 板就是依這個結果設計的 |

## 踩過的坑

- **freerouting-cli 2.5.0 會崩潰**([#957](https://github.com/freerouting/freerouting/issues/957)),要改用 jar,而 jar 需要 Java 25。
- freerouting 的**自動收窄**會把 0402 焊盤旁的線收到 0.125 mm,比 JLCPCB 的下限 0.127 mm 還細。要加 `--router.automatic_neckdown=false --router.neck_width_um=150`。
- DSN 不帶板邊間距,要另外傳 `--router.copper_to_edge_clearance_um`。這個參數**不管板內開槽**,開槽附近要另外放禁止區。
- 網路類別存在 `.kicad_pro`,不在 `.kicad_pcb`,要用 `pcbnew.SaveBoard()` 才會一併寫出。
- 用 Python 呼叫 `board.Remove(zone)` 可能報錯或讓 pcbnew 崩潰,要改用 `board.Delete()`。
- freerouting 在細間距封裝內報出的焊盤間「違規」,KiCad DRC 判定沒問題。根因是 KiCad 的 DSN 匯出器把圓角焊盤的**每一邊**都放大了。
- Windows PowerShell 5.1 會把沒有 BOM 的 UTF-8 腳本當成 ANSI 讀,所以這裡的建置腳本全部只用 ASCII 字元。

## 需求與快速開始

需要 Windows、[KiCad 10](https://www.kicad.org/)、Python 3.10 以上;模擬另外需要 numpy 和 matplotlib。freerouting 和 Java 25 由下載腳本抓取,會核對 SHA-256,只放在 `tools\`,不安裝到系統。

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-tools.ps1
powershell -ExecutionPolicy Bypass -File boards\esp32c3\build.ps1
```

## 限制

這幾塊都是雙層板,用模組、電源設計簡單。沒有阻抗控制、等長佈線、BGA,也沒有 SI/PI 分析,freerouting 也不做這些。產出的板子是需要人審查的起點,不是可以直接送廠的設計。**relay8 接市電**,這一點對它尤其重要。

## 授權

MIT。freerouting(GPL-3.0)與 Temurin JRE 是在安裝時才下載的,不包含在這個 repo 裡。
