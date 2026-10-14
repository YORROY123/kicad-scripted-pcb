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

- **原理圖區塊 2:5V → TPS568230 → 3.3V / 8A**。照 TI 規格書 ZHCSIY3C 表 3(3.3V、600kHz、1.5µH)
  與表 1(MODE 330k / 5.1k = Eco-mode 600kHz)。EN 絕對最大 4V,所以 LM5146 的 PGOOD(拉到 5V)
  經 R18 20k / R19 30k 分壓成 3.0V 才接 EN —— 3.3V 等 5V 穩定才起來。ERC 0、網表 152/152、審查 0 錯誤。

- `lib/review.py` 會推算可調穩壓器的輸出(`ADJUSTABLE`:VREF 範圍 × (1 + R上 / R下),電阻 ±1%):
  +5V 4.87–5.13V、+3V3 3.23–3.44V。之後接上 CM5、LAN7800,電源腳的範圍檢查就會用到這兩個值。
  `lib/review_test.py` 加了 3 個 cm5 突變測試(分壓改錯、上下對調、拿掉輸入電容),都會被抓到。

- **原理圖區塊 3:CM5 連接器**(圖紙改 A1)。5V ×6、GND、GPIO_VREF → CM5_3V3、CR2032 RTC 電池、
  電源鍵、nRPIBOOT 鍵、紅色電源燈 / 綠色活動燈(照官方 IO 板:陽極接 CM5_3.3V、1k 接模組 LED 腳)。
  其餘訊號腳先打 NC,後續區塊再接。
  **+3V3 改由 CM5 控制**:LM5146 PGOOD 上拉改接 CM5_3V3、直接驅動 TPS568230 EN →「5V 正常且 CM5 開機」
  才有 +3V3,CM5 關機時周邊一起斷電,不會倒灌進模組(規格書 3.1:5V 出現前任何腳都不能有電)。
  ERC 0、網表 368/368、審查 0 錯誤(2 個 WARN:LED 缺 Vf,要等料號核對)。
- `lib/review.py`:LED 電阻在陰極側(陽極直接接電源)也算得出電流;電源腳接到 GND 會報錯;
  規格書沒有去耦要求的電源腳不再要求電容。突變測試新增「GPIO_VREF 接地」「CM5 5V 腳接 +3V3」。

- **原理圖區塊 4:CM5 原生 Gigabit 網口**。照官方 CM5 IO 板:Pair0–3 → 2 × TPD4EUSB30(直通式 ESD,
  JLC C90627)→ Hanrun HR911130A MagJack(JLC C54408,庫存 2 萬);晶片側中心抽頭 100nF 對地,
  10 腳(內部 Bob Smith 終端)與屏蔽接 GND;nLED3 活動燈(綠)/ nLED2 速度燈(黃)經 470Ω,陽極接 CM5_3V3。
  ERC 0、網表 409/409、審查 0 錯誤。
- `gen/hr911130a_fp.py`:HR911130A 封裝(KiCad 沒有)。規格書是向量圖,在 Pi 上轉圖後讀尺寸,
  10 支訊號腳、定位柱、屏蔽腳用 Hough 圓偵測自動核對(≤ 0.02mm)。LED 腳圖上沒照比例畫,
  採標註值 13.25,並用 `--compare` 對 KiCad 內建同系列 HR911105A 的定位柱、LED 腳、屏蔽腳(一致;
  故意改成圖上量到的 12.7 會失敗)。單獨擺在空板、每焊盤不同網路,DRC 只剩兩支 SH 未連線(預期)。

- **原理圖區塊 5:USB3 → Gigabit ×2(LAN7800)**。CM5 USB3-0 / USB3-1(含各自的 USB2 對)→ 兩顆 LAN7800。
  照規格書 DS00001992H:3.3V 腳接 +3V3、內建 1.2V 降壓(3.3µH + 10µF)與 2.5V LDO(1µF)、REF_REXT 2k、
  REF_FILT 1µF、USBRBIAS 12k、25MHz 晶振(C13740,±30ppm)+ 27pF;LAN7800 TX → 100nF → CM5 RX
  (CM5 TX 已含電容);RESET_N 接 PG_3V3;不接 EEPROM,MAC 寫 OTP;LED0/LED1 → 綠 / 黃燈。
  **MDI(TR0–TR3)暫時 NC**,區塊 6 接 PoE 變壓器。符號 `gen/parts_sym.py` 對規格書圖 3-1 自動比對 48/48。
  review.py 加 LAN7800 電源範圍與內建穩壓器輸出,3 個突變測試(1.2V/2.5V 接錯、3.3V 腳接 5V)都抓到。

