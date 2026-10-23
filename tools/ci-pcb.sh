#!/usr/bin/env bash
# PCB half of every board's build, for CI (Linux, KiCad 10 from the kicad PPA, Java 25 on PATH).
# Mirrors boards/*/build.ps1 from placement to fab: place -> DSN -> freerouting -> import -> DRC
# -> fab. Run tools/ci-schematic.sh first (it writes net.txt).
#
#   bash tools/ci-pcb.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export KICAD_BIN=${KICAD_BIN:-$(dirname "$(command -v kicad-cli)")}

FR=tools/freerouting/freerouting-2.5.0.jar
FR_SHA=f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7
if ! echo "$FR_SHA  $FR" | sha256sum -c --quiet 2>/dev/null; then
    mkdir -p "$(dirname "$FR")"
    curl -fsSL -o "$FR" https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar
    echo "$FR_SHA  $FR" | sha256sum -c --quiet
fi
FR=$(realpath "$FR")

# Same settings as Invoke-Freerouting in lib/env.ps1.
autoroute() {  # dsn ses passes allowed_unrouted [extra args...]
    local dsn=$1 ses=$2 passes=$3 allow=$4; shift 4
    java -jar "$FR" -de "$dsn" -do "$ses" "--router.autorouter.max_passes=$passes" \
        --gui.enabled=false --router.copper_to_edge_clearance_um=500 \
        --router.optimizer.max_threads=1 "$@" > freerouting.log 2>&1 || { tail -40 freerouting.log; return 1; }
    local line n
    line=$(grep 'Auto-routing stage completed' freerouting.log | tail -1)
    echo "  ${line#*completed:}"
    n=$(sed -nE 's/.*\(([0-9]+) unrouted.*/\1/p' <<< "$line")
    [ -n "$n" ] && [ "$n" -le "$allow" ] || { echo "freerouting left $n unrouted (allowed $allow)"; return 1; }
}

drc() {  # board severity
    kicad-cli pcb drc "--severity-$2" --schematic-parity --exit-code-violations -o drc.rpt "$1.kicad_pcb" ||
        { cat drc.rpt; return 1; }
    grep '^\*\* Found' drc.rpt | sed 's/^/  /'
}

NECK=(--router.automatic_neckdown=false --router.neck_width_um=150)

board() {
    local b=$1
    echo "::group::$b"
    cd "boards/$b"
    case $b in
        usbc-ldo)
            python3 gen/pcb.py
            python3 ../../lib/route.py dsn "$b" .
            autoroute "$b.dsn" "$b.ses" 30 0
            python3 ../../lib/route.py ses "$b" .
            drc "$b" all ;;
        esp32c3)
            python3 gen/pcb.py
            python3 ../../lib/route.py dsn "$b" .
            autoroute "$b.dsn" "$b.ses" 50 0 "${NECK[@]}"
            python3 ../../lib/route.py ses "$b" .
            drc "$b" all ;;
        relay8)  # the 16 mains connections are drawn by gen/pcb.py, not freerouting
            python3 gen/pcb.py place
            python3 ../../lib/route.py dsn "$b" .
            autoroute "$b.dsn" "$b.ses" 60 16 "${NECK[@]}"
            python3 ../../lib/route.py ses "$b" .
            python3 gen/pcb.py finish
            drc "$b" error ;;
        cm5)  # placed but not routed yet: every DRC error except unconnected pads is a failure
            python3 gen/pcb.py
            kicad-cli pcb drc --severity-error --schematic-parity -o drc.rpt "$b.kicad_pcb"
            if grep '^\[' drc.rpt | grep -v '^\[unconnected_items\]'; then cat drc.rpt; return 1; fi
            grep '^\*\* Found' drc.rpt | sed 's/^/  /'
            cd ../..
            echo "::endgroup::"
            return ;;
    esac
    python3 ../../lib/fab.py "$b" .
    cd ../..
    echo "::endgroup::"
}

for b in usbc-ldo esp32c3 relay8 cm5; do board "$b"; done
