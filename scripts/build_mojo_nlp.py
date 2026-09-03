"""Build and contract-check the optional Linux Mojo NLP extension."""
from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "pipeline" / "nlp" / "_mojo_nlp.mojo"
OUTPUT = ROOT / "pipeline" / "nlp" / "_mojo_nlp.so"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-available", action="store_true",
                        help="Report and exit successfully when Mojo is unavailable")
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        message = f"Mojo NLP build is supported only on Linux x86_64, not {sys.platform}/{platform.machine()}"
        if args.if_available:
            print(message)
            return 0
        raise SystemExit(message)
    mojo = shutil.which("mojo")
    if mojo is None:
        message = "Mojo compiler unavailable; Python NLP fallback remains fully supported"
        if args.if_available:
            print(message)
            return 0
        raise SystemExit(message)
    subprocess.run([mojo, "build", str(SOURCE), "--emit", "shared-lib", "-o", str(OUTPUT)],
                   check=True, cwd=ROOT)
    spec = importlib.util.spec_from_file_location("pipeline.nlp._mojo_nlp", OUTPUT)
    if spec is None or spec.loader is None:
        raise SystemExit("built Mojo library is not a loadable Python extension")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.abi_version() != 1 or module.parity_approved() is not False:
        raise SystemExit("built Mojo boundary has an unexpected ABI/parity state")
    print(f"built inactive ABI-v1 Mojo boundary: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
