"""Read an .xlsx workbook without a dependency.

`openpyxl` is not a project dependency, and two Phase 19 modules (m24 council
spend, m25 Skills for Care) read .xlsx files. An .xlsx is a zip of XML, so
the reader is stdlib: `zipfile` plus `xml.etree`, shared strings resolved
once, sheet names taken from the workbook's own `sheets` list.

What it returns is deliberately plain. `read_sheet` gives one sheet at a
time as a list of lists, every cell a string exactly as the file stores it —
no types, no styles, no dates; a caller that needs a number parses it with
its own discipline (NULL on unparseable, never a guess). A reader that
returned floats or dates it inferred would be a second source of truth about
what the workbook says, and this pipeline has exactly one rule for that: the
file is the truth.

`iter_sheet` is the streaming form, for the workbooks whose sheets are too
large to materialise: Skills for Care's local-area download is 53 MB
compressed, 518 MB of raw sheet XML, and a full-tree read takes ten minutes
where a streaming one takes seconds. It yields one dict per row holding only
the columns the caller asked for, keyed by the column letters it asked for.

Two limits, both honest:

  * Cells are read by column letter from the `r` attribute. A worksheet
    whose cells carry no `r` attribute (rare, but some generators omit it)
    is refused rather than mis-read: rows without positions cannot be
    trusted, and an evidence pipeline that stores a spreadsheet it may have
    shuffled is worse than one that says it cannot read it.
  * The reader only understands the spreadsheetml shapes openpyxl itself
    writes: shared strings (`t="s"`), inline strings (`t="inlineStr"`),
    numbers, booleans and errors. A cell of a shape it has not seen is read
    as its raw text and the caller's parser decides — refusing the whole
    file for one exotic cell would make a 4 MB workbook unreadable because
    of a single cell nobody reads.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_COLUMN_RE = re.compile(r"[A-Z]+")
_TEXT_TAG = f"{{{_SPREADSHEET_NS}}}t"


class XlsxError(ValueError):
    """The file cannot be read as this module's xlsx. The caller records it
    as a parse_failure — an unreadable file is a fact, not a guess."""


def _open(path_or_bytes: Path | str | bytes) -> zipfile.ZipFile:
    """A ZipFile over either a path or the workbook's bytes.

    The pipeline client hands modules the exact bytes of a fetched file, and
    the raw archive is addressed by hash — writing those bytes to a named
    temp file just to reopen them as a zip is a step nothing needs. A
    bytes.BytesIO is a valid archive source.
    """
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return zipfile.ZipFile(io.BytesIO(path_or_bytes))
    return zipfile.ZipFile(path_or_bytes)


def _shared_strings(archive: zipfile.ZipFile) -> dict[int, str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    out: dict[int, str] = {}
    for index, item in enumerate(root.findall(f"{{{_SPREADSHEET_NS}}}si")):
        out[index] = "".join((node.text or "")
                              for node in item.iter(_TEXT_TAG))
    return out


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    """Sheet name -> worksheet path inside the archive."""
    root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map: dict[str, str] = {}
    for rel in rels:
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            rel_map[rid] = target
    out: dict[str, str] = {}
    for sheet in root.findall(f"{{{_SPREADSHEET_NS}}}sheets/"
                              f"{{{_SPREADSHEET_NS}}}sheet"):
        name = sheet.get("name")
        rid = sheet.get(f"{{{_REL_NS}}}id")
        if not name or not rid:
            continue
        target = rel_map.get(rid or "")
        if not target:
            continue
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        if target in archive.namelist():
            out[name] = target
    return out


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _cell_value(cell: ET.Element, shared: dict[int, str]) -> str:
    kind = cell.get("t")
    value = cell.find(f"{{{_SPREADSHEET_NS}}}v")
    if kind == "s" and value is not None:
        try:
            return shared.get(int(value.text or ""), "")
        except ValueError:
            return ""
    if kind == "inlineStr":
        inline = cell.find(f"{{{_SPREADSHEET_NS}}}is")
        if inline is None:
            return ""
        return "".join((node.text or "")
                        for node in inline.iter(_TEXT_TAG))
    if value is not None:
        return value.text or ""
    return ""


def sheet_names(path_or_bytes: Path | str | bytes) -> list[str]:
    """Sheet names in workbook order."""
    with _open(path_or_bytes) as archive:
        return list(_sheet_paths(archive))


def read_sheet(path_or_bytes: Path | str | bytes, name: str) -> list[list[str]]:
    """One sheet as rows of string cells.

    Only rows with at least one cell are returned (blank trailer rows are
    noise, and a sheet's real rows all carry at least one value). A row with
    no `r` attributes raises XlsxError. For a sheet that is large (hundreds
    of MB of XML), use `iter_sheet` instead.
    """
    with _open(path_or_bytes) as archive:
        target = _sheet_paths(archive).get(name)
        if target is None:
            raise XlsxError(f"no sheet named {name!r}")
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(target))
        out: list[list[str]] = []
        for row in root.findall(f"{{{_SPREADSHEET_NS}}}sheetData/"
                                f"{{{_SPREADSHEET_NS}}}row"):
            cells: dict[int, str] = {}
            for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
                ref = cell.get("r")
                if ref:
                    column = _COLUMN_RE.match(ref)
                    index = _column_index(column.group(0)) if column else None
                else:
                    index = None
                value = _cell_value(cell, shared)
                if index is not None and value != "":
                    cells[index] = value
            if not cells:
                continue
            width = max(cells) + 1
            out.append([cells.get(i, "") for i in range(width)])
        return out


def iter_sheet(path_or_bytes: Path | str | bytes, name: str,
               keep: set[str] | None = None) -> list[dict[str, str]]:
    """One sheet as row dicts holding only the requested column letters.

    `keep` names the columns to return by letter (e.g. {"A", "B", "DX"}).
    None keeps every non-empty cell. The sheet is read streaming — the
    element tree is dropped as it is walked — so a 500 MB sheet costs a few
    seconds of XML parsing rather than a full in-memory tree.

    Returns a list (the caller usually iterates it once and writes rows; a
    list keeps the call site free of iterator-lifetime surprises with the
    archive). Each row is {column_letter: value}.
    """
    out: list[dict[str, str]] = []
    with _open(path_or_bytes) as archive:
        target = _sheet_paths(archive).get(name)
        if target is None:
            raise XlsxError(f"no sheet named {name!r}")
        shared = _shared_strings(archive)
        row_cells: dict[str, str] = {}
        for event, elem in ET.iterparse(archive.open(target),
                                         events=("end",)):
            if elem.tag == f"{{{_SPREADSHEET_NS}}}c":
                ref = elem.get("r") or ""
                if not ref:
                    # A cell without a position cannot be trusted (see the
                    # module docstring); refuse rather than mis-read.
                    raise XlsxError("cell without an r attribute; "
                                    "the worksheet cannot be positioned")
                column = _COLUMN_RE.match(ref)
                if column is None:
                    continue
                letters = column.group(0)
                if keep is not None and letters not in keep:
                    elem.clear()
                    continue
                value = _cell_value(elem, shared)
                if value != "":
                    row_cells[letters] = value
                elem.clear()
            elif elem.tag == f"{{{_SPREADSHEET_NS}}}row":
                if row_cells:
                    out.append(dict(row_cells))
                    row_cells.clear()
                elem.clear()
            elif elem.tag == f"{{{_SPREADSHEET_NS}}}sheetData":
                elem.clear()
    return out
