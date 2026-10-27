#!/usr/bin/env python3
"""Build dist/<skill>.zip for Agensi: the shared core and the HTML templates are inlined into the
script so it runs as a single file."""
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = ROOT.name
DIST = ROOT / "dist"
INCLUDE = ["SKILL.md", "LICENSE", "references"]
CORE_BLOCK = re.compile(r"# @@CORE-IMPORT@@.*?# @@END-CORE-IMPORT@@\n", re.S)


def main() -> None:
    out = DIST / NAME
    (out / "scripts").mkdir(parents=True, exist_ok=True)
    for item in INCLUDE:
        src = ROOT / item
        if src.is_dir():
            shutil.copytree(src, out / item, dirs_exist_ok=True)
        elif src.exists():
            shutil.copy(src, out / item)
    core = (ROOT / "scripts" / "l10n_core.py").read_text("utf-8")
    templates = {p.name: p.read_text("utf-8") for p in sorted((ROOT / "assets").glob("*.html"))} if (ROOT / "assets").exists() else {}
    marker = '\n\nif __name__ == "__main__":'
    for script in sorted((ROOT / "scripts").glob("*.py")):
        if script.name == "l10n_core.py":
            continue
        code = script.read_text("utf-8")
        if not CORE_BLOCK.search(code):
            raise SystemExit(f"{script.name}: core import block not found")
        code = CORE_BLOCK.sub(lambda m: core + "\n", code, count=1)
        if templates:
            block = "\n\n# HTML templates, embedded so this script runs as a single file.\nEMBEDDED_TEMPLATES = " + json.dumps(templates, ensure_ascii=False) + "\n"
            code = code.replace(marker, block + marker, 1)
        (out / "scripts" / script.name).write_text(code, "utf-8")
    zpath = DIST / f"{NAME}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(DIST))
    print(f"built {zpath.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
