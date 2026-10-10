# ESP32-C3 minimal board — firmware handoff

Everything a firmware developer needs without opening the schematic.

## Module

ESP32-C3-WROOM-02-N4: RISC-V @ 160 MHz, 4 MB flash, Wi-Fi 2.4 GHz + Bluetooth 5 LE, PCB antenna.

## Pin map

| GPIO | Function on this board | Notes |
|---|---|---|
| IO18 / IO19 | USB D− / D+ (USB-C) | Native USB Serial/JTAG. Do not use as GPIO. |
| IO20 / IO21 | UART0 RX / TX | Also on header J2 pins 4 / 3 |
| IO10 | Yellow user LED (D2), active **high**, via 470 Ω | |
| IO4 – IO7 | Header J2 pins 5 – 8 | Free GPIO, 3.3 V logic |
| IO9 | BOOT button (SW2) to GND, 10 kΩ pull-up | Strapping pin: low at reset = download mode |
| IO8 | 10 kΩ pull-up | Strapping pin: must be high at reset. Avoid as output. |
| IO2 | 10 kΩ pull-up | Strapping pin: must be high at reset. Avoid as output. |
| EN | RESET button (SW1), 10 kΩ + 1 µF RC | |
| IO0, IO1, IO3 | Not connected | |

Header J2 (1×8, 2.54 mm): 1 3V3 · 2 GND · 3 TXD · 4 RXD · 5 IO4 · 6 IO5 · 7 IO6 · 8 IO7

## Power

- USB-C 5 V → LP38693MP-3.3 LDO (500 mA, ~330 mV dropout, 12 V absolute maximum input). The green LED D3 shows 3V3 is up.
- VBUS soft-start: P-MOSFET Q1 (AO3401A) between VBUS and the LDO, gate RC R9 100k / C6 100nF / C7 10nF. Without it the module's own ~12 µF plus C2 drew ~79 µC on hot-plug (USB 2.0 limit 50 µC). Simulated (`sim/softstart_sim.py`): ramp current 80–97 mA, 3V3 ready in 1.3–3.7 ms across the MOSFET's threshold range. Replugging within ~10 ms of unplugging skips part of the soft-start (C6 discharges through R9).
- Budget for J2's 3V3 pin: roughly 600 mA minus the module (Wi-Fi TX peaks ~350 mA) → keep external loads under ~200 mA.
- There is no battery input and no 5 V on the header.

## Flashing

- Plug in USB-C. It enumerates as "USB JTAG/serial debug unit" (no driver needed on Windows 10+, Linux, macOS).
- Arduino IDE / arduino-esp32: board **ESP32C3 Dev Module**, *USB CDC On Boot: Enabled*, flash size 4 MB.
- ESP-IDF: `idf.py -p COMx flash monitor` with target `esp32c3`.
- If the port does not appear (e.g. the running firmware broke USB): hold **BOOT**, press and release **RESET**, release **BOOT** → download mode.

## First program (Arduino)

```cpp
const int LED = 10;  // yellow user LED, active high

void setup() {
  pinMode(LED, OUTPUT);
  Serial.begin(115200);  // goes over native USB with "USB CDC On Boot" enabled
}

void loop() {
  digitalWrite(LED, HIGH);
  Serial.println("on");
  delay(500);
  digitalWrite(LED, LOW);
  delay(500);
}
```

## Things that will bite you

- Do not drive IO2, IO8 or IO9 low during reset: the chip will not boot from flash.
- Re-using IO18/IO19 as GPIO disconnects USB, and the board then needs the BOOT/RESET sequence to flash again.
