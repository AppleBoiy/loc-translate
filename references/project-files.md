# Localization Kit — project files

All four skills (`loc-translate`, `glossary-forge`, `loc-qa`, `loc-sync`) share these files at the project root.

## `.l10n.json`

Created by `loc-translate init` (or auto-detected by any skill when missing).

```json
{
  "source_lang": "en",
  "target_lang": "th",
  "profile": "smapi",
  "layouts": [{ "source": "**/i18n/default.json", "target": "{dir}/{lang}.json" }],
  "exclude": ["**/node_modules/**", "**/.git/**"],
  "glossary": "l10n/glossary.csv",
  "state_dir": "l10n",
  "extra_tokens": [],
  "max_length_ratio": 1.6,
  "dont_translate_keys": [],
  "qa_ignore": []
}
```

| Field | Meaning |
|---|---|
| `profile` | Token rules. `smapi`: Stardew/SMAPI/Content Patcher (`{{x}}`, `#$b#`, `$h`, `@`, `^`, `%`, `{0}`, `{Amount1}`, mail commands, line breaks; counts font glyphs `< > = \``). `app`: `{name}`, `{0}`, `%s`/`%1$d`/`%@`, `{{x}}`, HTML tags and entities. `generic`: braces, printf, tags. |
| `layouts` | `source` is a glob (`{src}` = source language). `target` builds the translation path: `{dir}` source folder, `{parent}` its parent, `{name}`/`{stem}` source file name, `{lang}` target language. |
| `extra_tokens` | Extra regexes to protect, e.g. `"\\[[A-Z_]+\\]"` for `[PLAYER_NAME]`. |
| `max_length_ratio` | `loc-qa` flags UI strings wider than this × the source (display width; Thai marks count as 0, CJK as 2). |
| `dont_translate_keys` | Keys never sent for translation (also any key whose comment says "don't translate"). |
| `qa_ignore` | Reviewed `loc-qa` findings to hide: patterns over `check:group::key`. |

## File format support

Flat JSON objects of strings, with or without JSONC extras (comments `//` `/* */`, trailing commas, BOM, CRLF). Edits change only the values (or insert/remove whole lines); comments, key order, indentation and line endings are kept. Comments directly above or beside a key are read as translator notes.

## `l10n/glossary.csv`

`source,target,type,status,case_sensitive,note,count` — `status` is `approved`, `candidate` or `rejected`. `loc-translate` offers approved and candidate terms; `loc-qa` enforces approved ones.

## `l10n/`

Working files: `work/` (translation batches), `qa.json`, `qa-report.html`, `sync/` (per-file-set fingerprints and history), `sync-report.html/.md`, `glossary.html`.
