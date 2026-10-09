"""Locate a KiCad 10 installation.

Override with environment variables when KiCad lives somewhere else:
    KICAD_SHARE  the 'share/kicad' directory (contains symbols/ and footprints/)
    KICAD_BIN    the directory containing kicad-cli and KiCad's bundled python
"""
import os
import sys
from pathlib import Path


def _candidates_share() -> list[Path]:
    out = []
    if os.environ.get("KICAD_SHARE"):
        out.append(Path(os.environ["KICAD_SHARE"]))
    if sys.platform == "win32":
        for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs", os.environ.get("ProgramFiles", "")):
            if base:
                out.append(Path(base) / "KiCad" / "10.0" / "share" / "kicad")
    elif sys.platform == "darwin":
        out.append(Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
    else:
        out += [Path("/usr/share/kicad"), Path("/usr/local/share/kicad")]
    return out


def _candidates_bin() -> list[Path]:
    out = []
    if os.environ.get("KICAD_BIN"):
        out.append(Path(os.environ["KICAD_BIN"]))
    if sys.platform == "win32":
        for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs", os.environ.get("ProgramFiles", "")):
            if base:
                out.append(Path(base) / "KiCad" / "10.0" / "bin")
    return out


def kicad_share() -> Path:
    for p in _candidates_share():
        if (p / "symbols").is_dir():
            return p
    raise SystemExit("KiCad 10 'share/kicad' not found; set KICAD_SHARE")


def kicad_bin() -> Path:
    for p in _candidates_bin():
        if (p / ("kicad-cli.exe" if sys.platform == "win32" else "kicad-cli")).exists():
            return p
    raise SystemExit("KiCad 10 bin directory not found; set KICAD_BIN")
