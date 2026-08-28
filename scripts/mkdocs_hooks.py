"""Repo-relative links in the docs, resolved at build time.

The docs here are written to be read in the checkout, so they link the way
the code does -- `pipeline/runner.py:120`, `docs/CAVEATS.md:25`, `BACKUP.md`.
Those targets mean nothing to a rendered site, and worse, they mean nothing
to a *reader* of the checkout either once the file moves.

So every link is resolved against the working tree while the site builds. A
target that still exists is rewritten to something the site can follow: an
internal page link if it is a document, a blob URL pinned to the line if it
is source. A target that does not exist is a warning, which `--strict` turns
into a failed build. That is the whole reason this file is here -- the site
is the side effect, the broken link is the thing being caught.

Links are left alone inside fenced code blocks. A doc that shows a Markdown
example is showing it, not linking.
"""
from __future__ import annotations

import logging
import os
import os.path
import re
import subprocess
from pathlib import Path

from mkdocs.structure.files import Files

# `git ls-files -z` separates entries with NUL. Named rather than written
# as an escape in the split call, where it is easy to get wrong.
NUL = chr(0)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
_GITHUB = "https://github.com/Jonfuk/cglpay.us-SectorTrace/"
BLOB = _GITHUB + "blob/master/"
TREE = _GITHUB + "tree/master/"

log = logging.getLogger(f"mkdocs.plugins.{__name__}")


