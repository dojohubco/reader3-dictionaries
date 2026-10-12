#!/usr/bin/env python3
"""Split the already-built v1 database into self-contained, attributed packs."""

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

VERSION = "2026.10.12"
RELEASE = f"https://github.com/dojohubco/reader3-dictionaries/releases/download/v{VERSION}"
PACKS = (
    ("en-en", "English", "English definitions (WordNet + Wiktionary)", "en", "en"),
    ("ka-ka", "ქართული განმარტებითი", "ქართული სიტყვების განმარტებები (ვიკილექსიკონი)", "ka", "ka"),
    ("en-ka", "English → ქართული", "English words with Georgian translations", "en", "ka"),
    ("ka-en", "ქართული → English", "Georgian translations and form-to-lemma aliases", "ka", "en"),
)
TABLES = ("meta", "sources", "entries", "senses", "translations", "forms", "morphy_rules")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_pack(source, output, pack):
    pack_id, title, subtitle, lang_from, lang_to = pack
    temporary = output / f"{pack_id}.sqlite.part"
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(temporary, uri=True) as db:
        db.execute("PRAGMA cache_size=-8192")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA threads=1")
        db.execute("PRAGMA user_version=1")
        db.execute("PRAGMA application_id=1380209203")
        db.execute("ATTACH DATABASE ? AS src", (source.resolve().as_uri() + "?mode=ro",))
        for name in TABLES:
            db.execute(db.execute("SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0])
        db.execute("INSERT INTO meta SELECT * FROM src.meta")
        db.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", (
            ("pack_id", pack_id), ("pack_version", VERSION),
            ("coverage", json.dumps({"pack": pack_id})),
        ))
        # Translation packs retain referenced glosses to preserve sense-level foreign keys.
        has_gloss = "EXISTS(SELECT 1 FROM src.senses s WHERE s.entry_id=e.id AND s.gloss_lang=?)"
        has_translation = "EXISTS(SELECT 1 FROM src.translations t WHERE t.entry_id=e.id AND t.target_lang=?)"
        condition = has_gloss if lang_from == lang_to else f"({has_translation}" + (f" OR {has_gloss})" if pack_id == "ka-en" else ")")
        args = [lang_from, lang_to] + ([lang_to] if pack_id == "ka-en" else [])
        db.execute(f"INSERT INTO entries SELECT e.* FROM src.entries e WHERE e.lang=? AND {condition}", args)
        for row in db.execute("SELECT sql FROM src.sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name").fetchall():
            db.execute(row[0])
        if lang_from != lang_to:
            db.execute("INSERT INTO translations SELECT t.* FROM src.translations t JOIN entries e ON e.id=t.entry_id WHERE t.target_lang=?", (lang_to,))
        db.execute("INSERT INTO senses SELECT s.* FROM src.senses s JOIN entries e ON e.id=s.entry_id "
                   "WHERE s.gloss_lang=? OR EXISTS(SELECT 1 FROM translations t WHERE t.entry_id=s.entry_id AND t.sense_idx=s.idx)", (lang_to,))
        db.execute("INSERT INTO forms SELECT f.* FROM src.forms f JOIN entries e ON e.id=f.entry_id")
        if pack_id != "en-en":
            # Source aliases often point at a different source's entry for the same lemma/POS.
            db.execute("INSERT OR IGNORE INTO forms SELECT f.form_norm,f.lang,e.id,f.source_id "
                       "FROM src.forms f JOIN src.entries original ON original.id=f.entry_id "
                       "JOIN entries e ON e.lang=original.lang AND e.headword_norm=original.headword_norm AND e.pos=original.pos "
                       "ORDER BY f.source_id")
        if lang_from == "en":
            db.execute("INSERT INTO morphy_rules SELECT * FROM src.morphy_rules")
        db.execute("INSERT INTO sources SELECT s.* FROM src.sources s WHERE s.id IN ("
                   "SELECT source_id FROM entries UNION SELECT ipa_source_id FROM entries UNION SELECT source_id FROM forms)")
        counts = {name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in TABLES[2:]}
        db.execute("UPDATE meta SET value=? WHERE key='coverage'", (json.dumps(counts, sort_keys=True),))
        source_rows = [dict(zip(("id", "name", "license", "url", "attribution"), row))
                       for row in db.execute("SELECT * FROM sources ORDER BY id")]
        db.commit()
        db.execute("VACUUM")
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", pack_id
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None, pack_id
        assert counts["entries"] > 0, pack_id
    path = output / f"{pack_id}.sqlite"
    temporary.replace(path)
    compressed = output / f"{pack_id}.sqlite.gz"
    compressed_temporary = output / f"{pack_id}.sqlite.gz.part"
    with path.open("rb") as incoming, compressed_temporary.open("wb") as outgoing:
        with gzip.GzipFile(filename="", mode="wb", fileobj=outgoing, compresslevel=9, mtime=0) as zipped:
            shutil.copyfileobj(incoming, zipped, 64 * 1024)
    compressed_temporary.replace(compressed)
    result = dict(id=pack_id, title=title, subtitle=subtitle, langFrom=lang_from, langTo=lang_to,
                  url=f"{RELEASE}/{compressed.name}", sha256=sha256(compressed), bytes=compressed.stat().st_size,
                  installedBytes=path.stat().st_size,
                  license="CC BY 4.0 / CC BY-SA 4.0" if any(s["id"] == 1 for s in source_rows) else "CC BY-SA 4.0",
                  sources=source_rows)
    print(f"{pack_id}: {result['bytes']:,} download / {result['installedBytes']:,} installed bytes; {counts}", flush=True)
    return result


def split(source, output):
    output.mkdir(parents=True, exist_ok=True)
    catalog = dict(schema=1, version=VERSION, packs=[split_pack(source, output, pack) for pack in PACKS])
    (output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.glob("*.sqlite*")) if not path.name.endswith(".part")), encoding="utf-8")
    return catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path.home() / "Documents/Projects/reader3-artifacts/reader3-dict-v1.sqlite")
    parser.add_argument("--out", type=Path, default=Path.home() / "Documents/Projects/reader3-artifacts/packs")
    args = parser.parse_args()
    split(args.db, args.out)
