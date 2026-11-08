"""Check the tracked release tree; this is not a complete secret/history audit."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
paths = [p for p in subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0") if p]
errors = []
private_names = {"Statin_NHI_available.json", "Statin_NHI_reminders.json", ".env"}
for name in paths:
    path = Path(name)
    if (path.parts[0] in {"dist", ".tk-runtime", ".venv", "private", "work"}
            or path.name in private_names
            or path.suffix.lower() in {".exe", ".pfx", ".p12", ".key", ".pem"}):
        errors.append(f"Private or generated tracked file: {name}")
    source = root / path
    if source.suffix.lower() in {".py", ".md", ".json", ".yml", ".csv"} and source.is_file():
        data = source.read_text(encoding="utf-8-sig")
        # Match common credential formats without displaying the candidate value.
        patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                    r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"\bAKIA[0-9A-Z]{16}\b"]
        if any(re.search(pattern, data) for pattern in patterns):
            errors.append(f"Potential credential in {name}; value suppressed")
for required in ["LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "SECURITY.md",
                 "CONTRIBUTING.md", "examples/Statin_NHI_available.example.json"]:
    if required not in paths:
        errors.append(f"Required public file not tracked: {required}")
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f"Public-tree checks passed: {len(paths)} tracked files (not a full security audit).")
