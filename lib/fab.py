"""製造檔:Gerber + 鑽孔(打包成 zip)、JLCPCB 格式的 BOM 與 CPL(座標檔),並自檢。

    python lib/fab.py <板名> <板目錄>        (用 KiCad 自帶的 python,要 pcbnew)

輸出在 <板目錄>/fab/:
  <板>-gerber.zip   銅、阻焊、錫膏、絲印、板框 + Excellon 鑽孔(PTH/NPTH 分檔)
  <板>-bom.csv          Comment, Designator, Footprint, LCSC Part #(只列交給 JLC 貼的件)
  <板>-cpl.csv          Designator, Mid X, Mid Y, Layer, Rotation(套用 lib/jlc_rotations.json)
  hand-solder.csv       LCSC 買不到、要自購手焊的件
  rotation-review.csv   每顆件的角度與依據,上傳後在 JLC 貼片預覽逐顆對照
  groups.json           「值|封裝」→ 位號,給 lib/lcsc.py 算數量

料號只讀 <板目錄>/lcsc-check.json(lib/lcsc.py 連線核對 lcsc.json 後寫出,含雜湊)。
沒核對、或 lcsc.json 改過沒重新核對、或有任何一列沒有料號也沒標明不貼 → 不寫 zip。

自檢(任何一項不過就回傳 1、不寫 zip):
  - 必要的 Gerber 層都有、而且不是空檔
  - 鑽孔檔的孔數 = 板檔裡的過孔 + 有孔焊盤數
  - CPL 的位號集合 = BOM 的位號集合 = 板上封裝的位號集合
  - 符號庫自帶預設封裝(具體型號,不是 Device:R 這種通用件)時,實際封裝必須相同。
    踩過:三塊板都用 USBLC6-2P6(SOT-666)的符號配 SOT-23-6 封裝 → 電氣沒錯
    (兩型號腳位相同),但 BOM 照值買會買到貼不上的料。ERC / DRC / 網表比對都抓不到。

不檢查、送廠前要人工看的:JLCPCB 對部分封裝的 0° 定義與 KiCad 不同。jlc_rotations.json
是社群整理的修正表,本專案沒有實物驗證 → rotation-review.csv 每一列都標「未確認」。
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcbnew  # noqa: E402
from kicad_paths import kicad_bin  # noqa: E402
from lcsc import lcsc_hash  # noqa: E402

CLI = str(kicad_bin() / ("kicad-cli.exe" if sys.platform == "win32" else "kicad-cli"))
LAYERS = ["F.Cu", "B.Cu", "F.Mask", "B.Mask", "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"]
# 一定要有內容的層(錫膏、底層絲印在純插件或單面件的板上可以是空的)
MUST_HAVE_CONTENT = ["F.Cu", "B.Cu", "F.Mask", "B.Mask", "Edge.Cuts"]


def run(*args: str) -> None:
    r = subprocess.run([CLI, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"kicad-cli {' '.join(args[:3])} 失敗(exit {r.returncode}):\n{r.stdout}{r.stderr}")


def sexpr(text: str):
    """最小的 S-expression 解析:回傳巢狀 list,字串去掉引號。"""
    tok = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')
    stack: list[list] = [[]]
    for m in tok.finditer(text):
        t = m.group()
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t[1:-1].replace('\\"', '"') if t.startswith('"') else t)
    return stack[0][0]


def props(node: list) -> dict[str, str]:
    return {c[1]: c[2] for c in node if isinstance(c, list) and c and c[0] == "property"}


def footprint_mismatches(sch_text: str) -> list[str]:
    root = sexpr(sch_text)
    lib_fp: dict[str, str] = {}
    for c in root:
        if isinstance(c, list) and c and c[0] == "lib_symbols":
            for s in c[1:]:
                lib_fp[s[1]] = props(s).get("Footprint", "")
    out = []
    for c in root:
        if not (isinstance(c, list) and c and c[0] == "symbol"):
            continue
        lib_id = next(x[1] for x in c if isinstance(x, list) and x[0] == "lib_id")
        p = props(c)
        want, got = lib_fp.get(lib_id, ""), p.get("Footprint", "")
        if want and got and want != got and not p.get("Reference", "#").startswith("#"):
            out.append(f"{p['Reference']} 符號 {lib_id} 的封裝是 {want},實際用 {got}(型號和封裝對不上?)")
    return out


def gerber_has_content(p: Path) -> bool:
    """有任何 D01(畫線)/ D03(閃光)指令才算有內容;只有表頭的檔案不算。"""
    return re.search(r"D0?[13]\*", p.read_text(encoding="utf-8", errors="replace")) is not None


def drill_hits(p: Path) -> int:
    """Excellon:表頭之後,每一行 X…Y… 是一個圓孔;槽孔是 route 格式
    (G00X…Y… → M15 → G01X…Y… → M16),以 G00 那行算一個。"""
    body = p.read_text(encoding="utf-8", errors="replace").split("%", 1)[-1]
    return sum(1 for line in body.splitlines() if re.match(r"^(G00)?X[-\d.]+Y[-\d.]+$", line))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    name, bdir = sys.argv[1], Path(sys.argv[2]).resolve()
    pcb, sch = bdir / f"{name}.kicad_pcb", bdir / f"{name}.kicad_sch"
    out = bdir / "fab"
    gdir = out / "gerber"
    gdir.mkdir(parents=True, exist_ok=True)
    for old in gdir.iterdir():
        old.unlink()
    problems: list[str] = footprint_mismatches(sch.read_text(encoding="utf-8"))

    # ── Gerber + 鑽孔 ──
    run("pcb", "export", "gerbers", "-o", str(gdir) + "/", "-l", ",".join(LAYERS), "--subtract-soldermask",
        "--check-zones", str(pcb))
    run("pcb", "export", "drill", "-o", str(gdir) + "/", "--format", "excellon", "--excellon-units", "mm",
        "--excellon-separate-th", "--excellon-oval-format", "route", str(pcb))
    files = sorted(gdir.iterdir())
    for layer in LAYERS:
        stem = layer.replace(".", "_")
        hit = [p for p in files if p.stem.endswith(stem)]
        if not hit:
            problems.append(f"缺 Gerber 層 {layer}")
        elif layer in MUST_HAVE_CONTENT and not gerber_has_content(hit[0]):
            problems.append(f"Gerber 層 {layer} 是空的")

    board = pcbnew.LoadBoard(str(pcb))
    vias = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    holes = sum(1 for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetDrillSize().x > 0 and pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH))
    drills = [p for p in files if p.suffix.lower() == ".drl"]
    hits = sum(drill_hits(p) for p in drills)
    if hits != vias + holes:
        problems.append(f"鑽孔檔 {hits} 個孔,板檔有 {vias} 過孔 + {holes} 有孔焊盤 = {vias + holes}")

    (out / "missing-lcsc.txt").unlink(missing_ok=True)   # 舊版留下的

    # ── 讀 BOM 分組(原理圖)──
    raw = out / "bom-raw.csv"
    run("sch", "export", "bom", "-o", str(raw), "--fields", "Reference,Value,Footprint",
        "--labels", "Ref,Value,Footprint", "--group-by", "", "--ref-range-delimiter", "", str(sch))
    natural = lambda s: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]  # noqa: E731
    groups: dict[str, list[str]] = defaultdict(list)
    with raw.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            for ref in r["Ref"].split(","):
                ref = ref.strip()
                if ref and not ref.startswith("#"):
                    groups[f"{r['Value']}|{r['Footprint']}"].append(ref)
    raw.unlink()
    groups = {k: sorted(v, key=natural) for k, v in sorted(groups.items(), key=lambda kv: natural(min(kv[1], key=natural)))}
    # lcsc.py 用這份算每列數量
    (out / "groups.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ── 料號:只吃 lcsc.py 核對過的結果 ──
    parts: dict[str, dict] = {}
    lcsc_file, check_file = bdir / "lcsc.json", bdir / "lcsc-check.json"
    if not lcsc_file.exists():
        problems.append("沒有 lcsc.json(每一列「值|封裝」都要有料號或標明不貼)")
    elif not check_file.exists():
        problems.append("lcsc.json 還沒核對過:跑 python lib/lcsc.py <板目錄>")
    else:
        chk = json.loads(check_file.read_text(encoding="utf-8"))
        if chk["lcsc_json_sha256"] != lcsc_hash(lcsc_file.read_text(encoding="utf-8")):
            problems.append("lcsc.json 改過但沒重新核對:跑 python lib/lcsc.py <板目錄>")
        parts = chk["parts"]
    for k in groups:
        if parts and k not in parts:
            problems.append(f"lcsc-check.json 沒有 {k}({', '.join(groups[k])})")
    for k in parts:
        if k not in groups:
            problems.append(f"lcsc-check.json 有一列板上沒有:{k}(值或封裝改過?)")

    bom_rows, hand_rows, assembled = [], [], set()
    for k, refs in groups.items():
        val, fpn = k.split("|", 1)
        p = parts.get(k, {})
        if p.get("assemble") is False:
            hand_rows.append([val, ",".join(refs), fpn.split(":")[-1], p["reason"], p.get("buy", "")])
        else:
            bom_rows.append([val, ",".join(refs), fpn.split(":")[-1], p.get("lcsc", "")])
            assembled.update(refs)
    with (out / f"{name}-bom.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        w.writerows(bom_rows)
    hand_file = out / "hand-solder.csv"
    if hand_rows:
        with hand_file.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["值", "位號", "封裝", "不交給 JLC 貼的原因", "自購"])
            w.writerows(hand_rows)
    elif hand_file.exists():
        hand_file.unlink()

    # ── CPL(只列要貼的件)+ 旋轉修正 ──
    rules = json.loads((Path(__file__).resolve().parent / "jlc_rotations.json").read_text(encoding="utf-8"))
    pos = out / "pos.csv"
    run("pcb", "export", "pos", "-o", str(pos), "--format", "csv", "--units", "mm", "--side", "both", str(pcb))
    cpl_rows, review = [], []
    with pos.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["Ref"] not in assembled:
                continue
            rule = next((x for x in rules["rules"] if re.search(x["pattern"], r["Package"])), None)
            corr = rule["rotation"] if rule else 0
            rot = (float(r["Rot"]) + corr) % 360
            side = "Top" if r["Side"] == "top" else "Bottom"
            cpl_rows.append([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm", side, f"{rot:g}"])
            review.append([r["Ref"], r["Package"], side, f"{float(r['Rot']) % 360:g}", f"{corr:+g}", f"{rot:g}",
                           rule["status"] if rule else "沒有修正資料,照 KiCad 角度"])
    pos.unlink()
    cpl_rows.sort(key=lambda x: natural(x[0]))
    review.sort(key=lambda x: natural(x[0]))
    with (out / f"{name}-cpl.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(cpl_rows)
    with (out / "rotation-review.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["位號", "KiCad 封裝", "面", "KiCad 角度", "修正", "CPL 角度", "依據(上傳後在 JLC 貼片預覽逐顆確認)"])
        w.writerows(review)

    # ── 位號一致:BOM = CPL,BOM ∪ 手焊 = 板上 ──
    on_board = {fp.GetReference() for fp in board.GetFootprints()}
    in_cpl = {r[0] for r in cpl_rows}
    in_hand = {ref for r in hand_rows for ref in r[1].split(",")}
    if in_cpl != assembled:
        problems.append(f"CPL 與 BOM 不一致:CPL 多 {sorted(in_cpl - assembled)}、少 {sorted(assembled - in_cpl)}")
    if assembled | in_hand != on_board:
        s = assembled | in_hand
        problems.append(f"BOM + 手焊 與板上封裝不一致:多 {sorted(s - on_board)}、少 {sorted(on_board - s)}")

    n_gbr = sum(1 for p in files if p.suffix.lower() not in (".drl", ".gbrjob"))
    print(f"  Gerber {n_gbr} 層 + 鑽孔 {len(drills)} 檔({hits} 孔 = {vias} 過孔 + {holes} 焊盤孔)")
    print(f"  BOM {len(bom_rows)} 列 / {len(assembled)} 件交給 JLC 貼,CPL {len(cpl_rows)} 件"
          + (f";自購手焊 {len(hand_rows)} 列 / {len(in_hand)} 件(fab/hand-solder.csv)" if hand_rows else ""))
    unreviewed = sum(1 for r in review if not r[6].startswith("已確認"))
    print(f"  旋轉角:{unreviewed}/{len(review)} 件未經確認,清單在 fab/rotation-review.csv")
    if problems:
        for p in problems:
            print("  ✗ " + p)
        return 1

    zpath = out / f"{name}-gerber.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
    print(f"  → {zpath.relative_to(bdir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
