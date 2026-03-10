#!/usr/bin/env python3
"""Wrapper for the shared CodeGuard bundle installer."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from install_bundle import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