- **原理圖區塊 6:802.3at PoE ×2**。IP804AR(JLC C19626921,4 埠 PSE、MOSFET 內建,用 Port0/1)自動模式、
  無 EEPROM、序列 LED 關閉;每埠 G2423S 變壓器(C5122139)→ Amphenol RJHSE5380 RJ45(C464586)。
  Alternative A、MDI-X 極性:RJ45 3/6 = +54V(經 1.5A 保險絲)、1/2 = PortN;4/5、7/8 中心抽頭經 75Ω +
  1nF/2kV(Bob Smith);每埠 SM6T68A + 100nF/100V。LAN7800 MDI 接上變壓器晶片側,中心抽頭各 100nF。
  符號:IP804AR 對規格書表 1 自動比對 48/48;G2423S 照轉圖的接線圖。`gen/g2423s_fp.py` 封裝(內外緣 12.70/16.50、
  跨距 13.97 自動核對;空板 DRC 0)。ERC 0、網表 814/814、審查 0 錯誤。
- `rails.json`:宣告從接頭進來的電源範圍(+54V 50–57V),review.py 據此推算與檢查(IP804AR V54 at 模式 50–57V)。
- `lib/netlabel.py`:電氣類型已是 no_connect 的腳不再加 NC 標記(KiCad 會誤報 dangling);relay8 原理圖因此少一個
  多餘的 NC 標記,ERC 與網表不變。

- **原理圖區塊 7:USB 2.0**。CM5 USB_P/N → FSUSB42(C11355)→ RUN:USB2514B Hub(C16251)→ USB-A ×2
  (Molex 48037-2200 C2765195,各一顆 AP2171W 1A 開關 C110466 + 100µF);FLASH:USB-C 燒錄口(CC 5.1k)。
  **原本的 RPIBOOT 按鈕改成 SW51 滑動開關(PCM12,C221841)**:FLASH = nRPIBOOT 低 + OTG_ID 浮接(device),
  RUN = OTG_ID 接地(host);FSUSB42 Sel 直接接 nRPIBOOT、電源接 CM5_3V3(同電源域)。Hub 預設設定
  (CFG_SEL = 00、埠 3/4 停用)、24MHz 晶振 C15643。每個 USB 接頭一顆 USBLC6。ERC 0、網表 977/977、審查 0 錯誤;
  review.py 加 USB2514B / FSUSB42 電源範圍、usb-esd 認得 USB-A,3 個新突變都抓到。

- **原理圖區塊 8:M.2 M-key**(PCIe Gen2 ×1)。插座 TE **1-2199230-6**(M key,JLC C4710843);
  ⚠ JLC 搜「2199230-4」會出現 E key 版本,SSD 插不進去 —— 料號表在 TE 圖面第 2 頁。
  `gen/m2_fp.py` 照 TE 圖面第 3 頁生成封裝(含 2230/2242/2260/2280 固定柱孔),`--compare` 對官方 CM5 IO
  封裝:訊號焊盤 67/67、機構孔位置一致(故意把下排移 0.05mm 會失敗);空板 DRC 0。
  腳位照官方 IO 板;3.3V 直接取 +3V3(PCIE_PWR_EN 不用)。review.py 加 M.2 3.3V ±5% 規則與突變測試。
  圖紙改 A0。

- **原理圖區塊 9:HDMI0**(Molex 208658-1001,C916313):照官方 IO 板直連;HDMI 5V 經 TPS2051C
  (C129581,EN 接 CM5_3V3)。⚠ TPS2051C 限流上限略高於 HDMI 規範的 0.5A,待確認;官方也沒加 HDMI ESD。
- **原理圖區塊 10:40-pin GPIO + 風扇**。GPIO0–27 全部拉到 2×20 排針,用程式對官方 J8 逐腳比對 40/40;
  風扇 JST SH 4P(C160404,與樹莓派主動散熱器相容):5V / PWM(10k 上拉)/ GND / TACHO。
- **原理圖完成**:ERC 0、網表 1126/1126、設計審查 0 錯誤(6 個 WARN 是 LED 缺 Vf,料號核對後消失)。
  CM5 刻意不接的 57 支腳:MIPI0/1(相機、螢幕)、HDMI1、SD 介面(用 eMMC 版)、SCL0/SDA0、CAM_GPIO、
  CC1/CC2、VBUS_EN(USB3 接 LAN7800,不供電)、PCIE_PWR_EN、PMIC_Enable、EEPROM_nWP、WL/BT_nDisable、SYNC_OUT。

### M.2 待確認
1. **SSD 固定柱**:四個 Ø3.7 鍍通孔要配壓入式或 SMT 銅柱(M2 螺絲),料號在 PCB 階段選。
2. **3.3V 不受 PCIE_PWR_EN 控制**:OS 無法單獨對 SSD 斷電重啟;若需要,加一顆 ≥ 3A 負載開關。
3. PCIe 走線:90Ω 差分、對內等長 0.1mm(CM5 規格書 2.3.1)。

