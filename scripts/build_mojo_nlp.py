"""Build and contract-check the optional Linux Mojo NLP extension."""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "pipeline" / "nlp" / "_mojo_nlp.mojo"
OUTPUT = ROOT / "pipeline" / "nlp" / "_mojo_nlp.so"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fixture_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _fixture_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _fixture_strings(item)


def _parity_texts():
    texts = []
    for path in sorted((ROOT / "tests" / "fixtures" / "nlp").glob("*.json")):
        texts.extend(_fixture_strings(json.loads(path.read_text(encoding="utf-8"))))
    texts.extend([
        "Recruitment difficulties remain.",
        "No staffing pressures were reported.",
        "The service relies on agency workers and alcohol misuse treatment.",
        "opioid-substitution treatment is available in the area.",
        "The council is a limited company, not a provider.",
    ])
    return list(dict.fromkeys(texts))


def _check_parity(module) -> None:
    from pipeline.nlp import accelerator, ontology

    onto = ontology.default()
    texts = _parity_texts()
    expected = onto.match_batch(texts)
    packed = accelerator.pack_texts(texts)
    result = module.match_ontology(
        packed.utf8, packed.offsets, onto.version, accelerator.pack_ontology(onto))
    actual = accelerator._unpack_matches(onto, texts, result)
    if actual != expected:
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            if left != right:
                raise SystemExit(
                    f"Mojo ontology parity mismatch at {index}: {texts[index]!r}; "
                    f"expected {left!r}, got {right!r}")
        raise SystemExit("Mojo ontology parity mismatch: result lengths differ")
    print(f"verified exact Mojo ontology parity for {len(texts)} texts")


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
    if module.abi_version() != 1 or module.parity_approved() is not True:
        raise SystemExit("built Mojo boundary has an unexpected ABI/parity state")
    _check_parity(module)
    print(f"built active ABI-v1 Mojo ontology boundary: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
