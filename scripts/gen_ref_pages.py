"""The API reference and the landing page, generated during the build.

Nothing this writes lands in the repository. mkdocs-gen-files hands the build
a virtual docs tree, which is the point: a module added to `pipeline/` gets a
reference page without anyone remembering to add one, and README.md stays the
only copy of the front page rather than being kept in step with a second one.

The reference exists to make the module docstrings navigable, not to become
the documentation. The docstrings in this codebase explain constraints and
reasoning -- see `pipeline/promote.py` -- and they are still meant to be read
next to the code.
"""
from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "pipeline"

# Migrations are SQL with a thin loader, and their comments are already the
# source docs/DATA_DICTIONARY.md is generated from. Documenting them twice
# would put the same prose in two places, which is the thing being avoided.
SKIP_PARTS = {"__pycache__", "migrations"}

nav = mkdocs_gen_files.Nav()

for path in sorted(SRC.rglob("*.py")):
    relative = path.relative_to(REPO_ROOT)
    if SKIP_PARTS & set(relative.parts):
        continue

    doc_path = relative.with_suffix(".md")
    parts = list(relative.with_suffix("").parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name("index.md")
        if not parts:
            continue
    elif parts[-1] == "__main__":
        continue

    full_doc_path = Path("reference", doc_path)
    # SUMMARY.md sits inside reference/, so its entries are relative to that
    # directory. Writing full_doc_path here prefixes reference/ twice and
    # every link in the generated nav misses.
    nav[parts] = doc_path.as_posix()

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        fd.write(f"# `{'.'.join(parts)}`\n\n::: {'.'.join(parts)}\n")

    # `..` backs out of the `docs/` in edit_uri: these pages describe a
    # source file, so editing one means editing the module, not a document.
    mkdocs_gen_files.set_edit_path(full_doc_path, f"../{relative.as_posix()}")

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as fd:
    fd.writelines(nav.build_literate_nav())

# The front page is README.md itself. Copying it into docs/index.md by hand
# would create a second one to keep current; including it by reference means
# the site cannot show a stale version of it. The hook in scripts/
# mkdocs_hooks.py resolves its `docs/...` links on the way through.
with mkdocs_gen_files.open("index.md", "w") as fd:
    fd.write((REPO_ROOT / "README.md").read_text(encoding="utf-8"))

mkdocs_gen_files.set_edit_path("index.md", "../README.md")