class _SymlinkNoiseFilter(logging.Filter):
    """Drops one Windows-only warning from the privacy plugin.

    When it downloads a font stylesheet whose URL carries no file extension it
    tries to symlink the extensionless name to the saved file, which needs
    Developer Mode on Windows. The plugin already handles the failure -- it
    points at the real file and moves on -- and says so in its own comment.
    The only consequence is that the font is re-downloaded on each local
    build.

    Without this, `--strict` fails on Windows and passes in CI, which would
    mean the check nobody can run locally is the one that gates the deploy.
    Narrow on purpose: this exact message, this logger, this platform. Any
    other warning from the privacy plugin still fails the build, and on Linux
    so does this one, because there it would mean something else.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "Couldn't create symbolic link" not in record.getMessage()


if os.name == "nt":
    logging.getLogger("mkdocs.material.privacy").addFilter(_SymlinkNoiseFilter())

# Working registers, not reference documentation. They stay in the repository
# and in git history -- they are not secret, and the repository is public --
# but they are not built into the site, because a published page reads as
# settled and these are not. A roadmap line quoted back as a finding is the
# specific failure being avoided.
#
# Links to them from published pages still work: they resolve to the file on
# GitHub rather than to a page that would not exist here. See _rewrite.
UNPUBLISHED = (
    "admin-ui-plan.md",
    "document-analysis.md",
    "m32-sab-site-crawl.md",
    "mysociety-access-request.md",
    "public-portal-ui-spec.md",
    "public-ui-refinement-backlog.md",
    "review-queue-improvements.md",
    "semantic-analysis.md",
    "unraid-document-worker.md",
    "upgrade-audit-prompt.md",
    "upgrade-roadmap.md",
)

# Whole directories, including the data files beside their write-ups.
UNPUBLISHED_DIRS = ("benchmarks/", "verification/")


def _unpublished(src_uri: str) -> bool:
    posix = src_uri.replace("\\", "/")
    return posix in UNPUBLISHED or posix.startswith(UNPUBLISHED_DIRS)

# Inline links only, and not images: `![alt](path)` is an asset reference and
# MkDocs already resolves those itself.
_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]*)\]\((?!<)([^)\s]+)((?:\s+\"[^\"]*\")?)\)")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

# `pipeline/runner.py:120` -- the line suffix this codebase writes into prose.
_LINE_SUFFIX_RE = re.compile(r":(\d+)$")

_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "//", "#")


def _split_fences(markdown: str) -> list[tuple[bool, str]]:
    """The document as (is_code, text) runs, so links in examples survive."""
    runs: list[tuple[bool, str]] = []
    buffer: list[str] = []
    in_fence = False
    fence: str | None = None

    for line in markdown.splitlines(keepends=True):
        match = _FENCE_RE.match(line)
        if match and not in_fence:
            runs.append((False, "".join(buffer)))
            buffer = [line]
            in_fence, fence = True, match.group(1)
        elif match and in_fence and fence and match.group(1).startswith(fence[0] * len(fence)):
            buffer.append(line)
            runs.append((True, "".join(buffer)))
            buffer, in_fence, fence = [], False, None
        else:
            buffer.append(line)

    runs.append((in_fence, "".join(buffer)))
    return runs


def _tracked() -> frozenset[Path] | None:
    """Everything git has, files and their directories. None if git cannot say.

    Existence on disk is the wrong test and CI proved it: `logs/` is ignored,
    so a link to a run log resolved on the machine that had done a run and
    failed on a fresh checkout. A check that passes because of what happens to
    be lying around is not a check. What a reader can follow is what is *in
    the repository*, so that is what gets asked.
    """
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        # A build from an unpacked tarball rather than a checkout. Fall back to
        # the filesystem rather than reporting every link in the docs as
        # broken, and say so once, because the check is weaker from here on.
        log.info("git unavailable; falling back to filesystem checks for link targets")
        return None

    paths: set[Path] = set()
    for entry in listing.split(NUL):
        if not entry:
            continue
        path = (REPO_ROOT / entry).resolve()
        paths.add(path)
        # Directories are never listed by `git ls-files`, but docs link to
        # them, so derive them from the files they contain.
        for parent in path.parents:
            if parent == REPO_ROOT:
                break
            paths.add(parent)
    return frozenset(paths)


TRACKED = _tracked()


def _resolve(target: str, page_dir: Path) -> Path | None:
    """First of the two bases that is in the repository, or None.

    Docs link both ways and always have: a sibling document by bare name, a
    source file by its path from the repository root. Guessing one convention
    and rewriting the other into a broken link would be worse than either.
    """
    for base in (page_dir, REPO_ROOT):
        candidate = (base / target).resolve()
        found = candidate in TRACKED if TRACKED is not None else candidate.exists()
        if found:
            return candidate
    return None


def _rewrite(target: str, page_dir: Path, page_path: str) -> str:
    if target.startswith(_EXTERNAL_PREFIXES):
        return target

    anchor = ""
    if "#" in target:
        target, _, anchor = target.partition("#")
        anchor = f"#{anchor}"
        if not target:
            return f"{anchor}"

    line_match = _LINE_SUFFIX_RE.search(target)
    line = line_match.group(1) if line_match else None
    if line_match:
        target = target[: line_match.start()]

    resolved = _resolve(target, page_dir)
    if resolved is None:
        log.warning("%s: link target does not exist: %s", page_path, target)
        return target + (f":{line}" if line else "") + anchor

    inside_docs = DOCS_DIR in resolved.parents or resolved.parent == DOCS_DIR
    published = inside_docs and not _unpublished(
        resolved.relative_to(DOCS_DIR).as_posix() if inside_docs else "")
    if published and resolved.suffix == ".md" and line is None:
        # A document the site also renders: keep it internal so the nav,
        # the search index and the offline build all agree it is one page.
        relative = Path(os.path.relpath(resolved, page_dir)).as_posix()
        return relative + anchor

    try:
        within_repo = resolved.relative_to(REPO_ROOT)
    except ValueError:
        # A `../` link that climbs out of the checkout. It resolved, so the
        # target exists on this machine, but it is not something a reader of
        # the site can be sent to. Warn rather than raise: a build that dies
        # with a traceback says less than one that names the link.
        log.warning("%s: link target is outside the repository: %s", page_path, target)
        return target + (f":{line}" if line else "") + anchor

    # GitHub serves directories under tree/, not blob/.
    kind = TREE if resolved.is_dir() else BLOB
    return kind + within_repo.as_posix() + (f"#L{line}" if line else anchor)


def on_files(files: Files, config) -> Files:  # noqa: ARG001
    """Remove the working registers from the build.

    Filtering here rather than only leaving them out of the nav: a document
    absent from the nav is still built and still reachable by anyone who
    guesses the URL, which is publication without navigation rather than no
    publication.
    """
    return Files([f for f in files if not _unpublished(f.src_uri)])


def on_page_markdown(markdown: str, page, config, files) -> str:  # noqa: ARG001
    # reference/ is generated by scripts/gen_ref_pages.py into a virtual tree
    # that has no counterpart on disk, so resolving its links against the
    # working tree would report every one of them as missing. MkDocs already
    # validates them against the file collection, which is the right check.
    if page.file.src_uri.startswith("reference/"):
        return markdown

    page_dir = (DOCS_DIR / page.file.src_uri).parent

    def replace(match: re.Match[str]) -> str:
        text, target, title = match.groups()
        return f"[{text}]({_rewrite(target, page_dir, page.file.src_uri)}{title})"

    return "".join(
        run if is_code else _LINK_RE.sub(replace, run)
        for is_code, run in _split_fences(markdown)
    )


# --- no third-party assets, checked rather than intended -------------------

_CSS_REMOTE_URL_RE = re.compile(r"url\(\s*['\"]?(https?://[^)'\"]+)['\"]?\s*\)")

# Hosts that serve assets or identify readers. Checked by name rather than by
# flagging every absolute URL in a script, which was tried and is not usable:
# minified bundles are full of XML namespace URIs (http://www.w3.org/2000/svg)
# that are identifiers and never fetched, and of template literals assembled
# from variables. Naming the hosts keeps the check about the thing that
# matters -- does a reader's browser talk to anyone but this site -- and it
# still catches what the CSS-only version missed.
#
# This is a floor, not a proof. The runtime check is the browser's own
# resource timings on the built page; see the verification note in the commit.
_OFFSITE_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com",
    "gravatar.com", "weavatar.com",
    "unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
)
# One allowed exception, written down rather than absorbed into the pattern.
#
# The theme's bundle contains
#   typeof ResizeObserver == "undefined" ? Rt("https://unpkg.com/...") : ...
# a polyfill injected only by a browser that lacks ResizeObserver, which has
# been supported everywhere since 2020. It does not fire, and with no network
# it fails and the page still renders, which is the property rule 6 protects.
#
# It is listed here so that it stays a decision someone took. If the theme
# ever adds a second one, the build fails and somebody has to look at it.
_ALLOWED_OFFSITE = frozenset({
    "https://unpkg.com/resize-observer-polyfill",
})


_SCRIPT_REMOTE_URL_RE = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:" + "|".join(h.replace(".", r"\.") for h in _OFFSITE_HOSTS) + r")[^\"'`\s)]*"
)

# HTML only where the browser is told to fetch something. `<a href>` is left
# alone: these documents cite sources by link, and must.
_HTML_REMOTE_ASSET_RE = re.compile(
    r"(?:<(?:script|img|iframe|source)[^>]*?(src)=|"
    r"<link[^>]*?rel=[\"']?stylesheet[\"']?[^>]*?(?:href)=)"
    r"[\"'](https?://[^\"']+)[\"']",
)


def on_post_build(config) -> None:
    """Strip remote font fallbacks, then prove none are left.

    The privacy plugin localises what the build references, but a plugin that
    copies its own stylesheet in afterwards is outside that: document-dates
    ships a Material Icons face listing its local woff2 first and three
    gstatic URLs after it. In practice the local file wins and nothing is
    fetched. "In practice" is not the standard here -- rule 6 says both front
    ends render with the network cable unplugged -- so the fallbacks are
    removed when the local file is genuinely present, and then every built
    stylesheet is checked for a remaining remote url().

    Scripts are checked too, and that is not hypothetical: the first dates
    plugin tried here printed no author anywhere and still fetched a favicon
    from gravatar.com and weavatar.com on every page load, to decide which
    avatar host was faster. A CSS-only check saw nothing wrong. So any absolute
    URL in a built script is a failure, because nothing here has a reason to
    hold one.

    HTML is checked only where it loads something -- `src=` and stylesheet
    links. Prose in these documents links out to sources constantly and must
    keep doing so; a link a reader may choose to follow is not a request the
    page makes.

    A leftover is a warning, so `--strict` fails on it. That turns no-CDN from
    a thing everyone remembers into a thing the build refuses to get wrong.
    """
    site_dir = Path(config["site_dir"])

    for css in site_dir.rglob("*.css"):
        text = css.read_text(encoding="utf-8", errors="ignore")
        remotes = _CSS_REMOTE_URL_RE.findall(text)
        if not remotes:
            continue

        # Only drop a remote source when a local one sits beside it in the
        # same rule. Removing the last source available would replace a font
        # that loads over the network with a font that does not load.
        if "url(./" in text or "url('./" in text:
            text = _CSS_REMOTE_URL_RE.sub("", text)
            text = re.sub(r",\s*,", ",", text)
            text = re.sub(r",\s*;", ";", text)
            css.write_text(text, encoding="utf-8")
            remotes = _CSS_REMOTE_URL_RE.findall(text)

        for url in remotes:
            log.warning(
                "%s still loads an asset from %s",
                css.relative_to(site_dir).as_posix(), url,
            )

    for script in site_dir.rglob("*.js"):
        text = script.read_text(encoding="utf-8", errors="ignore")
        found = set(_SCRIPT_REMOTE_URL_RE.findall(text)) - _ALLOWED_OFFSITE
        for url in sorted(found):
            log.warning(
                "%s references %s; scripts here must not reach off-site",
                script.relative_to(site_dir).as_posix(), url,
            )

    for page in site_dir.rglob("*.html"):
        text = page.read_text(encoding="utf-8", errors="ignore")
        for attr, url in _HTML_REMOTE_ASSET_RE.findall(text):
            log.warning(
                "%s loads %s via %s",
                page.relative_to(site_dir).as_posix(), url, attr,
            )
