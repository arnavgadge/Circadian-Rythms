"""Phase 18 release utility: SHA-256 checksums for release-critical files.

Run standalone (``python -m scripts.generate_checksums``) to regenerate
``release/checksums.sha256`` from the current state of the frozen model
artifacts and key release documents. This does not train, evaluate, or
modify anything -- it only hashes files that already exist.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Release-critical files whose exact bytes should be identifiable later.
# Large per-participant/window datasets under data/ are intentionally
# excluded -- they are regenerable from the pinned synthetic seed, not
# unique artifacts that need a fixed checksum.
CHECKSUM_TARGETS = [
    "models/xgboost_dlmo_cos_v1.pkl",
    "models/xgboost_dlmo_sin_v1.pkl",
    "models/model_metadata_v1.json",
    "requirements-lock.txt",
    "frontend/package-lock.json",
    "release/version_manifest.json",
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    lines = [
        "# CircadianIQ release checksums (SHA-256)",
        "# Regenerate with: python -m scripts.generate_checksums",
        "",
    ]
    missing = []
    for rel_path in CHECKSUM_TARGETS:
        path = PROJECT_ROOT / rel_path
        if not path.exists():
            missing.append(rel_path)
            continue
        lines.append(f"{sha256_of(path)}  {rel_path}")

    out_path = PROJECT_ROOT / "release" / "checksums.sha256"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_path} ({len(lines) - 2} files hashed)")
    if missing:
        print("Skipped (not found yet -- generate first, then rerun):")
        for m in missing:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
