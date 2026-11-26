"""cm5 分阶段自动布线:cm5.kicad_pcb(gen/pcb.py 的输出)→ cm5-routed.kicad_pcb。

用 KiCad 自带的 python.exe 跑(要 pcbnew),约 2–3 小时:
    python.exe gen/route_stages.py [--keep]

整板一次交给 freerouting 不收敛(每轮约 10 分钟,未布通在 107–154 之间摆荡),所以分批:
  1. 关键网(晶振、回授、LAN7800 的 REXT/1V2/2V5/SW)先在几乎空的板上布好、锁定;
  2. 其余未接的网按类别间距分组(同一批的间距取组内最大,见 lib/route.py only_nets),
     每组一批,布完锁定;重复到未接数不再下降。
每批:lib/route.py dsn(只留这批网)→ freerouting → lib/route.py lock。
同一台机器结果可重现(freerouting 单线程、DSN 照固定 UUID 排序)。
工作目录 route/ 留着每批的 DSN、SES、freerouting 日志;--keep 不清掉旧的工作目录。
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pcbnew

BOARD = Path(__file__).resolve().parent.parent
REPO = BOARD.parent.parent
NAME = "cm5"
WORK = BOARD / "route"
OUT = BOARD / f"{NAME}-routed.kicad_pcb"
CLI = Path(sys.executable).with_name("kicad-cli.exe")
JAR = REPO / "tools" / "freerouting" / "freerouting-2.6.0.jar"

# 第一阶段:先占位置的关键网与 freerouting 轮数。顺序有关系:晶振最短最挤,回授网其次。
CRITICAL = [
    ("HUB_XI,HUB_XO", 10),
    ("FB,FB3,COMP,FB_FF", 15),
    ("LAN0_REXT,LAN1_REXT,LAN0_RBIAS,LAN1_RBIAS,LAN0_FILT,LAN1_FILT,"
     "RT,SS,ILIM,EN_UVLO,MODE3,VCC3,COMP_RC", 15),
    ("LAN0_SW,LAN1_SW,LAN0_1V2,LAN1_1V2,LAN0_2V5,LAN1_2V5", 25),
]
REST_PASSES = 30
MAX_ROUNDS = 6
UNCONNECTED_RE = re.compile(r"^\s+@\([^)]*\): .*?\[([^\]]+)\]")


def run(cmd, log=None):
    r = subprocess.run([str(c) for c in cmd], cwd=WORK, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if log:
        (WORK / log).write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        sys.exit(f"{cmd[0]} 失败(exit {r.returncode}):\n{(r.stdout + r.stderr)[-2000:]}")
    return r.stdout


def java():
    found = sorted((REPO / "tools" / "jre").glob("*/bin/java.exe"))
    if not found or not JAR.exists():
        sys.exit("缺 freerouting 或 Java 25:先跑 tools/setup-tools.ps1")
    return found[0]


def stage(nets: str, passes: int, n: int) -> None:
    route = [sys.executable, REPO / "lib" / "route.py"]
    run(route + ["dsn", NAME, ".", nets])
    log = f"fr-{n:02d}.log"
    run([java(), "-jar", JAR, "-de", f"{NAME}.dsn", "-do", f"{NAME}.ses",
         f"--router.autorouter.max_passes={passes}", "--gui.enabled=false",
         "--router.copper_to_edge_clearance_um=500", "--router.optimizer.max_threads=1",
         "--router.automatic_neckdown=false", "--router.neck_width_um=100"], log=log)
    score = re.findall(r"final score: .*?\((\d+) unrouted", (WORK / log).read_text(encoding="utf-8"))
    out = run(route + ["lock", NAME, "."])
    left = score[-1] if score else "?"
    print(f"  批 {n:02d}:{len(nets.split(','))} 个网,freerouting 剩 {left};{out.strip().splitlines()[-1]}",
          flush=True)


def unconnected() -> tuple:
    """DRC 报的未接:(未接数, 涉及的网)。网名取每个未接项两端的 [网]。"""
    run([CLI, "pcb", "drc", "-o", "drc.rpt", f"{NAME}.kicad_pcb"])
    text = (WORK / "drc.rpt").read_text(encoding="utf-8")
    count = int(re.search(r"\*\* Found (\d+) unconnected pads", text).group(1))
    nets, inside = set(), False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.startswith("[unconnected_items]")
        elif inside:
            m = UNCONNECTED_RE.match(line)
            if m:
                nets.add(m.group(1))
    return count, nets


def by_clearance(nets: set) -> list:
    """按类别间距分组(小的先布):同一批的间距取组内最大,混在一起会让细间距的网出不了脚。"""
    board = pcbnew.LoadBoard(str(WORK / f"{NAME}.kicad_pcb"))
    clear = {}
    for p in board.GetPads():
        n = p.GetNetname()
        if n in nets:
            clear[n] = max(clear.get(n, 0), p.GetOwnClearance(pcbnew.F_Cu))
    groups = {}
    for n in sorted(nets):
        groups.setdefault("GND" if n == "GND" else clear.get(n, 0), []).append(n)
    order = sorted((k for k in groups if k != "GND"))
    return [",".join(groups[k]) for k in order] + ([groups["GND"][0]] if "GND" in groups else [])


def main():
    if not (BOARD / f"{NAME}.kicad_pcb").exists():
        sys.exit("先跑 build.ps1(gen/pcb.py)产生 cm5.kicad_pcb")
    if "--keep" not in sys.argv and WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(exist_ok=True)
    for ext in ("kicad_pcb", "kicad_pro", "kicad_dru"):
        shutil.copy(BOARD / f"{NAME}.{ext}", WORK / f"{NAME}.{ext}")
    n = 0
    print("== 关键网", flush=True)
    for nets, passes in CRITICAL:
        n += 1
        stage(nets, passes, n)
    best, nets = unconnected()
    print(f"  未接 {best}", flush=True)
    for r in range(1, MAX_ROUNDS + 1):
        # NC 脚被并成一个网的(unconnected-(…))也交给 freerouting:两个 NC 脚连起来无害
        print(f"== 第 {r} 轮:{len(nets)} 个网", flush=True)
        for group in by_clearance(nets):
            n += 1
            stage(group, REST_PASSES, n)
        count, nets = unconnected()
        print(f"  未接 {count}", flush=True)
        if count == 0 or count >= best:
            break
        best = count
    shutil.copy(WORK / f"{NAME}.kicad_pcb", OUT)
    # 网路类别存在 .kicad_pro、板子规则在 .kicad_dru;KiCad 只读同名的那两个档,
    # 少了它们打开 cm5-routed 或跑 DRC 会套预设规则(线宽 0.2、间距 0.2)报一堆假错误
    for ext in ("kicad_pro", "kicad_dru"):
        shutil.copy(BOARD / f"{NAME}.{ext}", OUT.with_suffix(f".{ext}"))
    print(f"wrote {OUT.name}:未接 {count}")


if __name__ == "__main__":
    main()
