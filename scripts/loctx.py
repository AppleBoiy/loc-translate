#!/usr/bin/env python3
"""loc-translate: translate i18n files without breaking game/app tokens or file layout.

Standard library only. No network access — the agent does the translating; this script
prepares safe work batches and verifies every translation before writing it.

  init      detect project layout (SMAPI mods, app locale files) and write .l10n.json
  scan      coverage per file set: translated / missing / same-as-source
  prepare   write work batches: source text with tokens replaced by ⟦n⟧ placeholders,
            translator notes, context lines, glossary terms, reusable translations
  apply     verify the agent's translations (tokens, order, glyphs) and write them into
            the target files, preserving comments, key order and formatting; failures
            go to a retry batch
  review    side-by-side review page (l10n/review.html) of the latest applied batch
  status    progress of prepared batches
"""
import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# @@CORE-IMPORT@@
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from l10n_core import *  # noqa: F401,F403  (inlined into this file when packaged)
# @@END-CORE-IMPORT@@

VERSION = "1.0.0"

TOKEN_HELP = {
    "cp-token": "Content Patcher / i18n token — keep exactly, never translate the text inside",
    "dialogue-cmd": "dialogue command (break, question, response…) — keep exactly where it is",
    "portrait": "portrait expression code — keep it at the end of the same sentence",
    "mail-cmd": "mail attachment / title marker — keep exactly",
    "text-token": "game text variable (player farm, pet name…) — keep; it is replaced in-game",
    "farmer": "the player's name — keep; you may move it to fit the grammar",
    "narration": "narration marker — keep at the start of this segment",
    "separator": "dialogue box break — keep: the text before and after it are separate boxes",
    "gender-split": "dialogue: male^female variants (translate both sides) · mail/letters: line break — keep, in order",
    "format": "numbered format slot — keep; you may move it",
    "newline": "line break — keep",
    "icu": "named placeholder — keep; you may move it",
    "printf": "printf placeholder — keep; you may move it",
    "mustache": "template placeholder — keep; you may move it",
    "html": "markup tag — keep and keep it wrapping the same words",
    "entity": "HTML entity — keep",
    "braces": "placeholder — keep; you may move it",
}


def log(m):
    print(m, file=sys.stderr)


def today():
    return _dt.date.today().isoformat()


def get_cfg(a):
    root = Path(a.root).resolve()
    cfg = load_config(root)
    if not cfg["_found"]:
        cfg = detect_config(root)
        cfg["_found"] = False
    return cfg


def state_dir(cfg):
    p = Path(cfg["_root"]) / cfg.get("state_dir", "l10n")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ----------------------------------------------------------------------------- init / scan

def cmd_init(a):
    root = Path(a.root).resolve()
    if (root / CONFIG_NAME).exists() and not a.force:
        cfg = load_config(root)
        log(f"{CONFIG_NAME} already exists (use --force to re-detect)")
    else:
        cfg = detect_config(root, a.target)
        if a.target:
            cfg["target_lang"] = a.target
        if a.source:
            cfg["source_lang"] = a.source
        if a.profile:
            cfg["profile"] = a.profile
        p = save_config(cfg)
        log(f"wrote {p}")
    sets = discover(cfg)
    print(f"profile={cfg['profile']}  {cfg['source_lang']} → {cfg['target_lang']}  layouts={[l['source'] for l in cfg['layouts']]}")
    print(f"{len(sets)} file sets found")
    for s, t, g in sets[:40]:
        print(f"  {g:<40} {Path(s).relative_to(root)}  →  {Path(t).name}{'' if Path(t).exists() else '  (new)'}")
    if not sets:
        print("No source files matched. Edit 'layouts' in .l10n.json (source glob + target pattern).")


def coverage(cfg):
    rows = []
    for s, t, g in discover(cfg):
        src = load_doc(s)
        sd = src.as_dict()
        dont = set(cfg.get("dont_translate_keys", []))
        td = load_doc(t).as_dict() if Path(t).exists() else {}
        translatable = {k: v for k, v in sd.items() if k not in dont and strip_tokens(v, cfg["profile"]).strip()}
        missing = [k for k in translatable if k not in td]
        same = [k for k in translatable if k in td and td[k] == translatable[k] and re.search(r"[A-Za-z]{3}", strip_tokens(td[k], cfg["profile"]))]
        done = len(translatable) - len(missing) - len(same)
        rows.append({"group": g, "source": str(s), "target": str(t), "total": len(translatable), "done": done,
                     "missing": missing, "same": same, "extra": [k for k in td if k not in sd]})
    return rows


