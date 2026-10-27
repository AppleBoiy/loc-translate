# Thai (th) localization guide

## Script and spacing
- Thai has no spaces between words. Use a space only where Thai uses one: between sentences/clauses, around numbers and Latin words, and before ๆ only when it ends a phrase.
- No full stop at the end of sentences. `?` and `!` are fine in game dialogue.
- Use `...` or `…` consistently with the rest of the file.
- Use Arabic digits (1, 2, 3) in games and apps, not Thai digits, unless the file already does otherwise.
- Tone marks and above/below vowels take no width — line length is measured in base characters, so Thai often fits where the character count looks long.

## Politeness and voice
- Sentence-final particles carry the speaker's gender and politeness: male speakers `ครับ`, female speakers `ค่ะ` (statements) / `คะ` (questions). Casual speech drops them or uses `นะ`, `ล่ะ`, `จ้ะ`, `เว้ย`, `ว่ะ` depending on character.
- The particle follows the **speaker**, not the listener. In a `male^female` split (`^`) the variants are about the *player*, so both sides keep the speaker's own particle.
- Pronouns set the voice: `ผม` (male, polite), `ฉัน`/`ดิฉัน` (female/neutral), `เรา` (friendly), `ข้า`/`เจ้า` (archaic, fantasy, rough), `กู`/`มึง` (very rough — only if the original is clearly crude).
- Address the player with `คุณ` + name for polite characters, the name alone for friends, `เจ้า`/`แก` for rough or old-fashioned speakers.

## Words
- Prefer Thai words players actually use; established game loanwords are fine (`มอนสเตอร์`, `เควส`, `ไอเทม`, `ฟาร์ม`).
- Transliterate names by sound, consistently (glossary). Don't add the English in parentheses.
- UI: short verbs (`บันทึก`, `ยกเลิก`, `เปิด/ปิด`), no politeness particles.
