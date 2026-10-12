#!/usr/bin/env python3
"""Offline self-check for pack filtering, alias remapping and distributions."""

import gzip
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from dictionary import DATABASE, connect, lookup
from split_packs import sha256, split


def check():
    fixture = ROOT.parents[1] / "core/dictionary/src/test/resources/dictionary.sqlite"
    fixture = Path(sys.argv[1]) if len(sys.argv) > 1 else fixture if fixture.is_file() else DATABASE
    before = sha256(fixture)
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        catalog = split(fixture, output)
        assert [p["id"] for p in catalog["packs"]] == ["en-en", "ka-ka", "en-ka", "ka-en"]
        for pack in catalog["packs"]:
            path = output / (pack["id"] + ".sqlite")
            archive = path.with_suffix(".sqlite.gz")
            assert sha256(archive) == pack["sha256"]
            assert path.stat().st_size == pack["installedBytes"]
            digest = hashlib.sha256()
            with gzip.open(archive, "rb") as incoming:
                for block in iter(lambda: incoming.read(64 * 1024), b""):
                    digest.update(block)
            assert digest.hexdigest() == sha256(path)
            with connect(path) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert db.execute("PRAGMA foreign_key_check").fetchone() is None
                assert db.execute("SELECT value FROM meta WHERE key='pack_id'").fetchone()[0] == pack["id"]
                # The shared fixture has a StarDict alias pointing to a different source's Georgian lemma.
                word = {"en-en": "acquiesced", "en-ka": "provincial", "ka-ka": "წიგნებს", "ka-en": "ვლაპარაკობ"}[pack["id"]]
                assert lookup(db, word, pack["langFrom"])[2], (pack["id"], word)
                assert db.execute("SELECT count(*) FROM entries WHERE lang!=?", (pack["langFrom"],)).fetchone()[0] == 0
        with connect(output / "en-en.sqlite") as db:
            assert db.execute("SELECT count(*) FROM translations").fetchone()[0] == 0
    assert before == sha256(fixture), "Source database was modified"
    print("Pack filtering, provenance, aliases, SHA-256, gzip and read-only source checks passed")


if __name__ == "__main__":
    check()
