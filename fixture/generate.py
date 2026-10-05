"""Trusted synthetic fixture generator; run only inside the lab's own copy."""
from pathlib import Path

value = Path("value.txt").read_text(encoding="ascii").strip()
if value not in {"11", "29"}:
    raise SystemExit("Expected the fixture value 11 or 29")
Path("generated.h").write_text(f"#define FIXTURE_VALUE {value}\n", encoding="ascii")
