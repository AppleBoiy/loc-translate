# --- BEGIN L10N CORE (shared by loc-translate, glossary-forge, loc-qa, loc-sync; edit in core/l10n_core.py) ---
"""Shared localization core: layout-preserving JSONC, token masking, project config.

Standard library only.
"""
import fnmatch
import glob as _glob
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

CORE_VERSION = "1.0.0"
CONFIG_NAME = ".l10n.json"


# ============================================================================ JSONC (layout-preserving)

class JsoncError(ValueError):
    pass


class Entry:
    """One key/value pair of a flat i18n object, with its exact position in the file."""
    __slots__ = ("key", "value", "vstart", "vend", "kstart", "line_start", "line_end", "note", "is_string")

    def __init__(self, key, value, kstart, vstart, vend, is_string):
        self.key, self.value, self.kstart, self.vstart, self.vend, self.is_string = key, value, kstart, vstart, vend, is_string
        self.line_start = self.line_end = 0
        self.note = ""


class JsoncDoc:
    """A flat JSON/JSONC object (SMAPI i18n, app locale files) that can be edited without
    touching comments, key order, indentation, BOM or line endings."""

    def __init__(self, text, path=""):
        self.path = path
        self.bom = text.startswith("\ufeff")
        self.text = text[1:] if self.bom else text
        self.newline = "\r\n" if "\r\n" in self.text else "\n"
        self.entries = []
        self.open_brace = self.close_brace = -1
        self._parse()

    # ---------- parsing
    def _skip_ws(self, i, comments=None):
        t, n = self.text, len(self.text)
        while i < n:
            c = t[i]
            if c in " \t\r\n,":
                i += 1
            elif t.startswith("//", i):
                j = t.find("\n", i)
                j = n if j < 0 else j
                if comments is not None:
                    comments.append((i, t[i + 2:j].strip()))
                i = j
            elif t.startswith("/*", i):
                j = t.find("*/", i)
                if j < 0:
                    raise JsoncError(f"{self.path}: unterminated /* comment")
                if comments is not None:
                    comments.append((i, t[i + 2:j].strip(" *\n\t")))
                i = j + 2
            else:
                break
        return i

    def _string(self, i):
        t, n = self.text, len(self.text)
        if t[i] != '"':
            raise JsoncError(f"{self.path}: expected string at {self._pos(i)}")
        j = i + 1
        while j < n:
            c = t[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                raw = t[i:j + 1]
                try:
                    return json.loads(raw), j + 1
                except json.JSONDecodeError:
                    # tolerate raw control characters (literal newlines/tabs) some mods ship
                    return json.loads(raw.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")), j + 1
            j += 1
        raise JsoncError(f"{self.path}: unterminated string at {self._pos(i)}")

    def _value_end(self, i):
        """End of a non-string value (number, bool, null, nested object/array)."""
        t, n = self.text, len(self.text)
        if t[i] in "{[":
            depth, j, ins = 0, i, False
            while j < n:
                c = t[j]
                if ins:
                    if c == "\\":
                        j += 2
                        continue
                    if c == '"':
                        ins = False
                elif c == '"':
                    ins = True
                elif t.startswith("//", j):
                    j = t.find("\n", j)
                    j = n if j < 0 else j
                    continue
                elif t.startswith("/*", j):
                    j = t.find("*/", j) + 2
                    continue
                elif c in "{[":
                    depth += 1
                elif c in "}]":
                    depth -= 1
                    if depth == 0:
                        return j + 1
                j += 1
            raise JsoncError(f"{self.path}: unbalanced brackets")
        m = re.compile(r"[^\s,}\]/]+").match(t, i)
        if not m:
            raise JsoncError(f"{self.path}: bad value at {self._pos(i)}")
        return m.end()

    def _pos(self, i):
        line = self.text.count("\n", 0, i) + 1
        return f"line {line}"

    def _parse(self):
        t = self.text
        i = self._skip_ws(0)
        if i >= len(t) or t[i] != "{":
            raise JsoncError(f"{self.path}: top level must be an object")
        self.open_brace = i
        i += 1
        pending = []  # comments seen since the previous entry
        while True:
            comments = []
            i = self._skip_ws(i, comments)
            if self.entries and comments:
                # a comment on the same line as the previous entry belongs to it
                prev = self.entries[-1]
                same_line = [c for c in comments if "\n" not in t[prev.vend:c[0]]]
                for c in same_line:
                    prev.note = (prev.note + " " + c[1]).strip()
                comments = [c for c in comments if c not in same_line]
            pending += comments
            if i >= len(t):
                raise JsoncError(f"{self.path}: missing closing brace")
            if t[i] == "}":
                self.close_brace = i
                break
            kstart = i
            key, i = self._string(i)
            i = self._skip_ws(i)
            if t[i] != ":":
                raise JsoncError(f"{self.path}: expected ':' after key {key!r} at {self._pos(i)}")
            i = self._skip_ws(i + 1)
            if t[i] == '"':
                value, end = self._string(i)
                e = Entry(key, value, kstart, i, end, True)
            else:
                end = self._value_end(i)
                e = Entry(key, t[i:end], kstart, i, end, False)
            e.line_start = t.count("\n", 0, kstart) + 1
            e.line_end = t.count("\n", 0, end) + 1
            # comments directly above (no blank line in between) are notes for this key
            above = [c for c in pending if "\n\n" not in t[c[0]:kstart].replace("\r", "")]
            e.note = " ".join(c[1] for c in above).strip()
            pending = []
            self.entries.append(e)
            i = end

    # ---------- access
    def items(self):
        return [(e.key, e.value) for e in self.entries if e.is_string]

    def as_dict(self):
        return dict(self.items())

    def get(self, key, default=None):
        for e in self.entries:
            if e.key == key:
                return e.value if e.is_string else default
        return default

    def notes(self):
        return {e.key: e.note for e in self.entries if e.note}

    def keys(self):
        return [e.key for e in self.entries]

    # ---------- editing (all edits rebuild offsets)
    @staticmethod
    def encode(value):
        return json.dumps(value, ensure_ascii=False)

    def set_many(self, updates):
        """Replace string values in place. Keys not in the file are ignored (use insert)."""
        pieces, last = [], 0
        for e in self.entries:
            if e.is_string and e.key in updates and updates[e.key] != e.value:
                pieces.append(self.text[last:e.vstart])
                pieces.append(self.encode(updates[e.key]))
                last = e.vend
        pieces.append(self.text[last:])
        self._reload("".join(pieces))

    def remove(self, keys):
        keys = set(keys)
        t = self.text
        spans = []
        for e in self.entries:
            if e.key in keys:
                # remove the whole line(s) of the entry including its trailing comma and newline
                s = t.rfind("\n", 0, e.kstart) + 1
                if t[s:e.kstart].strip():  # other content on the line: remove just the pair
                    s = e.kstart
                end = e.vend
                m = re.compile(r"[ \t]*,?[ \t]*(//[^\n]*)?").match(t, end)
                end = m.end()
                if t.startswith("\r\n", end):
                    end += 2
                elif t.startswith("\n", end):
                    end += 1
                spans.append((s, end))
        out, last = [], 0
        for s, e in sorted(spans):
            out.append(t[last:s])
            last = e
        out.append(t[last:])
        text = "".join(out)
        had_trailing = bool(re.search(r",\s*(//[^\n]*\s*)*\}\s*$", t))
        if not had_trailing:  # removing the last entry must not leave a dangling comma
            text = re.sub(r",(\s*(?://[^\n]*\s*)*)\}(\s*)$", r"\1}\2", text)
        self._reload(text)

    def insert_before(self, pairs, before):
        """Insert new entries directly above an existing key's line (below any section-header comment that
        sits above it). `before` maps new key -> existing key; keys without one go after the last entry."""
        index = {e.key: e for e in self.entries}
        t, nl = self.text, self.newline
        groups, rest = {}, []
        for k, v in pairs:
            b = before.get(k)
            if b in index:
                groups.setdefault(b, []).append((k, v))
            else:
                rest.append((k, v))
        cuts = []
        for b, items in groups.items():
            e = index[b]
            ls = t.rfind("\n", 0, e.kstart) + 1
            if t[ls:e.kstart].strip():  # key shares its line with something else: insert at the key
                ls = e.kstart
                cuts.append((ls, "".join(f"{self.encode(k)}: {self.encode(v)}, " for k, v in items)))
                continue
            indent = t[ls:e.kstart]
            cuts.append((ls, "".join(f"{indent}{self.encode(k)}: {self.encode(v)},{nl}" for k, v in items)))
        out, last = [], 0
        for off, txt in sorted(cuts, key=lambda c: c[0]):
            out.append(t[last:off])
            out.append(txt)
            last = off
        out.append(t[last:])
        self._reload("".join(out))
        if rest:
            self.insert(rest, after={})

    def insert(self, pairs, after=None):
        """Insert new string entries on their own lines. `after` maps new key -> existing key to insert after
        (keeps source order); unknown anchors go after the last entry. Indentation and trailing-comma style
        copy the file; comments stay attached to the entries they belong to."""
        if not pairs:
            return
        t, nl = self.text, self.newline
        indent = "\t"
        if self.entries:
            ls = t.rfind("\n", 0, self.entries[-1].kstart) + 1
            indent = re.match(r"[ \t]*", t[ls:]).group(0) or indent
        index = {e.key: e for e in self.entries}
        groups, home = {}, {}
        for k, v in pairs:
            a = (after or {}).get(k)
            if a in home:  # anchored on a key inserted in this same call: follow it
                a = home[a]
            elif a not in index:
                a = self.entries[-1].key if self.entries else None
            groups.setdefault(a, []).append((k, v))
            home[k] = a
        cuts = []
        for anchor, items in groups.items():
            if anchor is None:  # empty object
                body = ("," + nl).join(f"{indent}{self.encode(k)}: {self.encode(v)}" for k, v in items)
                cuts.append((self.open_brace + 1, nl + body + nl))
                continue
            e = index[anchor]
            is_last = e is self.entries[-1]
            after_val = t[e.vend:]
            has_comma = bool(re.match(r"[ \t]*,", after_val))
            nl_at = t.find("\n", e.vend)
            closing_on_line = nl_at < 0 or "}" in t[e.vend:nl_at]
            lines = [f"{indent}{self.encode(k)}: {self.encode(v)}" for k, v in items]
            trailing = "," if (not is_last or has_comma) else ""
            block = ("," + nl).join(lines) + trailing + nl
            if is_last and not has_comma:
                cuts.append((e.vend, ","))
            if closing_on_line:  # "...": "x" } on one line
                cuts.append((e.vend if not has_comma else e.vend + len(re.match(r"[ \t]*,", after_val).group(0)), nl + block.rstrip("\r\n")))
            else:
                cuts.append((nl_at + 1, block))
        out, last = [], 0
        for off, txt in sorted(cuts, key=lambda c: c[0]):
            out.append(t[last:off])
            out.append(txt)
            last = off
        out.append(t[last:])
        self._reload("".join(out))

    def _reload(self, text):
        bom = self.bom
        self.__init__(text, self.path)
        self.bom = bom

    def dumps(self):
        return ("\ufeff" if self.bom else "") + self.text

    def save(self, path=None):
        p = Path(path or self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(self.dumps())


def load_doc(path):
    with open(path, encoding="utf-8", newline="") as f:
        return JsoncDoc(f.read(), str(path))


def doc_from_template(source_doc, values, drop_missing=False):
    """Build a target file that mirrors the source file's layout and comments, with translated values.
    Keys without a translation keep the source text (or are dropped when drop_missing)."""
    d = JsoncDoc(source_doc.dumps(), source_doc.path)
    d.set_many({k: v for k, v in values.items()})
    if drop_missing:
        d.remove([k for k, _ in source_doc.items() if k not in values])
    return d


# ============================================================================ tokens

# Each rule: (name, regex, kind). kind "struct" tokens split the text into segments and must keep
# their order; "inline" tokens may move but must all survive exactly once.
PROFILES = {
    "smapi": [
        ("cp-token", r"\{\{[^{}]+\}\}", "inline"),
        ("dialogue-cmd", r"#\$(?:b|e)#", "struct"),
        ("dialogue-cmd", r"#\$(?:q|r|p|d|c|k|t|1|action|query)\b[^#]*", "struct"),
        ("dialogue-cmd", r"#\$y\s", "struct"),
        ("portrait", r"\$(?:h|s|u|l|a|neutral|\d{1,2})(?=#|\^|\s*$|\s*\|)", "inline"),
        ("mail-cmd", r"%item\b[^%]*%%|%secretsanta|\[#\]", "inline"),
        ("text-token", r"%(?:adj|noun|place|spouse|name|pet|farm|kid1|kid2|fork|book|rival|favorite|firstnameletter|time|band|season)\b", "inline"),
        ("farmer", r"@", "inline"),
        ("narration", r"(?:(?<=#)|(?<=\^)|(?<![\s\S]))%(?=\S)", "inline"),
        ("separator", r"#", "struct"),
        ("gender-split", r"\^|¦", "struct"),
        ("format", r"\{\d+(?::[^{}]*)?\}", "inline"),
        ("so-token", r"\{[A-Za-z]\w*(?::\w+)?\}", "inline"),  # special orders / quests: {Amount1}, {Monster1:LocalizedName}
        ("newline", r"\n", "struct"),
    ],
    "app": [
        ("icu", r"\{[A-Za-z_][\w.]*\}", "inline"),  # plural/select bodies stay translatable; QA checks them
        ("format", r"\{\d+(?::[^{}]*)?\}", "inline"),
        ("printf", r"%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t)?[diouxXeEfgGcsp@%]", "inline"),
        ("mustache", r"\{\{[^{}]+\}\}", "inline"),
        ("html", r"</?[a-zA-Z][^<>]*>", "inline"),
        ("entity", r"&(?:[a-zA-Z]+|#\d+);", "inline"),
        ("newline", r"\n", "struct"),
    ],
    "generic": [
        ("mustache", r"\{\{[^{}]+\}\}", "inline"),
        ("braces", r"\{[A-Za-z0-9_.:-]*\}", "inline"),
        ("printf", r"%(?:\d+\$)?[-+ 0#]*\d*(?:\.\d+)?[sdif@]", "inline"),
        ("html", r"</?[a-zA-Z][^<>]*>", "inline"),
        ("newline", r"\n", "struct"),
    ],
}
GLYPHS = {"smapi": "<>=`"}  # Stardew font glyphs: < heart, > arrow, = star, ` up arrow — counted, not masked
PH_L, PH_R = "\u27e6", "\u27e7"  # ⟦ ⟧
PH_RE = re.compile(re.escape(PH_L) + r"(\d+)" + re.escape(PH_R))


def compile_profile(profile, extra=None):
    rules = list(PROFILES.get(profile, PROFILES["generic"]))
    for i, rx in enumerate(extra or []):
        rules.append((f"custom{i}", rx, "inline"))
    combined = "|".join(f"(?P<r{i}>{rx})" for i, (_, rx, _) in enumerate(rules))
    return rules, re.compile(combined)


def find_tokens(text, profile="smapi", extra=None, _cache={}):
    key = (profile, tuple(extra or []))
    if key not in _cache:
        _cache[key] = compile_profile(profile, extra)
    rules, rx = _cache[key]
    out = []
    for m in rx.finditer(text or ""):
        idx = int(m.lastgroup[1:])
        name, _, kind = rules[idx]
        if m.group(0):
            out.append((m.start(), m.end(), m.group(0), name, kind))
    return out


def mask(text, profile="smapi", extra=None):
    """Replace protected tokens with ⟦n⟧ placeholders. Returns (masked_text, table)."""
    toks = find_tokens(text, profile, extra)
    out, last, table = [], 0, []
    for s, e, tok, name, kind in toks:
        out.append(text[last:s])
        n = len(table) + 1
        table.append({"n": n, "token": tok, "type": name, "kind": kind})
        out.append(f"{PH_L}{n}{PH_R}")
        last = e
    out.append(text[last:])
    return "".join(out), table


def unmask(masked, table):
    """Restore tokens. Returns (text, problems). Never guesses: any mismatch is reported."""
    problems = []
    found = [int(m.group(1)) for m in PH_RE.finditer(masked)]
    want = [t["n"] for t in table]
    by_n = {t["n"]: t for t in table}
    missing = [n for n in want if n not in found]
    extra = [n for n in found if n not in by_n]
    dup = sorted({n for n in found if found.count(n) > 1})
    if missing:
        problems.append("missing tokens: " + ", ".join(repr(by_n[n]["token"]) for n in missing))
    if extra:
        problems.append("unknown placeholders: " + ", ".join(f"{PH_L}{n}{PH_R}" for n in extra))
    if dup:
        problems.append("duplicated tokens: " + ", ".join(repr(by_n[n]["token"]) for n in dup))
    struct_want = [t["n"] for t in table if t["kind"] == "struct"]
    struct_got = [n for n in found if n in by_n and by_n[n]["kind"] == "struct"]
    if not missing and not dup and struct_got != struct_want:
        problems.append("structure tokens moved (dialogue breaks / gender splits / line breaks must keep their order)")
    text = PH_RE.sub(lambda m: by_n[int(m.group(1))]["token"] if int(m.group(1)) in by_n else m.group(0), masked)
    # stray brackets the model may have produced around placeholders
    if PH_L in text or PH_R in text:
        problems.append("leftover placeholder brackets")
    return text, problems


def token_signature(text, profile="smapi", extra=None):
    """(inline multiset, struct sequence) for parity checks between source and translation."""
    toks = find_tokens(text, profile, extra)
    inline = sorted(t[2] for t in toks if t[4] == "inline")
    struct = [t[2] for t in toks if t[4] == "struct"]
    return inline, struct


def glyph_counts(text, profile="smapi"):
    return {g: (text or "").count(g) for g in GLYPHS.get(profile, "")}


# ============================================================================ text utilities

SCRIPTS = {
    "th": (0x0E00, 0x0E7F), "lo": (0x0E80, 0x0EFF), "km": (0x1780, 0x17FF), "my": (0x1000, 0x109F),
    "ja": None, "zh": None, "ko": (0xAC00, 0xD7AF), "ru": (0x0400, 0x04FF), "uk": (0x0400, 0x04FF),
    "ar": (0x0600, 0x06FF), "he": (0x0590, 0x05FF), "el": (0x0370, 0x03FF), "hi": (0x0900, 0x097F),
}
LATIN_TARGETS = {"en", "es", "fr", "de", "it", "pt", "pt-br", "nl", "pl", "tr", "vi", "id", "ms", "tl", "sv", "da", "no", "fi", "cs", "hu", "ro"}


def base_lang(lang):
    return (lang or "").lower().replace("_", "-").split("-")[0] if lang and lang.lower() not in ("pt-br",) else (lang or "").lower()


def is_target_char(ch, lang):
    o = ord(ch)
    b = base_lang(lang)
    if b == "ja":
        return 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9F
    if b == "zh":
        return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
    r = SCRIPTS.get(b)
    return bool(r) and r[0] <= o <= r[1]


def uses_latin(lang):
    return base_lang(lang) in LATIN_TARGETS or base_lang(lang) not in SCRIPTS and base_lang(lang) not in ("ja", "zh")


def strip_tokens(text, profile="smapi", extra=None):
    toks = find_tokens(text, profile, extra)
    out, last = [], 0
    for s, e, *_ in toks:
        out.append(text[last:s])
        out.append(" ")
        last = e
    out.append(text[last:])
    return "".join(out)


def display_width(text):
    """Grapheme-aware width: combining marks (Thai tone marks and vowels above/below, accents) take no space,
    East Asian wide characters take two."""
    w = 0
    for ch in text or "":
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def sha(text):
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


# ============================================================================ project config & file discovery

DEFAULT_CONFIG = {
    "source_lang": "en",
    "target_lang": "th",
    "profile": "smapi",
    "layouts": [
        {"source": "**/i18n/default.json", "target": "{dir}/{lang}.json"},
    ],
    "exclude": ["**/node_modules/**", "**/.git/**", "**/bin/**", "**/obj/**"],
    "glossary": "l10n/glossary.csv",
    "state_dir": "l10n",
    "extra_tokens": [],
    "max_length_ratio": 1.6,
    "dont_translate_keys": [],
}

KNOWN_LAYOUTS = [
    ("smapi", {"source": "**/i18n/default.json", "target": "{dir}/{lang}.json"}),
    ("app", {"source": "**/{src}.json", "target": "{dir}/{lang}.json"}),
    ("app", {"source": "**/locales/{src}/*.json", "target": "{parent}/{lang}/{name}"}),
    ("app", {"source": "**/locales/{src}.json", "target": "{dir}/{lang}.json"}),
    ("app", {"source": "**/i18n/{src}.json", "target": "{dir}/{lang}.json"}),
]


def load_config(root):
    root = Path(root)
    p = root / CONFIG_NAME
    cfg = dict(DEFAULT_CONFIG)
    if p.exists():
        user = json.loads(p.read_text("utf-8"))
        cfg.update(user)
    cfg["_root"] = str(root.resolve())
    cfg["_found"] = p.exists()
    return cfg


def _fmt(pattern, cfg):
    return pattern.replace("{src}", cfg["source_lang"]).replace("{lang}", cfg["target_lang"])


def _excluded(rel, cfg):
    return any(fnmatch.fnmatch(rel, pat) for pat in cfg.get("exclude", []))


def discover(cfg):
    """List (source_path, target_path, group_name) for every source file the layouts match."""
    root = Path(cfg["_root"])
    out, seen = [], set()
    for lay in cfg["layouts"]:
        pat = _fmt(lay["source"], cfg)
        for sp in sorted(_glob.glob(str(root / pat), recursive=True)):
            spath = Path(sp)
            rel = spath.relative_to(root).as_posix()
            if rel in seen or _excluded(rel, cfg):
                continue
            seen.add(rel)
            tpl = _fmt(lay["target"], cfg)
            tp = (tpl.replace("{dir}", str(spath.parent)).replace("{parent}", str(spath.parent.parent))
                  .replace("{name}", spath.name).replace("{stem}", spath.stem))
            tpath = Path(tp)
            if tpath.resolve() == spath.resolve():
                continue
            out.append((spath, tpath, group_name(spath, root)))
    return out


def group_name(spath, root):
    """Human name for a file set: the mod/package folder (skips i18n/locales/[CP] wrappers)."""
    parts = list(spath.relative_to(root).parts[:-1])
    skip = {"i18n", "locales", "locale", "lang", "langs", "translations", "assets", "src", "res"}
    parts = [p for p in parts if p.lower() not in skip]
    if len(parts) >= 2 and re.match(r"^\[[A-Z]{2,4}\]", parts[-1]) and not re.match(r"^\[[A-Z]{2,4}\]", parts[-2]):
        return parts[-2]
    if parts:
        return parts[-1]
    return Path(root).name or spath.stem  # app projects: the project folder, not "en"


def detect_config(root, target_lang=None):
    """Guess profile, languages and layout from the files present."""
    root = Path(root)
    cfg = dict(DEFAULT_CONFIG)
    cfg["_root"] = str(root.resolve())
    smapi = _glob.glob(str(root / "**/i18n/default.json"), recursive=True)
    manifests = _glob.glob(str(root / "**/manifest.json"), recursive=True)
    if smapi or manifests:
        cfg["profile"] = "smapi"
        cfg["layouts"] = [{"source": "**/i18n/default.json", "target": "{dir}/{lang}.json"}]
        if not target_lang:
            langs = {}
            for f in _glob.glob(str(root / "**/i18n/*.json"), recursive=True):
                stem = Path(f).stem
                if stem != "default" and re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2,4})?", stem):
                    langs[stem] = langs.get(stem, 0) + 1
            target_lang = max(langs, key=langs.get) if langs else "th"
    else:
        cfg["profile"] = "app"
        files = [Path(f) for f in _glob.glob(str(root / "**/*.json"), recursive=True) if "node_modules" not in f]
        names = {}
        for f in files:
            if re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2,4})?", f.stem):
                names.setdefault(f.parent, set()).add(f.stem)
        cfg["source_lang"] = "en"
        if names:
            d, ls = max(names.items(), key=lambda kv: len(kv[1]))
            if not target_lang:
                others = sorted(ls - {"en"})
                target_lang = others[0] if others else "th"
            rel = Path(d).relative_to(root).as_posix()
            cfg["layouts"] = [{"source": (rel + "/" if rel != "." else "") + "{src}.json", "target": "{dir}/{lang}.json"}]
    cfg["target_lang"] = target_lang or "th"
    return cfg


def save_config(cfg):
    p = Path(cfg["_root"]) / CONFIG_NAME
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return p


# ============================================================================ glossary (shared CSV)

GLOSSARY_FIELDS = ["source", "target", "type", "status", "case_sensitive", "note", "count"]


def load_glossary(path):
    import csv
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = [dict(r) for r in csv.DictReader(f)]
    return [r for r in rows if (r.get("source") or "").strip()]


def save_glossary(path, rows):
    import csv
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GLOSSARY_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in GLOSSARY_FIELDS})


def glossary_hits(text, glossary):
    """Glossary entries whose source term appears in text (word-boundary, case-insensitive unless flagged)."""
    hits = []
    for g in glossary:
        if (g.get("status") or "approved") in ("rejected",):
            continue
        term = g["source"]
        flags = 0 if str(g.get("case_sensitive", "")).lower() in ("1", "true", "yes") else re.I
        if re.search(r"(?<![\w])" + re.escape(term) + r"(?![\w])", text or "", flags):
            hits.append(g)
    hits.sort(key=lambda g: -len(g["source"]))
    return hits
# --- END L10N CORE ---
