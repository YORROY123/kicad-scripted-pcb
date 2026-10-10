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

## 送廠前必須確認(還沒做)

1. **CM5 載板連接器**:CM5 規格書 4.1.1 推薦 Amphenol `10164227-1001A1RLF`(1.5 mm 堆疊,LCSC C6782225)
   或 `-1004A1RLF`(4.0 mm,底下留 2.5 mm 空間,C7435219 庫存少)。KiCad 只有 Hirose DF40 的封裝,
   要對 Amphenol 圖面確認焊盤相容、焊盤 1 位置。1.5 mm 堆疊時 CM5 底下**不能放零件**。
2. **兩顆連接器在板上的位置與方向**:規格書圖 4 是向量圖,文字抽不出座標;
   要用 CM5 IO Board 的設計檔或把圖渲染出來量。固定孔 M2.5 在 (3.5, 3.5)、(51.5, 3.5)、(3.5, 36.5)、(51.5, 36.5)(表 13)。
3. **PoE 變壓器**:選 CND-tek G2423S(LCSC C5122139,802.3at、每口 720 mA)。接腳圖是向量圖,
   目前只從文字得知極性 1-24、4-21、7-18、10-15 同相,完整接腳要看圖。
4. **IP804AR 規格書沒有應用電路**,PoE 接法照 802.3 推導,要另外審。
