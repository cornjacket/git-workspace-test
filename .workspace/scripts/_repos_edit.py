"""Text-preserving edits to .workspace/repos.yml.

repos.yml is CONTENT: the user reads and edits it, and it ships with a long
explanatory header plus per-entry comments. A YAML round-trip
(`yaml.safe_load` -> `yaml.safe_dump`) would silently delete every one of those
comments, reflow the quoting, and reorder keys — so the verbs edit the file as
*text* and only parse YAML to validate the result.

The file is a lockfile the verbs maintain, not a config you hand-author, so the
shapes it must survive are narrow:

    repos: []                 the seeded empty state
    repos:                    entries at indent 2 (`  - name:`), keys at indent 4
      - name: foo
        url: ...
"""
import io
import re

ENTRY_RE = re.compile(r"^  - (\w+):", re.M)
REPOS_KEY_RE = re.compile(r"^repos:[ \t]*(\[\s*\])?[ \t]*$", re.M)

ENTRY_INDENT = "  - "
KEY_INDENT = "    "


class RepoEditError(RuntimeError):
    """The file is not in a shape these verbs can safely edit."""


def _lines(text):
    return text.splitlines(keepends=True)


def find_repos_key(text):
    """(start, end) character span of the `repos:` line, or raise."""
    m = REPOS_KEY_RE.search(text)
    if not m:
        raise RepoEditError(
            "repos.yml has no top-level `repos:` key that these verbs can edit. "
            "Add one (or restore the generated file) and re-run."
        )
    return m.start(), m.end()


def entry_spans(text):
    """[(name, start_line, end_line)] over the entry blocks, in file order.

    An entry runs from its `  - name:` line to just before the next entry (or
    the end of the repos block). Trailing comments and blank lines belong to the
    entry above them, which keeps a comment attached to what it describes when
    the entry is removed.
    """
    lines = _lines(text)
    starts = []
    for i, line in enumerate(lines):
        if line.startswith(ENTRY_INDENT):
            key = line[len(ENTRY_INDENT):].split(":", 1)[0].strip()
            if key != "name":
                raise RepoEditError(
                    f"repos.yml line {i + 1}: an entry must start with `- name:`; "
                    f"found `- {key}:`. Reorder it and re-run."
                )
            starts.append(i)
    out = []
    for n, i in enumerate(starts):
        name = lines[i].split(":", 1)[1].strip()
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        out.append((name, i, end))
    return out


def find_entry(text, name):
    for entry in entry_spans(text):
        if entry[0] == name:
            return entry
    return None


def names(text):
    return [e[0] for e in entry_spans(text)]


def render_entry(fields):
    """One YAML entry block from an ordered (key, value) list."""
    buf = io.StringIO()
    first = True
    for key, value in fields:
        if value is None or value == "":
            continue
        prefix = ENTRY_INDENT if first else KEY_INDENT
        buf.write(f"{prefix}{key}: {value}\n")
        first = False
    return buf.getvalue()


def append_entry(text, entry_block):
    """Add an entry at the end of the repos list.

    Handles the seeded `repos: []` by converting it to a real list first —
    otherwise the appended entry would sit under an explicitly empty sequence
    and be silently ignored by every reader.
    """
    start, end = find_repos_key(text)
    if text[start:end].strip() != "repos:":
        text = text[:start] + "repos:" + text[end:]

    if not text.endswith("\n"):
        text += "\n"
    # Entries live at the end of the file in every generated repos.yml; if the
    # user put content after them, append after the LAST entry instead of at EOF.
    spans = entry_spans(text)
    if not spans:
        return text + entry_block
    lines = _lines(text)
    last_end = spans[-1][2]
    if last_end >= len(lines):
        return text + entry_block
    return "".join(lines[:last_end]) + entry_block + "".join(lines[last_end:])


def remove_entry(text, name):
    span = find_entry(text, name)
    if span is None:
        raise RepoEditError(f"no repo named '{name}' in repos.yml")
    lines = _lines(text)
    del lines[span[1]:span[2]]
    text = "".join(lines)
    # An empty list must be spelled `repos: []`, not a bare `repos:` — the
    # latter parses as None and every reader would need a special case.
    if not entry_spans(text):
        start, end = find_repos_key(text)
        text = text[:start] + "repos: []" + text[end:]
    return text


def set_field(text, name, key, value):
    """Set (or insert) one key inside an entry, leaving everything else alone."""
    span = find_entry(text, name)
    if span is None:
        raise RepoEditError(f"no repo named '{name}' in repos.yml")
    lines = _lines(text)
    key_re = re.compile(rf"^{KEY_INDENT}{re.escape(key)}:")
    for i in range(span[1], span[2]):
        if key_re.match(lines[i]):
            lines[i] = f"{KEY_INDENT}{key}: {value}\n"
            return "".join(lines)
    # Not present: insert directly after `- name:` so the flag sits near the top
    # of its entry rather than after a trailing comment.
    lines.insert(span[1] + 1, f"{KEY_INDENT}{key}: {value}\n")
    return "".join(lines)


def validate(text):
    """Parse the edited text and return the repo dicts, or raise.

    Every verb runs this before writing: a text edit that produced invalid YAML
    must never reach disk, because the next reader is a status run that would
    fail somewhere far from the cause.
    """
    import yaml
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise RepoEditError(f"the edit produced invalid YAML: {e}")
    repos = data.get("repos")
    if repos is None:
        return []
    if not isinstance(repos, list):
        raise RepoEditError("`repos:` must be a list")
    seen = set()
    for r in repos:
        if not isinstance(r, dict) or not r.get("name"):
            raise RepoEditError(f"every entry needs a `name:` — got {r!r}")
        if r["name"] in seen:
            raise RepoEditError(f"duplicate repo name '{r['name']}'")
        seen.add(r["name"])
    return repos
