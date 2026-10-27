import json
import re
import unittest
from common import Project, load_script

tx = load_script("loctx")
core = tx  # core names are imported into the script


class TranslateTest(unittest.TestCase):
    def setUp(self):
        self.p = Project("mods")

    def tearDown(self):
        self.p.close()

    def test_init_detects_smapi(self):
        code, out = self.p.run(tx, "init")
        self.assertEqual(code, 0, out)
        cfg = json.loads((self.p.root / ".l10n.json").read_text())
        self.assertEqual(cfg["profile"], "smapi")
        self.assertEqual(cfg["target_lang"], "th")
        self.assertIn("Moonlit Orchard", out)

    def test_prepare_apply_roundtrip(self):
        self.p.run(tx, "init")
        code, out = self.p.run(tx, "prepare", "--batch", "50")
        self.assertEqual(code, 0, out)
        batch = next((self.p.root / "l10n/work").glob("batch-*[0-9].json"))
        items = json.loads(batch.read_text())["items"]
        keys = {i["key"] for i in items}
        self.assertIn("Quest.Objective", keys)           # missing
        self.assertIn("StarJam.Name", keys)              # still English
        self.assertNotIn("Placeholder", keys)            # "don't translate" note respected
        q = next(i for i in items if i["key"] == "Quest.Objective")
        self.assertNotIn("{Amount1}", q["source"])       # token masked
        self.assertIn("⟦", q["source"])
        answers = {}
        for it in items:
            ph = re.findall("⟦\\d+⟧", it["source"])
            answers[it["id"]] = "ข้อความ " + " ".join(ph) if ph else "ข้อความแปล"
        bad = next(i for i in items if i["key"] == "Config.Speed.Desc")
        answers[bad["id"]] = "ข้อความที่ทำ token หาย"   # drops every token → must be rejected
        (batch.with_name(batch.stem + ".out.json")).write_text(json.dumps(answers, ensure_ascii=False))
        code, out = self.p.run(tx, "apply")
        self.assertIn("1 rejected", out)
        th = self.p.i18n("th.json").read_text()
        self.assertIn("// Items", th)                    # comments kept
        self.assertIn("// Dialogue", th)
        self.assertIn('"Quest.Objective"', th)
        self.assertIn("{Amount1}", th)                   # token restored
        self.assertNotIn('"' + bad["key"] + '": "ข้อความที่ทำ', th)
        doc = core.load_doc(self.p.i18n("th.json"))
        src_order = [k for k in core.load_doc(self.p.i18n("default.json")).keys() if k in doc.as_dict()]
        self.assertEqual([k for k in doc.keys() if k in src_order], src_order)   # source order kept
        self.assertTrue(list((self.p.root / "l10n/work").glob("*-retry.json")))


class MaskTest(unittest.TestCase):
    def test_mask_unmask_exact(self):
        for s in ["Hi @!#$b#Bye$h", "a^b", "%item object 388 5 %%[#]Title", "{{Speed}}x {0}", "Bring {Amount1} {Item1:LocalizedName}."]:
            m, t = core.mask(s, "smapi")
            back, probs = core.unmask(m, t)
            self.assertEqual(back, s)
            self.assertEqual(probs, [])

    def test_structure_order_enforced(self):
        m, t = core.mask("A#B^C", "smapi")
        swapped = m.replace("⟦1⟧", "X").replace("⟦2⟧", "⟦1⟧").replace("X", "⟦2⟧")
        _, probs = core.unmask(swapped, t)
        self.assertTrue(any("order" in p for p in probs))


if __name__ == "__main__":
    unittest.main()
