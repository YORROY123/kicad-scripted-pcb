#!/usr/bin/env bash
# Schematic half of every board's build, for CI (Linux, KiCad 10 from the kicad PPA):
#   board.py -> ERC -> netlist -> netlist check -> design review, then the review mutation tests,
#   then confirm the regenerated schematics match the committed ones byte for byte.
# Placement, freerouting and DRC are not run here (they need minutes per board and a JRE).
#
#   bash tools/ci-schematic.sh
set -euo pipefail
cd "$(dirname "$0")/.."

for dir in boards/*/; do
    b=$(basename "$dir")
    echo "::group::$b"
    (
        cd "$dir"
        python3 gen/board.py
        kicad-cli sch erc --severity-all --exit-code-violations -o erc.rpt "$b.kicad_sch" ||
            { cat erc.rpt; exit 1; }
        kicad-cli sch export netlist --format kicadsexpr -o net.txt "$b.kicad_sch"
        if [ -f expected_nets.json ]; then python3 ../../lib/check_netlist.py .; fi
        python3 ../../lib/review.py .
    )
    echo "::endgroup::"
done

echo "::group::review mutation tests"
python3 lib/review_test.py
echo "::endgroup::"

# Generators are seeded, so a schematic that differs from the commit means the commit is stale
# (or a different KiCad symbol library changed an embedded symbol).
git diff --stat --exit-code -- 'boards/*/*.kicad_sch' 'boards/*/expected_nets.json' 'boards/*/review.txt'
