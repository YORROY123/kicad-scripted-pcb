# Contributing

Thanks for looking. Issues and pull requests are welcome in English or Chinese
(中文討論也歡迎). Code comments in `lib/` are mostly Chinese; English comments are fine in new code.

## The one rule

**Every check must be shown to fail.** A check that has never caught anything might not work. When
you add a rule or a self-check, also add a test that breaks something on purpose and confirms the
check catches it. `lib/review_test.py` and the "mutation test" notes in commit messages show how.

## Set up and build

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup-tools.ps1     # freerouting jar + Java 25, SHA-256 pinned
powershell -ExecutionPolicy Bypass -File boards\usbc-ldo\build.ps1  # smallest board, about a minute
python lib\review_test.py                                           # needs the boards built once
```

`lib/field2d_check.py` (the field solver validation) takes about 15 minutes and needs numpy and scipy.

## Adding a design-review rule (`lib/review.py`)

Good first contributions. A rule turns one datasheet requirement into a check on the netlist.

1. **Cite the source next to every number**: datasheet name, revision or table/section. Rules
   without a source will not be merged; a wrong number in a checker is worse than no checker.
2. Prefer component knowledge in the tables at the top of the file (`SOURCES`, `SUPPLY_PINS`,
   `SOURCE_RATING`, `LOADS`, `LINEAR`, ...) over special cases inside rule functions.
3. Report `OK` with the numbers when a rule passes, so `review.txt` shows what was checked.
4. Add a case to `CASES` in `lib/review_test.py` that breaks a real board so the rule fires.
5. The unmodified boards must still report 0 ERROR. If a finding is a deliberate trade-off, add it
   to `boards/<b>/review-waivers.json` with the reason. The review flags waivers that no longer
   match anything.

Ideas: I²C pull-ups present and sized for the bus speed, reverse-polarity protection on DC inputs,
MOSFET Vgs(th) vs gate-drive voltage, crystal load capacitors, ESD parts on every external connector.

## Adding a board

Copy the layout of `boards/esp32c3/`:

- `gen/board.py`: the circuit as a pin → net table using `lib/netlabel.py`. It also writes
  `expected_nets.json` for the netlist check.
- `gen/pcb.py`: a `BoardSpec` with the board size and every footprint's `(x, y, rotation)`.
- `build.ps1`: the same `Step` sequence. Keep the file ASCII-only (Windows PowerShell 5.1 reads
  BOM-less UTF-8 as ANSI).
- `lcsc.json`: one entry per `"value|footprint"` group, `{"lcsc": "C…", "model": "…"}` or
  `{"assemble": false, "reason": "…"}`. Then run `python lib/lcsc.py boards/<b>` (needs network).

A board is done when the build passes end to end: ERC 0, netlist check, review 0 ERROR, DRC 0
errors, fab self-checks.

## Pull requests

- One topic per PR. Say what you verified and how (which boards you rebuilt, which tests ran).
- Regenerated files (`.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `board-top.png`, `review.txt`,
  `lcsc-check.json`) change on every build. Commit them only when your change affects that board,
  and rebuild after rebasing on `main`.
- Keep `boards/*/fab/` out of git (it is ignored; Gerber headers carry timestamps).
- Known limits stay written down. If you find that something documented here is wrong, a PR that
  corrects the documentation is as welcome as a code fix.

## Safety

`boards/relay8` switches mains voltage. Changes to it need extra care: describe what you changed in
the mains section and why the clearance and creepage still hold. Passing DRC is not a safety review.