def cmd_scan(a):
    cfg = get_cfg(a)
    rows = coverage(cfg)
    tot = sum(r["total"] for r in rows)
    done = sum(r["done"] for r in rows)
    print(f"{'file set':<42} {'done':>6} {'total':>6} {'missing':>8} {'same':>6}  coverage")
    for r in sorted(rows, key=lambda r: (r["done"] / r["total"] if r["total"] else 1)):
        pct = 100 * r["done"] / r["total"] if r["total"] else 100
        bar = "█" * int(pct / 5) + "·" * (20 - int(pct / 5))
        print(f"{r['group'][:42]:<42} {r['done']:>6} {r['total']:>6} {len(r['missing']):>8} {len(r['same']):>6}  {bar} {pct:5.1f}%")
    print(f"{'TOTAL':<42} {done:>6} {tot:>6}  {100 * done / tot if tot else 100:.1f}%")
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))


# ----------------------------------------------------------------------------- prepare

def speaker_hint(key, profile):
    """Stardew keys often name the speaker: 'SpiritEve.Aguar.1-2heart', 'Characters/Dialogue/Abigail:...'."""
    if profile != "smapi":
        return ""
    parts = [m.group(1) for p in re.split(r"[./:_\-]", key) for m in [re.match(r"([A-Z][a-z]{2,})", p)] if m]
    caps = [p for p in parts if p not in
            {"Name", "Description", "Desc", "Title", "Text", "Config", "Setting", "Option", "Tooltip", "Event", "Mail", "Quest",
             "Item", "Object", "Location", "Dialogue", "Strings", "Message", "Label", "Spouse", "Marriage", "Heart"}]
    return caps[0] if caps else ""


def build_tm(cfg):
    """Translation memory from every existing translation in the project: exact source → target."""
    tm = defaultdict(Counter)
    for s, t, g in discover(cfg):
        if not Path(t).exists():
            continue
        sd, td = load_doc(s).as_dict(), load_doc(t).as_dict()
        for k, v in sd.items():
            if k in td and td[k] != v and td[k].strip():
                tm[v][td[k]] += 1
    return {src: c.most_common(1)[0][0] for src, c in tm.items()}


