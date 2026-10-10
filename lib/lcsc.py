"""LCSC 料號連線核對:lcsc.json 裡人工寫的每一個料號,都去 JLCPCB 查一次實際資料。

    python lib/lcsc.py <板目錄> [--boards 5]      (要連網;KiCad 自帶的 python 也可以)

為什麼要有這一步:料號是人(或 AI)寫的,寫錯一碼板廠就照錯的料貼。這裡不信任
lcsc.json,逐筆查 JLCPCB 零件庫,對不上就回傳 1:
  - 料號存在,而且型號 = lcsc.json 寫的 "model"(人寫下「我以為它是什麼」,工具查證)
  - 庫存 ≥ 數量 × 板數
  - 封裝:能從 KiCad 封裝名推出尺寸的(0402/0805、SOT-23-6、SOT-223-5、SMA…)一定比對;
    推不出的(USB-C、模組、插件)列為「人工確認」,不算失敗
  - 數值:電阻 / 電容比對 JLC 的 Resistance / Capacitance 屬性,LED 比對顏色,
    其他零件的「值」要出現在型號裡;都不適用的要在 lcsc.json 寫 "note" 說明

結果寫到 <板目錄>/lcsc-check.json(含 lcsc.json 的雜湊)。fab.py 只吃這份:
lcsc.json 改過但沒重新核對,建置就停。所以建置本身不需要連網。

lcsc.json 格式(key 是「值|KiCad 封裝」,與 fab.py 分組一致):
  "100nF|Capacitor_SMD:C_0402_1005Metric": {"lcsc": "C1525", "model": "CL05B104KO5NNNC"}
  "CH1|TerminalBlock_…":                   {"assemble": false, "reason": "LCSC 無貨", "buy": "…"}
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

URL = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList"

# KiCad 封裝名 → JLC 封裝欄位必須符合的樣式
PACKAGE_RULES = [
    (r"_(0201|0402|0603|0805|1206|1210)_\d{4}Metric", lambda m: re.escape(m.group(1))),
    (r"^SOT-23-6$", lambda m: r"^SOT-23-6"),
    (r"^SOT-223-5$", lambda m: r"^SOT-223-5"),
    (r"^SOT-23$", lambda m: r"^SOT-23(-3)?$"),
    (r"^D_SMA$", lambda m: r"SMA"),
    (r"^SOIC-(\d+)W_", lambda m: rf"SO(IC|P)-{m.group(1)}-300mil"),
    (r"^CP_Elec_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)$",
     lambda m: rf"D{re.escape(m.group(1))}xL{re.escape(m.group(2))}mm"),
    (r"^PinHeader_1x(\d+)_P2\.54mm", lambda m: r"P=2\.54mm"),
]
COLORS = {"RED": "Red", "GREEN": "Green", "BLUE": "Blue", "YELLOW": "Yellow", "WHITE": "White"}
SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6}


def query(code: str) -> dict | None:
    body = json.dumps({"keyword": code, "currentPage": 1, "pageSize": 10}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    lst = json.load(urllib.request.urlopen(req, timeout=30))["data"]["componentPageInfo"]["list"] or []
    return next((c for c in lst if c["componentCode"] == code), None)


def si_value(s: str) -> float | None:
    """'5.1k' / '5.1kΩ' / '100nF' / '4.7uF' → 數值;'4k7' 這種寫法不支援(回 None)。"""
    m = re.fullmatch(r"\s*([\d.]+)\s*([pnuµmkM]?)\s*(Ω|ohm|F)?\s*", s)
    return float(m.group(1)) * SI[m.group(2)] if m else None


def norm(s: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", s.upper())


def lcsc_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def check_entry(key: str, e: dict, refs_n: int, boards: int, c: dict) -> tuple[list[str], list[str]]:
    """回傳 (錯誤, 人工確認事項)。"""
    val, fp = key.split("|", 1)
    fpn = fp.split(":")[-1]
    errs, manual = [], []
    if not c["componentModelEn"].upper().startswith(e["model"].upper()):
        errs.append(f"型號是 {c['componentModelEn']},lcsc.json 寫 {e['model']}")
    need = refs_n * boards
    if c["stockCount"] < need:
        errs.append(f"庫存 {c['stockCount']} < 需要 {need}({refs_n} 顆 × {boards} 片)")
    pkg = c["componentSpecificationEn"] or ""
    for pat, mk in PACKAGE_RULES:
        m = re.search(pat, fpn)
        if m:
            if not re.search(mk(m), pkg):
                errs.append(f"封裝是 {pkg},KiCad 封裝 {fpn} 要的是 /{mk(m)}/")
            break
    else:
        manual.append(f"封裝 JLC 寫「{pkg}」,KiCad 用 {fpn},對不對要人看規格書")
    attrs = {a["attribute_name_en"]: a["attribute_value_name"] for a in c.get("attributes") or []}
    want = si_value(val)
    if fp.startswith(("Resistor_SMD:", "Capacitor_SMD:")) and want is not None:
        name = "Resistance" if fp.startswith("Resistor") else "Capacitance"
        got = si_value(attrs.get(name, ""))
        if got is None or abs(got / want - 1) > 1e-6:
            errs.append(f"{name} 是 {attrs.get(name)},值是 {val}")
    elif val.upper() in COLORS:
        if COLORS[val.upper()] not in attrs.get("Illumination Color", ""):
            errs.append(f"顏色是 {attrs.get('Illumination Color')},值是 {val}")
    elif norm(val) and norm(val) in norm(c["componentModelEn"]):
        pass
    elif not e.get("note"):
        errs.append(f"值 {val} 不在型號 {c['componentModelEn']} 裡,也沒有 note 說明為什麼對")
    return errs, manual


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    bdir = Path(sys.argv[1]).resolve()
    boards = int(sys.argv[sys.argv.index("--boards") + 1]) if "--boards" in sys.argv else 5
    text = (bdir / "lcsc.json").read_text(encoding="utf-8")
    table = json.loads(text)
    # 數量:從 net.txt(原理圖匯出的網表)按「值|封裝」分組
    from review import Netlist
    groups: dict[str, list[str]] = {}
    for ref, c in Netlist(bdir / "net.txt").comps.items():
        if not ref.startswith("#"):
            groups.setdefault(f"{c['value']}|{c['footprint']}", []).append(ref)
    out, bad = {}, 0
    for key, e in table.items():
        refs = groups.get(key)
        if refs is None:
            print(f"✗ {key}:板上沒有這個「值|封裝」(值或封裝改過?)")
            bad += 1
            continue
        if e.get("assemble") is False:
            out[key] = {"assemble": False, "reason": e["reason"], "buy": e.get("buy", "")}
            print(f"–  {key.split('|')[0]:22s} 不貼:{e['reason']}")
            continue
        c = query(e["lcsc"])
        time.sleep(0.3)
        if c is None:
            print(f"✗ {key}:JLCPCB 查不到 {e['lcsc']}")
            bad += 1
            continue
        errs, manual = check_entry(key, e, len(refs), boards, c)
        lib = {"base": "基礎", "expand": "擴展"}.get(c["componentLibraryType"], c["componentLibraryType"])
        out[key] = {"lcsc": e["lcsc"], "model": c["componentModelEn"], "package": c["componentSpecificationEn"],
                    "brand": c["componentBrandEn"], "library": c["componentLibraryType"],
                    "stock": c["stockCount"], "price": c.get("initialPrice"), "manual": manual, "errors": errs,
                    "attrs": {a["attribute_name_en"]: a["attribute_value_name"] for a in c.get("attributes") or []
                              if a["attribute_value_name"] not in ("-", "")}}
        mark = "✗" if errs else "✓"
        print(f"{mark}  {key.split('|')[0]:22s} {e['lcsc']:>9} {c['componentModelEn'][:26]:26s} "
              f"{lib} 庫存 {c['stockCount']}")
        for x in errs:
            print(f"     ✗ {x}")
        for x in manual:
            print(f"     ? {x}")
        bad += bool(errs)
    missing = sorted(set(groups) - set(table))
    for k in missing:
        print(f"✗ {k}({', '.join(groups[k])}):lcsc.json 沒有這一列")
    bad += len(missing)
    ext = sum(1 for v in out.values() if v.get("library") == "expand")
    print(f"擴展庫零件 {ext} 種(JLC 每種收一次換料費)")
    if bad:
        print(f"{bad} 項未通過,不寫 lcsc-check.json")
        return 1
    (bdir / "lcsc-check.json").write_text(json.dumps(
        {"lcsc_json_sha256": lcsc_hash(text), "checked": date.today().isoformat(), "boards": boards,
         "parts": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("→ lcsc-check.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
