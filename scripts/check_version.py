"""Fail CI when Android, Python packaging, or API drift from root VERSION."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
checks = {
    "VERSION": bool(version),
    "backend dynamic version": 'version = {attr = "gulyay.version.__version__"}' in (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"),
    "android versionName": "versionName appVersion" in (ROOT / "app" / "build.gradle").read_text(encoding="utf-8"),
    "android version source": "file('VERSION').getText('UTF-8').trim()" in (ROOT / "app" / "build.gradle").read_text(encoding="utf-8"),
    "backend version source": ' / "VERSION").read_text(encoding="utf-8").strip()' in (ROOT / "backend" / "gulyay" / "version.py").read_text(encoding="utf-8"),
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    print("Version configuration check failed: " + ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print(f"Version configuration OK: {version}")
