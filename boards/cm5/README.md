# CM5 carrier(進行中)

Raspberry Pi Compute Module 5(含 eMMC)的通用載板,目標是 JLCPCB 能直接 PCBA,CM5 自己插上。

## 規格(草案)

- 電源:54 V DC 輸入(120 W)→ LM5146 降壓 → 5 V;5 V → 3.3 V 降壓(CM5_3V3 每腳 300 mA、合計 600 mA,不夠供 LAN7800 ×2)
- 網路 ×3:CM5 原生 Gigabit → router;CM5 的 USB3-0 / USB3-1 → LAN7800 ×2 → 2 個 802.3at PoE 口(IP804AR auto mode)
- USB 2.0(CM5 腳 103/105)經 FSUSB42 切換:平常 → USB2514B Hub → USB-A ×2;按 nRPIBOOT 開機 → USB-C 燒錄口
- HDMI、M.2 M-key(PCIe Gen2 x1)、40-pin GPIO、RTC 電池、電源鍵、nRPIBOOT 鍵、狀態燈、風扇
- 4 層板

## 已完成

- `gen/cm5_sym.py` → `symbols/CM5.kicad_sym`:CM5_J1(CM5 腳 1–100)、CM5_J2(焊盤 n = CM5 腳 100+n)。
  `--verify <pdftotext 輸出>` 從規格書 4.2 Pinout 重新解析逐腳比對,目前 200/200 一致。

- `gen/cm5_fp.py` → `footprints/CM5.pretty/Amphenol_10164227-1001A1RLF_2x50_P0.4mm.kicad_mod`:
  一顆連接器一個封裝(J1、J2 共用,BOM 與座標檔才會逐顆列出),兩顆與 4 個孔的相對位置在
  `MODULE`(模組中心為原點)。`--compare <官方封裝>` 把兩顆連接器與孔組回去,用 pcbnew 逐焊盤比對
  位置、尺寸、形狀、類型、銅層、錫膏、阻焊:**200/200、孔 4/4 一致**。比對本身用 5 種故意改錯驗證過
  (排距、焊盤寬、J2 偏 0.1 mm、孔偏 0.1 mm、奇偶排對調 = 腳 1 放錯邊),都會失敗。
  兩顆照 `MODULE` 擺在空板上、每個焊盤不同網路,DRC 0。
- `lib/pcbgen.py` 加 `EXTRA_FP_DIRS`:板子自己的封裝庫,先找這裡。

- **原理圖區塊 1:54V 輸入 → LM5146 → 5V / 12A**(`gen/board.py`,設計推導寫在檔頭)。
  照 TI 規格書 Design 1(48V → 5V / 12A、300kHz)改:UVLO 開 40.1V / 關 36.1V、MOSFET 換 JLC 有庫存的
  Infineon BSC160N10NS3G(高側)/ BSC070N10NS5(低側)、限流 R13 依新 MOSFET 重算。
  LM5146 符號由 `gen/parts_sym.py` 生成(腳位照規格書表 6-1)。`build.ps1`:ERC 0、網表比對 97/97、設計審查 0 錯誤。
- `lib/schgen.py` / `lib/netlabel.py`:旋轉 90° / 270° 的器件,引腳原本算到鏡像位置(KiCad 是畫面逆時針)。
  ERC 抓不到,網表比對才抓到。三塊既有板子沒用到 90° / 270°,重生原理圖內容不變。

### 電源區塊待確認
1. **電感封裝**:目前暫填 `L_Bourns_SRP1050WA`,要依 TDK SPM10065VT 的規格書焊盤圖另做(可用 Pi 轉圖)。
2. **LM5146 裸露焊盤尺寸**:LCSC 的規格書只有封裝總覽頁,沒有 RGY0020 詳圖;
   KiCad 的 `Texas_RGY_R-PVQFN-N20_EP2.05x3.05mm` 要對 TI 原檔確認(帶 wettable flank 的版本可能不同)。
3. **補償**:輸出電容改 10V(原設計 6.3V),實際容值較大 → 要模擬(ngspice)確認相位裕度。
4. **BSC070N10NS5 在 VGS 7.5V 的 RDS(on)**:限流值用估計的 6.5mΩ,要對規格書曲線。
5. **反接保護**:目前是 TVS + 保險絲撬棍式,電源短路電流大時 TVS 要撐到保險絲斷;考慮改理想二極體。

## 已查清(2026-10-12)

規格書的向量圖在樹莓派上用 `pdftoppm` 轉成 PNG 讀出;連接器位置另外用官方
CM5 IO Board rev 2 的 KiCad 檔(<https://rpltd.co/cm5io-design-files>,`RP-008099-DD-1`)核對。

1. **CM5 連接器與封裝**:官方 IO 板用的就是 2 顆 Amphenol `10164227-1001A1RLF`,
   封裝 `CM5IO:Raspberry-Pi-5-Compute-Module` 把兩顆連接器和 4 個固定孔做成一個封裝。
   焊盤 0.2 × 0.7 mm、腳距 0.4 mm、每顆 2 排 × 50。官方檔只寫 `Copyright © 2024 Raspberry Pi Ltd.`、
   沒有授權條款 → **不放進本 repo**,由腳本依下列尺寸自己生成,再逐焊盤和官方檔比對。
2. **位置**(官方封裝座標,原點 = 一個固定孔,連接器沿 y 方向):
   - 固定孔 NPTH 2.7 mm:(0, 0)、(33, 0)、(0, −48)、(33, −48) → 孔距 33 × 48 = (40 − 7) × (55 − 7)
   - 腳 1–100 的連接器:中心線 x = −0.5(奇數腳 x −2.04、偶數腳 x 1.04),腳 1/2 在 y −31.3、腳 99/100 在 y −11.7
   - 腳 101–200 的連接器:中心線 x = 33.5(奇數 31.96、偶數 35.04),腳 101/102 在 y −31.3
   - 也就是:連接器中心線離模組邊 3 mm、連接器中心離固定孔 21.5 mm —— 與規格書圖 4 相符
3. **PoE 變壓器 G2423S 接腳**(4 組,每組 1CT:1CT,纜線側另有共模扼流):
   | 組 | 晶片側 TD+ / TD− / TCT | 纜線側 MX+ / MX− / MCT |
   |---|---|---|
   | 1 | 23 / 22 / 24 | 2 / 3 / 1 |
   | 2 | 20 / 19 / 21 | 5 / 6 / 4 |
   | 3 | 17 / 16 / 18 | 8 / 9 / 7 |
   | 4 | 14 / 13 / 15 | 11 / 12 / 10 |
   PoE 由 MCT(1、4、7、10)注入:MCT 直接接纜線側繞組中心抽頭,MX± 經共模扼流。

## 送廠前必須確認(還沒做)

1. 1.5 mm 堆疊時 CM5 底下**不能放零件**(擺件時當禁區)。
2. **IP804AR 規格書沒有應用電路**,PoE 接法照 802.3 推導,要另外審。
