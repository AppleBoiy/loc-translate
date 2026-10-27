# Translating game dialogue and UI

## Voice
- Each character keeps one voice across every line: formality, pronouns, sentence-final particles, verbal tics. Decide it from their first few lines (use `speaker`) and keep it.
- Children, elders, rough characters and royalty sound different — in many languages that difference is grammatical (honorifics, particles, pronoun choice), not only word choice.
- The player character (`@`) is addressed the way the speaker would address a friend/acquaintance at that relationship stage — heart-event lines often get warmer as hearts rise.

## Dialogue structure (Stardew / SMAPI)
| Token | Meaning | Rule |
|---|---|---|
| `#` | new dialogue box | Keep the same number of boxes, in order. Never merge or split boxes. |
| `#$b#` | box break | Same as above. |
| `#$e#` | end of the conversation chunk | Keep. |
| `$h $s $u $l $a $0…` | portrait expression | Keep at the end of the same sentence it followed. |
| `@` | player's name | Keep; move freely to fit grammar. |
| `^` | male^female variants | Translate both sides; each side must read naturally on its own. |
| `%` at segment start | narration (no speaker) | Keep; write it as narration, not speech. |
| `%adj %noun %place %spouse %pet %farm %kid1 …` | in-game substitutions | Keep; make the sentence work for any value. |
| `{{Token}}` | Content Patcher / i18n token | Keep exactly; text inside is code, not English. |
| `{0} {1}` | format slots | Keep; reorder freely. |
| `< > = \`` | font glyphs (heart, arrow, star, up-arrow) | Keep the same count. |
| `$q`, `$r` + numbers | questions / responses | Translate the question/answer text, never the IDs after them. |

## UI strings
- Settings, buttons and tooltips: shortest natural wording. Long translations overflow menus.
- Config option names often appear next to the English setting key in GMCM — keep them recognisable.
- Don't add the English in parentheses ("ชื่อ (Name)") — use a glossary term instead.

## Names and terms
- Character and place names: transliterate consistently; use the glossary.
- Item names: translate meaning where the original is descriptive ("Lava Dragon Egg"); transliterate brand-like names ("Junimo").
- Never translate keys, IDs, file names, mod names that are proper names, or anything in a "don't translate" note.