def cmd_prepare(a):
    cfg = get_cfg(a)
    prof, extra = cfg["profile"], cfg.get("extra_tokens", [])
    gl = load_glossary(Path(cfg["_root"]) / cfg["glossary"])
    tm = build_tm(cfg) if not a.no_reuse else {}
    work = state_dir(cfg) / "work"
    work.mkdir(parents=True, exist_ok=True)
    rows = coverage(cfg)
    sets = {r["group"]: r for r in rows}
    items, autofilled = [], 0
    for s, t, g in discover(cfg):
        if a.group and not any(x.lower() in g.lower() for x in a.group):
            continue
        r = sets[g]
        src = load_doc(s)
        sd, notes = src.as_dict(), src.notes()
        td = load_doc(t).as_dict() if Path(t).exists() else {}
        if a.keys:
            wanted = [k for k in sd if k in set(a.keys)]
        elif a.mode == "all":
            wanted = [k for k in sd if k in set(r["missing"]) | set(r["same"]) | set(td)]
        elif a.mode == "missing":
            wanted = r["missing"]
        else:  # todo = missing + same-as-source
            wanted = r["missing"] + r["same"]
        keys = list(sd)
        for k in wanted:
            v = sd[k]
            if k in cfg.get("dont_translate_keys", []) or re.search(r"don'?t translate|do not translate|DNT", notes.get(k, ""), re.I):
                continue
            m, table = mask(v, prof, extra)
            i = keys.index(k)
            item = {
                "id": f"{g}::{k}", "group": g, "key": k, "source": m,
                "tokens": {f"{PH_L}{t_['n']}{PH_R}": f"{t_['token']!r} — {TOKEN_HELP.get(t_['type'], 'keep exactly')}" for t_ in table},
                "note": notes.get(k, ""),
                "speaker": speaker_hint(k, prof),
                "context_before": sd[keys[i - 1]][:160] if i > 0 else "",
                "context_after": sd[keys[i + 1]][:160] if i + 1 < len(keys) else "",
                "glossary": [{"source": h["source"], "target": h["target"], "note": h.get("note", "")} for h in glossary_hits(v, gl) if h.get("target")],
                "current": td.get(k, "") if td.get(k, "") != v else "",
                "source_width": display_width(strip_tokens(v, prof)),
                "_table": table, "_source_raw": v, "_target": str(t), "_source_file": str(s),
            }
            if v in tm and not a.no_reuse:
                item["reuse"] = mask(tm[v], prof, extra)[0]
                if a.autofill_exact:
                    autofilled += 1
                    item["_autofill"] = tm[v]
            items.append(item)
    if not items:
        print("Nothing to translate for the chosen files and mode.")
        return
    auto = [i for i in items if "_autofill" in i]
    if auto:
        write_targets(cfg, {i["id"]: i["_autofill"] for i in auto}, {i["id"]: i for i in auto})
        items = [i for i in items if "_autofill" not in i]
        log(f"auto-filled {len(auto)} strings from identical earlier translations")
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    n_batches = 0
    for bi in range(0, len(items), a.batch):
        chunk = items[bi:bi + a.batch]
        n_batches += 1
        name = f"batch-{stamp}-{n_batches:03d}"
        public = [{k: v for k, v in it.items() if not k.startswith("_") and v not in ("", [], {})} for it in chunk]
        doc = {
            "batch": name, "created": today(), "source_lang": cfg["source_lang"], "target_lang": cfg["target_lang"],
            "profile": prof,
            "instructions": (
                f"Translate each item's 'source' from {cfg['source_lang']} into {cfg['target_lang']}. "
                f"Every {PH_L}n{PH_R} placeholder must appear exactly once in your translation, written exactly as given. "
                "Placeholders marked as breaks, splits or line breaks must stay in the same order. "
                "Use the 'glossary' targets for those terms. Respect 'note' (translator notes from the file). "
                "'speaker' and 'context_*' are for tone only. If 'reuse' is present, it is an earlier translation of the identical text — prefer it. "
                f"Write the answers to {name}.out.json as {{\"<id>\": \"<translation>\"}}."),
            "items": public,
        }
        (work / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
        (work / f"{name}.private.json").write_text(json.dumps({it["id"]: {k: it[k] for k in ("_table", "_source_raw", "_target", "_source_file", "key")} for it in chunk}, ensure_ascii=False), "utf-8")
    print(f"prepared {len(items)} strings in {n_batches} batch(es) → {work}")
    print(f"glossary terms used: {sum(1 for i in items if i.get('glossary'))} items · reusable translations offered: {sum(1 for i in items if 'reuse' in i)}")


# ----------------------------------------------------------------------------- apply

def write_targets(cfg, translations, meta):
    """translations: id -> final text; meta: id -> dict with _target, _source_file, key."""
    by_target = defaultdict(dict)
    for iid, txt in translations.items():
        m = meta[iid]
        by_target[(m["_target"], m["_source_file"])][m["key"]] = txt
    for (tpath, spath), vals in by_target.items():
        src = load_doc(spath)
        if Path(tpath).exists():
            doc = load_doc(tpath)
            existing = set(doc.keys())
            doc.set_many({k: v for k, v in vals.items() if k in existing})
            new = [(k, vals[k]) for k in src.keys() if k in vals and k not in existing]
            if new:
                order = src.keys()
                pos = {k: i for i, k in enumerate(order)}
                existing_in_src = sorted((pos[k], k) for k in existing if k in pos)
                src_entries = {e.key: e for e in src.entries}
                before, after, have = {}, {}, set(existing)
                for k, _ in new:
                    nxt = next((ek for ei, ek in existing_in_src if ei > pos[k]), None)
                    # the source file decides which side of a comment block the key belongs on
                    between = src.text[src_entries[k].vend:src_entries[nxt].kstart] if nxt else ""
                    if nxt and "//" not in between and "/*" not in between:
                        before[k] = nxt
                    else:
                        after[k] = next((order[j] for j in range(pos[k] - 1, -1, -1) if order[j] in have), None)
                    have.add(k)
                b_pairs = [(k, v) for k, v in new if k in before]
                a_pairs = [(k, v) for k, v in new if k not in before]
                if b_pairs:
                    doc.insert_before(b_pairs, before)
                if a_pairs:
                    doc.insert(a_pairs, after=after)
        else:
            doc = doc_from_template(src, vals, drop_missing=not cfg.get("keep_untranslated_in_new_files", True))
            doc.path = tpath
        doc.save(tpath)


def verify(text, it, cfg):
    prof = cfg["profile"]
    restored, problems = unmask(text, it["_table"])
    src = it["_source_raw"]
    if not problems:
        gs, gt = glyph_counts(src, prof), glyph_counts(restored, prof)
        for g, n in gs.items():
            if gt.get(g, 0) != n:
                problems.append(f"special glyph {g!r} count changed ({n} → {gt.get(g, 0)})")
        if src.strip() and not restored.strip():
            problems.append("empty translation")
        if restored != restored.strip() and src == src.strip():
            restored = restored.strip()
        if not uses_latin(cfg["target_lang"]):
            body = strip_tokens(restored, prof)
            if re.search(r"[A-Za-z]{3,}", strip_tokens(src, prof)) and not any(is_target_char(c, cfg["target_lang"]) for c in body):
                problems.append(f"no {cfg['target_lang']} text — looks untranslated")
    return restored, problems


def cmd_apply(a):
    cfg = get_cfg(a)
    work = state_dir(cfg) / "work"
    batches = [Path(b) for b in a.batches] if a.batches else sorted(work.glob("batch-*.out.json"))
    if not batches:
        sys.exit(f"no *.out.json files in {work}")
    ok_all, bad_all, total = {}, [], 0
    meta_all = {}
    for out in batches:
        name = out.name.replace(".out.json", "")
        priv_p = out.with_name(f"{name}.private.json")
        pub_p = out.with_name(f"{name}.json")
        if not priv_p.exists():
            log(f"skip {out.name}: no matching {priv_p.name}")
            continue
        priv = json.loads(priv_p.read_text("utf-8"))
        pub = {i["id"]: i for i in json.loads(pub_p.read_text("utf-8"))["items"]}
        answers = json.loads(out.read_text("utf-8"))
        for iid, txt in answers.items():
            total += 1
            if iid not in priv:
                bad_all.append((iid, ["id not in this batch"], None))
                continue
            it = dict(priv[iid])
            meta_all[iid] = it
            if not isinstance(txt, str):
                bad_all.append((iid, ["answer is not a string"], pub.get(iid)))
                continue
            restored, problems = verify(txt, it, cfg)
            if problems:
                bad_all.append((iid, problems, dict(pub.get(iid, {}), rejected=txt, problems=problems)))
            else:
                ok_all[iid] = restored
        missing = [i for i in pub if i not in answers]
        for iid in missing:
            bad_all.append((iid, ["no answer"], pub[iid]))
            meta_all.setdefault(iid, priv[iid])
    if ok_all and not a.dry_run:
        write_targets(cfg, ok_all, meta_all)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_rows = []
    for out in batches:
        pub_p = out.with_name(out.name.replace(".out.json", ".json"))
        if pub_p.exists():
            for it in json.loads(pub_p.read_text("utf-8"))["items"]:
                iid = it["id"]
                row = {"id": iid, "group": it.get("group"), "key": it.get("key"), "speaker": it.get("speaker", ""),
                       "source": meta_all.get(iid, {}).get("_source_raw", ""), "glossary": it.get("glossary", []), "note": it.get("note", "")}
                if iid in ok_all:
                    row.update(status="written", translation=ok_all[iid])
                else:
                    prob = next((b[1] for b in bad_all if b[0] == iid), ["not answered"])
                    raw = json.loads(out.read_text("utf-8")).get(iid, "") if out.exists() else ""
                    row.update(status="rejected", translation=raw, problems=prob)
                log_rows.append(row)
    if log_rows and not a.dry_run:
        (work / f"applied-{stamp}.json").write_text(json.dumps(log_rows, ensure_ascii=False, indent=1), "utf-8")
    print(f"checked {total} answers: {len(ok_all)} written{' (dry run)' if a.dry_run else ''}, {len(bad_all)} rejected")
    for iid, probs, _ in bad_all[:25]:
        print(f"  ✗ {iid}: {'; '.join(probs)}")
    if bad_all:
        retry = [b[2] for b in bad_all if b[2]]
        if retry:
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"batch-{stamp}-retry"
            priv = {b[0]: meta_all[b[0]] for b in bad_all if b[2] and b[0] in meta_all}
            doc = {"batch": name, "created": today(), "source_lang": cfg["source_lang"], "target_lang": cfg["target_lang"],
                   "profile": cfg["profile"],
                   "instructions": f"These translations were rejected; each item has 'rejected' (your last answer) and 'problems'. Fix them and write {name}.out.json.",
                   "items": retry}
            (work / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")
            (work / f"{name}.private.json").write_text(json.dumps(priv, ensure_ascii=False), "utf-8")
            print(f"retry batch → {work / (name + '.json')}")
    if not a.dry_run:
        for out in batches:
            done = out.with_name(out.name.replace(".out.json", ".done.json"))
            out.rename(done)


def cmd_review(a):
    """Side-by-side review page of applied translations (latest apply by default)."""
    cfg = get_cfg(a)
    work = state_dir(cfg) / "work"
    logs = sorted(work.glob("applied-*.json"))
    if not logs:
        sys.exit("nothing applied yet — run apply first")
    pick = logs if a.all else logs[-1:]
    rows = []
    for lp in pick:
        rows += json.loads(lp.read_text("utf-8"))
    import html as _html
    payload = {"title": a.title or f"Translation review · {cfg['source_lang']} → {cfg['target_lang']}",
               "generated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "project": Path(cfg["_root"]).name,
               "source_lang": cfg["source_lang"], "target_lang": cfg["target_lang"], "profile": cfg["profile"], "rows": rows,
               "batches": [p.name for p in pick]}
    tpl = load_template("review.html")
    out = Path(a.out or (state_dir(cfg) / "review.html"))
    out.write_text(tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
                   .replace("__TITLE__", _html.escape(payload["title"])), "utf-8")
    ok = sum(1 for r in rows if r["status"] == "written")
    print(f"review → {out}  ({ok} written, {len(rows) - ok} rejected)")


def load_template(name):
    emb = globals().get("EMBEDDED_TEMPLATES", {})
    if name in emb:
        return emb[name]
    return (Path(__file__).resolve().parent.parent / "assets" / name).read_text("utf-8")


def cmd_status(a):
    cfg = get_cfg(a)
    work = state_dir(cfg) / "work"
    rows = []
    for b in sorted(work.glob("batch-*.json")):
        if b.name.endswith((".private.json", ".out.json", ".done.json")):
            continue
        n = len(json.loads(b.read_text("utf-8"))["items"])
        st = "applied" if b.with_name(b.stem + ".done.json").exists() else ("answered" if b.with_name(b.stem + ".out.json").exists() else "waiting")
        rows.append((b.stem, n, st))
    for r in rows:
        print(f"{r[0]:<36} {r[1]:>4} strings  {r[2]}")
    if not rows:
        print("no batches yet — run prepare")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="loctx.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--root", default=".", help="project root (where .l10n.json lives)")

    s = sub.add_parser("init", help="detect layout and write .l10n.json")
    common(s)
    s.add_argument("--target", help="target language code, e.g. th, ja, pt-BR")
    s.add_argument("--source", help="source language code (default en)")
    s.add_argument("--profile", choices=sorted(PROFILES), help="token profile")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("scan", help="coverage per file set")
    common(s)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_scan)

    s = sub.add_parser("prepare", help="write translation batches")
    common(s)
    s.add_argument("--group", nargs="*", help="only file sets whose name contains these words")
    s.add_argument("--keys", nargs="*", help="only these keys")
    s.add_argument("--mode", choices=["todo", "missing", "all"], default="todo",
                   help="todo = missing + same-as-source (default); all = also re-translate existing")
    s.add_argument("--batch", type=int, default=40, help="strings per batch")
    s.add_argument("--no-reuse", action="store_true", help="don't offer earlier translations of identical text")
    s.add_argument("--autofill-exact", action="store_true", help="write identical earlier translations directly")
    s.set_defaults(fn=cmd_prepare)

    s = sub.add_parser("apply", help="verify answers and write target files")
    common(s)
    s.add_argument("batches", nargs="*", help="*.out.json files (default: all in l10n/work)")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("review", help="write l10n/review.html for human review")
    common(s)
    s.add_argument("--all", action="store_true", help="include every applied batch, not just the latest")
    s.add_argument("--out")
    s.add_argument("--title")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("status", help="batch progress")
    common(s)
    s.set_defaults(fn=cmd_status)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