### USB 區塊待確認
1. **韌體**:RUN 位置 OTG_ID 接地後,config.txt 仍要 `dtoverlay=dwc2,dr_mode=host` —— 寫進韌體交接。
2. **USB2514B 的 SUSP_IND/LOCAL_PWR**:浮接(內部下拉 = 埠可拔除),但 LOCAL_PWR 讀到低可能讓 hub 回報匯流排供電;
   對 Microchip 參考設計確認是否要上拉(上拉會讓 NON_REM0 = 1,埠 1 變不可拔除)。
3. **晶振負載電容**:27pF 為估計(C1 = 2(CL − C0) − CS),實物量頻率;LAN7800 同。
4. **USB2514B 封裝**:KiCad 預設 `QFN-36-1EP_6x6mm_P0.5mm_EP3.7x3.7mm`,要對規格書的 EP 尺寸。
5. 燒錄時 CM5 由本板 54V 供電,USB-C 只接資料(VBUS 只到 ESD 參考腳)。

### PoE 區塊待審(送廠前必須由懂 PoE 的人看)
1. **極性與 Alternative**:採 Alternative A、MDI-X(3/6 正、1/2 負);IP804AR 的 ALT_A/B 腳只影響內部設定,
   規格書沒有說明對偵測的影響。
2. **TVS**:SM6T68A 箝位最高約 92V > IP804AR 絕對最大 75V(PortN、V54)。參考設計多用 58V 級 TVS,但要確認。
3. **輸入電壓**:LM5146 UVLO 40V,但 802.3at 要 V54 ≥ 50V → 輸入 40–50V 時 CM5 開機、PoE 可能不供電。
   電源要選 54V(52–57V)。
4. **功率預算**:2 埠 × 30W(at)+ 5V 系統最多 60W ≈ 125W,與 120W 輸入接近;F1 4A 夠用但要再算一次。
5. **供電中心抽頭的終端**:MCT1/MCT2 只接電源,沒有 Bob Smith(帶電的抽頭不能直接經 75Ω 接地);
   EMC 上是否要加 75Ω + 10nF/100V 待審。
6. G2423S 焊墊長 1.90(由內外緣算出)vs 圖上另標 2.00 ± 0.25,在公差內。

### 電源區塊待確認
1. **電感封裝**:目前暫填 `L_Bourns_SRP1050WA`,要依 TDK SPM10065VT 的規格書焊盤圖另做(可用 Pi 轉圖)。
2. **LM5146 裸露焊盤尺寸**:LCSC 的規格書只有封裝總覽頁,沒有 RGY0020 詳圖;
   KiCad 的 `Texas_RGY_R-PVQFN-N20_EP2.05x3.05mm` 要對 TI 原檔確認(帶 wettable flank 的版本可能不同)。
3. **補償**:輸出電容改 10V(原設計 6.3V),實際容值較大 → 要模擬(ngspice)確認相位裕度。
4. **BSC070N10NS5 在 VGS 7.5V 的 RDS(on)**:限流值用估計的 6.5mΩ,要對規格書曲線。
8. **LED_nPWR**:規格書說要加緩衝,官方 IO 板仍直接帶 1k(約 1mA),照官方;料號核對後看 review 的電流結果。
10. **網口走線**:4 對 100Ω 差分、對內等長;CM5 規格書 4.2 附模組內部各腳走線長度(Pair0_P 2.92mm 等),
   等長要把它算進去。MagJack 前方要靠板邊。LED 最壞(Vf 2.8V、VOL 0.4V)電流接近 0,實際約 2mA。
11. **LAN7800 庫存**:JLC C633489 只剩 89 顆(打樣夠);量產前另找料源或改用規格書公開的替代晶片。
12. **LAN7800 LED**:沒有 EEPROM / OTP 設定時 LED0/LED1 是否預設啟用,要對 Linux lan78xx 驅動;
    必要時在 OTP 寫 LED 設定。MAC 寫 OTP 的流程寫進韌體交接。
13. **LAN7800 封裝**:KiCad `QFN-48-1EP_7x7mm_P0.5mm_EP5.3x5.3mm` 焊盤寬 0.25,規格書建議 0.28(晶片腳 0.18–0.30),
    排距 6.9、EP 5.3 一致。1.2V 電感 MPIH252012-3R3M(C490457)電流額定要對 LAN7800 1.2V 負載確認。
9. **CM5_1V8** 目前沒有負載(只有兩支輸出腳互接),之後用不到就維持這樣。
6. **TPS568230 封裝**:KiCad 內建 `Texas_RJE0020A`(EP 0.675 × 0.76mm,多塊散熱焊盤)要對 TI 原始 RJE 圖面;
   JLC 標 VQFN-20-EP(3x3)。
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
