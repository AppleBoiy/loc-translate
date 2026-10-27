import importlib.util
import io
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def load_script(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Project:
    """A temp copy of one fixture project (mods/ or app/)."""

    def __init__(self, which="mods"):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / which
        shutil.copytree(FIX / which, self.root)

    def run(self, mod, *args):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                mod.main(list(args) + ["--root", str(self.root)])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
        return code, out.getvalue() + err.getvalue()

    def i18n(self, name):
        return next(self.root.glob(f"**/i18n/{name}"))

    def close(self):
        self.tmp.cleanup()
