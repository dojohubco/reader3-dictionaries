#!/usr/bin/env python3
"""Small synthetic fixtures for parsing, ambiguity, provenance and indexed lookup."""

import hashlib
import io
import sqlite3
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
from dictionary import connect, lookup, normalize, render


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(build.SCHEMA)
        self.db.executemany("INSERT INTO sources VALUES(?,?,?,?,?)",
                            ((i, str(i), "fixture", "https://example.test", "fixture") for i in range(1, 5)))
        self.builder = build.Builder(self.db)
        for pos, rules in build.MORPHY_RULES.items():
            self.db.executemany("INSERT INTO morphy_rules VALUES(?,?,?,?)",
                                ((pos, a, b, i) for i, (a, b) in enumerate(rules)))

    def tearDown(self):
        self.db.close()

    def add(self, word, pos="noun", lang="en", source=1):
        entry = self.builder.entry(lang, word, pos, source)
        self.builder.senses(entry, [("Definition for " + word, None)], lang)
        return entry

    def test_normalization_and_possessive(self):
        self.assertEqual(normalize(' “HuCkster’s,” '), "huckster's")
        self.assertEqual(normalize("GIVE\u00a0 UP!"), "give up")
        self.assertEqual(normalize("cafe\u0301"), "café")
        self.assertEqual(normalize("ᲬᲘᲒᲜᲘ"), "წიგნი")
        self.assertEqual(normalize("re-sign"), "re-sign")
        self.assertEqual(normalize("჻"), "")
        self.add("huckster")
        route, _, rows = lookup(self.db, "huckster's", "en")
        self.assertEqual(route, "morphy")
        self.assertEqual(rows[0]["headword"], "huckster")

    def test_lookup_precedence_ambiguity_and_pos(self):
        axe = self.add("axe")
        axis = self.add("axis")
        self.add("acquiesce", "verb")
        self.add("acquiesce", "noun")
        self.db.executemany("INSERT INTO forms VALUES('axes','en',?,1)", ((axe,), (axis,)))
        route, _, rows = lookup(self.db, "axes", "en")
        self.assertEqual(route, "forms")
        self.assertEqual({r["headword"] for r in rows}, {"axe", "axis"})
        route, _, rows = lookup(self.db, "acquiesced", "en")
        self.assertEqual(route, "morphy")
        self.assertEqual({r["pos"] for r in rows}, {"verb"})
        exact = self.add("axes", "verb")
        self.assertEqual([r["id"] for r in lookup(self.db, "axes", "en")[2]], [exact])

    def test_phrase_and_georgian_alias(self):
        self.add("give up", "verb")
        self.assertEqual(lookup(self.db, '“give up”', "en")[0], "exact")
        self.assertEqual(lookup(self.db, "please give up now", "en")[0], "phrase")
        self.assertIn("Partial phrase match", render(self.db, "please give up now", "en"))
        book = self.add("წიგნი", lang="ka", source=4)
        self.db.execute("INSERT INTO forms VALUES('წიგნებს','ka',?,3)", (book,))
        self.assertIn("Lemma: წიგნი", render(self.db, "წიგნებს", "ka"))
        self.assertEqual(lookup(self.db, "unknown", "ka")[0], "none")
        self.assertEqual(lookup(self.db, "'" * 30, "en")[0], "none")

    def test_sense_limit_translation_and_foreign_keys(self):
        entry = self.add("book")
        self.builder.senses(entry, ((str(i), "Example") for i in range(10)), "en")
        self.builder.senses(entry, [("0", "duplicate")], "en")
        self.assertEqual(self.db.execute("SELECT count(*) FROM senses").fetchone()[0], 6)
        self.db.execute("INSERT INTO translations VALUES(?,'ka','წიგნი',NULL)", (entry,))
        self.assertIn("→ ka: წიგნი", render(self.db, "book", "en"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO forms VALUES('bad','en',999,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO translations VALUES(?,'ka','bad',999)", (entry,))

    def test_georgian_language_sections_nested_links_and_templates(self):
        text = """== ქართული ==
==== მნიშვნელობა ====
===== {{კატეგორია|ქართული|არსებითი სახელი}} =====
# {{კ|ძველი}} [[წიგნი|წიგნის]] [[ფურცელი|ფურცლები]].
##: სხვისი ციტატა არ უნდა გახდეს განმარტება.
{{მაგალითები|ძველი წიგნი}}
==== თარგმანები ====
{{თარგმანები|en={{თ+|en|book}}}}
== ინგლისური ==
=== არსებითი სახელი ===
# ეს უცხო სექციის განმარტებაა.
"""
        definitions, aliases, translations, _ = build.parse_georgian(text, "წიგნი")
        self.assertEqual(definitions["noun"], [("(ძველი) წიგნის ფურცლები.", "ძველი წიგნი")])
        self.assertEqual(translations, ["book"])
        self.assertEqual(aliases, [])
        definitions, aliases, _, _ = build.parse_georgian(
            "==[[ქართული]]==\n==={{ლემა|ნაბრუნები ფორმა|ქართული}}===\n#{{ნაბრუნები|წიგნი}}", "წიგნს")
        self.assertFalse(any(definitions.values()))
        self.assertEqual(aliases, ["წიგნი"])
        definitions, _, _, _ = build.parse_georgian(
            "==[[ქართული]]==\n==={{ლემა|ზმნიზედა|ქართული}}===\n'''მნიშვნელობა:'''\n"
            ":[1] გარდა ამისა\n'''სინონიმები:'''\n:[1] არ ჩართო ეს", "აგრეთვე")
        self.assertEqual(definitions["adv"], [("გარდა ამისა", None)])

    def test_wiktextract_forms_and_external_quotations(self):
        record = {"senses": [
            {"form_of": [{"word": "book"}], "glosses": ["plural of book"]},
            {"glosses": ["Books."], "examples": [
                {"text": "Copyrighted quote", "type": "quotation", "ref": "Author"},
                {"text": "My own example.", "type": "example"}]}]}
        self.assertEqual(build.lexical_senses(record), [("Books.", "My own example.")])

    def test_stardict_binary_and_html(self):
        syn = "წიგნებს".encode() + b"\0" + struct.pack(">I", 7)
        self.assertEqual(list(build.stardict_records(io.BytesIO(syn))), [("წიგნებს", (7,))])
        for truncated in (b"abc", b"abc\0\x00"):
            with self.assertRaises(ValueError):
                list(build.stardict_records(io.BytesIO(truncated)))
        parser = build.StarDictGlosses()
        parser.feed("<ol><li>A <a>felt</a> cloak.<dl><dd>Do not import this quotation.</dd></dl></li></ol>"
                    "<ul><li>Do not import usage notes.</li></ul>"
                    "<ol><li>A second definition.<ul><li>Nested note.</li></ul> Its ending.</li></ol>")
        self.assertEqual(parser.senses, [("A felt cloak.", None), ("A second definition. Its ending.", None)])

    def test_wordnet_offsets_sense_order_and_exceptions(self):
        fixture = io.BytesIO()
        with zipfile.ZipFile(fixture, "w") as archive:
            for filename, pos in (("noun", "n"), ("verb", "v"), ("adj", "a"), ("adv", "r")):
                prefix = "oewn2025-plus/"
                archive.writestr(prefix + "data." + filename,
                                 '  1 Source notice\n12345678 00 ' + pos + ' 01 axe 00 000 | a blade; "a sharp axe"\n\n')
                archive.writestr(prefix + "index." + filename, f"axe {pos} 1 0 1 0 12345678\n\n")
                archive.writestr(prefix + filename + ".exc", "axes axe\n")
        fixture.seek(0)
        base = build.import_wordnet(self.builder, fixture, {})
        self.assertEqual(len(base), 4)
        row = self.db.execute("SELECT gloss,example FROM senses LIMIT 1").fetchone()
        self.assertEqual(tuple(row), ("a blade", "a sharp axe"))
        self.assertEqual(self.db.execute("SELECT count(*) FROM _aliases").fetchone()[0], 4)

    def test_lookup_indexes(self):
        self.add("give up", "verb")
        self.db.execute("CREATE INDEX entries_phrase ON entries(lang,headword_norm) WHERE instr(headword_norm,' ')>0")
        plans = [
            ("SELECT id FROM entries WHERE lang='en' AND headword_norm='book'", "entries_lookup"),
            ("SELECT entry_id FROM forms WHERE lang='ka' AND form_norm='წიგნებს'", "PRIMARY KEY"),
            ("SELECT id FROM entries WHERE lang='en' AND instr(headword_norm,' ')>0 AND headword_norm='give up'", "entries_phrase")]
        for sql, index in plans:
            plan = " ".join(str(r[3]) for r in self.db.execute("EXPLAIN QUERY PLAN " + sql))
            self.assertIn(index, plan)

    def test_source_checksum_rejection_preserves_cached_file(self):
        build.WORK.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build.WORK) as directory:
            work = Path(directory)
            out = work / "out"
            out.mkdir()
            path = work / "source"
            path.write_bytes(b"abc")
            spec = {"filename": "source", "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
            with patch.object(build, "WORK", work), patch.object(build, "OUT", out):
                self.assertEqual(build.fetch(spec, {}), path)
                spec["sha256"] = "0" * 64
                with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                    build.fetch(spec, {})
                self.assertEqual(path.read_bytes(), b"abc")
                path.rename(work / "source.part")
                spec["sha256"] = hashlib.sha256(b"abc").hexdigest()
                self.assertEqual(build.fetch(spec, {}), path)

    def test_read_only_connection_never_creates_a_missing_database(self):
        build.WORK.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build.WORK) as directory:
            path = Path(directory) / "fixture.sqlite"
            with sqlite3.connect(path) as writer:
                writer.execute("CREATE TABLE fixture(value)")
            reader = connect(path)
            try:
                with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                    reader.execute("INSERT INTO fixture VALUES(1)")
            finally:
                reader.close()
            missing = Path(directory) / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                connect(missing)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
