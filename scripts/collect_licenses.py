"""Collect installed dependency notices for release alongside the frozen EXE."""
from importlib import metadata
from pathlib import Path
import sys

output = Path(sys.argv[1])
sections = []
for name in ["customtkinter", "darkdetect", "packaging", "pillow", "pyinstaller", "pyinstaller-hooks-contrib"]:
    distribution = metadata.distribution(name)
    notices = []
    for item in distribution.files or []:
        if item.name.lower().startswith(("license", "copying", "notice", "copyright", "ofl")):
            file = Path(distribution.locate_file(item))
            if file.is_file():
                notices.append(f"--- {item} ---\n{file.read_text(encoding='utf-8', errors='replace')}")
    if not notices:
        raise RuntimeError(f"No license file found for {name}; inspect package before distribution")
    sections.append(f"=== {name} {distribution.version} ===\n" + "\n".join(notices))
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if not python_license.is_file():
    python_license = Path(sys.base_prefix) / "LICENSE"
if not python_license.is_file() and sys.platform == "linux":
    python_license = Path("/usr/share/doc") / f"python{sys.version_info.major}.{sys.version_info.minor}" / "copyright"
if not python_license.is_file():
    raise RuntimeError("Python license file missing; inspect runtime before distribution")
sections.append("=== Python runtime ===\n" + python_license.read_text(encoding="utf-8", errors="replace"))
# Windows Python installs Tcl/Tk notices separately when available.
for file in (Path(sys.base_prefix) / "tcl").glob("**/license*"):
    if file.is_file():
        sections.append(f"=== {file.relative_to(sys.base_prefix)} ===\n" + file.read_text(encoding="utf-8", errors="replace"))
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n\n".join(sections), encoding="utf-8")
print(f"Collected dependency and runtime notices: {output.name}")
