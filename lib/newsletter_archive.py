"""Let the newsletter publisher read Substack's current archive body.

The public archive used to be a bare list of letters. It now also returns
``{"posts": [...], "nextCursor": "..."}``. The private publisher rejects any
body that is not a list, reports that the archive contained no letters, and
leaves the live page in place. This adapter hands that publisher the posts
array. An empty array, a body with no posts array, and any other shape still
fail closed.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import ModuleType

EMPTY_ARCHIVE = "The newsletter archive did not include any letters."


def posts_from_archive(payload: object) -> list:
    """Return the letter records from a bare list or a posts envelope.

    The list object is the same object the caller passed when the body is
    already a list, so a later check can tell that unwrapping did nothing.
    """
    if isinstance(payload, dict):
        posts = payload.get("posts")
        if isinstance(posts, list):
            payload = posts
        else:
            raise RuntimeError(EMPTY_ARCHIVE)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(EMPTY_ARCHIVE)
    return payload


def accepting_parser(parse_archive):
    """Call the publisher's parser, unwrapping a posts envelope if it refuses one.

    The publisher still decides which records are letters. Other failures are
    not retried and are not turned into an empty success.
    """

    def wrapped(payload, *args, **kwargs):
        try:
            return parse_archive(payload, *args, **kwargs)
        except RuntimeError as error:
            if str(error) != EMPTY_ARCHIVE:
                raise
            posts = posts_from_archive(payload)
            if posts is payload:
                raise
            return parse_archive(posts, *args, **kwargs)

    return wrapped


def patch_archive_source(source: str) -> str | None:
    """Insert an envelope unwrap ahead of the historical list-only guard.

    Returns None when that guard is not present, so an unrelated publisher is
    left untouched. The guard that runs after individual letters are filtered
    does not match and stays in place.
    """
    needle = 'if not isinstance(payload, list) or not payload:\n'
    start = 0
    while True:
        at = source.find(needle, start)
        if at < 0:
            return None
        line_start = source.rfind("\n", 0, at) + 1
        indent = source[line_start:at]
        if indent.strip():
            start = at + len(needle)
            continue
        raise_at = at + len(needle)
        extra = "\t" if "\t" in indent else "    "
        raise_line = f'{indent}{extra}raise RuntimeError("{EMPTY_ARCHIVE}")'
        if not source.startswith(raise_line, raise_at):
            start = at + len(needle)
            continue
        unwrap = (
            f'{indent}if isinstance(payload, dict) and isinstance(payload.get("posts"), list):\n'
            f'{indent}{extra}payload = payload["posts"]\n'
        )
        return source[:line_start] + unwrap + source[line_start:]


def load_publisher(path: Path) -> ModuleType:
    """Load the private publisher, patching its list-only guard when present."""
    script = path.resolve()
    source = script.read_text(encoding="utf-8")
    patched = patch_archive_source(source)
    if patched is not None:
        source = patched
    directory = str(script.parent)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    module_name = "publish_newsletter_" + hashlib.sha256(str(script).encode()).hexdigest()[:12]
    module = ModuleType(module_name)
    module.__file__ = str(script)
    sys.modules[module_name] = module
    exec(compile(source, str(script), "exec"), module.__dict__)
    parse_archive = getattr(module, "parse_archive", None)
    if callable(parse_archive):
        module.parse_archive = accepting_parser(parse_archive)
    elif patched is None:
        raise RuntimeError(
            "Newsletter publisher has no parse_archive() and no list-only archive guard. "
            "Refusing to publish."
        )
    return module
