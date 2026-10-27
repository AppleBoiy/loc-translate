---
name: loc-translate
description: Translates game-mod and app localization files (SMAPI/Stardew Valley i18n, Content Patcher, JSON/JSONC locale files) into any language without breaking them — every game or app token is locked behind a numbered placeholder and verified on the way back, translator comments, key order and formatting are preserved, glossary terms are applied and identical strings are reused. Use when someone asks to translate a mod, i18n folder, locale JSON or app strings, finish a partial translation, or translate new keys after an update.
---

# Loc Translate

Translate localization files the way a careful human localizer would — but without ever breaking a token, a dialogue command or the file itself.

Part of the Localization Kit: `glossary-forge` (terms) → **`loc-translate`** → `loc-qa` (checks + report) → `loc-sync` (updates). They share `.l10n.json` and `l10n/glossary.csv`.

## Non-negotiable rules

1. **Never edit target files by hand or by rewriting them.** All writes go through `scripts/loctx.py apply`, which verifies every string and keeps comments, key order and formatting intact.
2. **Placeholders are sacred.** Each `⟦n⟧` must appear exactly once in your translation, unchanged. Break/split/line-break placeholders keep their order. Read the `tokens` legend on each item — it says what each placeholder is and whether it may move.
3. **Respect translator notes.** Items flagged "don't translate" in the file's comments are skipped automatically; follow any other `note`.
4. **Use the glossary.** If an item lists `glossary` terms, use those target terms. If a term seems wrong, finish the batch with the glossary term and tell the user which term to review.
5. Don't invent content, add jokes, or "improve" the original meaning.

## 1. Set up (once per project)

```bash
python3 scripts/loctx.py init --target th        # any language code: ja, zh-CN, pt-BR, es, de…
python3 scripts/loctx.py scan                    # coverage per mod / file set
```

`init` detects the layout and writes `.l10n.json`:
- **SMAPI / Stardew mods:** `**/i18n/default.json` → `i18n/<lang>.json`, profile `smapi` (protects `{{tokens}}`, `#$b#`, `$h`, `@`, `^`, `%` narration, `{0}`, mail commands, line breaks; counts the font glyphs `< > = \``).
- **Apps / web:** `en.json` → `<lang>.json` (or `locales/en/*.json`), profile `app` (protects `{name}`, `{0}`, `%s`/`%1$d`, `{{x}}`, HTML tags, entities, line breaks).
- Anything else: edit `layouts` in `.l10n.json` — a `source` glob and a `target` pattern using `{dir}`, `{lang}`, `{name}`, `{parent}`. Add project-specific tokens as regexes in `extra_tokens`.

If the user has a glossary, put it at `l10n/glossary.csv` (columns `source,target,type,status,note`), or run `glossary-forge` first — it mines one from existing translations.

## 2. Prepare batches

```bash
python3 scripts/loctx.py prepare                 # missing + still-in-source-language strings
python3 scripts/loctx.py prepare --group "Better Crafting" --batch 40
python3 scripts/loctx.py prepare --autofill-exact   # also write identical earlier translations directly
```

Each `l10n/work/batch-*.json` item has: `source` (with `⟦n⟧` placeholders), `tokens` (legend), `note`, `speaker` (guessed from the key, e.g. `Javi`), `context_before/after`, `glossary`, `current` (an existing translation, when re-translating) and `reuse` (an earlier translation of identical text).

## 3. Translate

For each batch: read `references/style-game-dialogue.md` once, and the target-language guide if one exists (`references/lang-th.md` for Thai). Then translate every item and write `l10n/work/<batch>.out.json`:

```json
{ "<id>": "<translation with the same ⟦n⟧ placeholders>" }
```

Translate in batches of ~40, in key order, keeping each character's voice consistent across items (use `speaker`). Keep UI strings (settings, buttons, tooltips) short — the item's `source_width` tells you how long the original is.

## 4. Apply and fix rejects

```bash
python3 scripts/loctx.py apply
```

`apply` restores the tokens, checks that none are missing, duplicated or reordered, that special glyphs survive, and that the text is actually in the target language; then writes good strings into the target files (new files mirror the source file's layout and comments). Rejected strings go to `batch-*-retry.json` with the reason — fix those and run `apply` again until nothing is rejected.

```bash
python3 scripts/loctx.py scan       # confirm coverage
```

## 5. Deliver

Tell the user, briefly:
1. Coverage before → after per mod/file set (from `scan`).
2. Anything you were unsure about: glossary terms that felt wrong, ambiguous speakers, strings that are probably too long for their UI.
3. That `loc-qa` can produce a full QA report, and `loc-sync` keeps the translation current when the original updates.

## No terminal

Translate the strings in conversation, but **never write placeholders back by hand into a file you haven't parsed**. Give the user the translations as a key → text table and tell them that verified writing needs the script.
