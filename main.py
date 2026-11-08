from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_tk_runtime() -> None:
    python_root = Path(sys.executable).resolve().parent
    application_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        application_root / "tcl8.6",
        python_root / "tcl" / "tcl8.6",
        python_root / "lib" / "tcl8.6",
    ]
    tk_candidates = [
        application_root / "tk8.6",
        python_root / "tcl" / "tk8.6",
        python_root / "lib" / "tk8.6",
    ]

    if "TCL_LIBRARY" not in os.environ:
        for path in candidates:
            if (path / "init.tcl").exists():
                os.environ["TCL_LIBRARY"] = str(path)
                break
    if "TK_LIBRARY" not in os.environ:
        for path in tk_candidates:
            if (path / "tk.tcl").exists():
                os.environ["TK_LIBRARY"] = str(path)
                break


_bootstrap_tk_runtime()

from statin_nhi.ui import run


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from statin_nhi.smoke import run_smoke
        run_smoke(Path(sys.argv[2]))
    else:
        run()
