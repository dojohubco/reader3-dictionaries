#!/usr/bin/env python3
"""Build the pinned, offline reader3 dictionary. Python standard library + zstd CLI."""

import bz2
import collections
import datetime
import gzip
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictionary import DATABASE, MAX_SENSES, MORPHY_RULES, morphy_candidates, normalize, short

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "out"
LOCK = ROOT / "sources.lock.json"
BUDGET = 8_000_000_000
SCHEMA = """
PRAGMA foreign_keys=ON;
PRAGMA user_version=1;
PRAGMA application_id=1380209203;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT NOT NULL, license TEXT NOT NULL,
                     url TEXT NOT NULL, attribution TEXT NOT NULL);
CREATE TABLE entries(id INTEGER PRIMARY KEY, lang TEXT NOT NULL CHECK(lang IN ('en','ka')),
    headword TEXT NOT NULL, headword_norm TEXT NOT NULL, pos TEXT NOT NULL, ipa TEXT,
    source_id INTEGER NOT NULL REFERENCES sources(id), ipa_source_id INTEGER REFERENCES sources(id),
    UNIQUE(lang,headword,pos,source_id));
CREATE INDEX entries_lookup ON entries(lang,headword_norm);
CREATE TABLE senses(entry_id INTEGER NOT NULL REFERENCES entries(id), idx INTEGER NOT NULL,
    gloss TEXT NOT NULL, gloss_lang TEXT NOT NULL CHECK(gloss_lang IN ('en','ka')), example TEXT,
    PRIMARY KEY(entry_id,idx)) WITHOUT ROWID;
CREATE TABLE translations(entry_id INTEGER NOT NULL REFERENCES entries(id), target_lang TEXT NOT NULL,
    text TEXT NOT NULL, sense_idx INTEGER,
    PRIMARY KEY(entry_id,target_lang,text),
    FOREIGN KEY(entry_id,sense_idx) REFERENCES senses(entry_id,idx)) WITHOUT ROWID;
CREATE TABLE forms(form_norm TEXT NOT NULL, lang TEXT NOT NULL,
    entry_id INTEGER NOT NULL REFERENCES entries(id), source_id INTEGER NOT NULL REFERENCES sources(id),
    PRIMARY KEY(lang,form_norm,entry_id)) WITHOUT ROWID;
CREATE TABLE morphy_rules(pos TEXT NOT NULL, suffix TEXT NOT NULL, replacement TEXT NOT NULL,
    priority INTEGER NOT NULL, PRIMARY KEY(pos,priority)) WITHOUT ROWID;
CREATE TABLE _aliases(form_norm TEXT NOT NULL, lang TEXT NOT NULL, lemma_norm TEXT NOT NULL,
    pos TEXT NOT NULL, source_id INTEGER NOT NULL,
    PRIMARY KEY(lang,form_norm,lemma_norm,pos,source_id)) WITHOUT ROWID;
CREATE TABLE _surfaces(form_norm TEXT PRIMARY KEY) WITHOUT ROWID;
"""
EN_POS = {"noun", "verb", "adj", "adv", "phrase", "prep_phrase", "adv_phrase", "proverb", "conj",
          "pron", "det", "prep", "postp", "article", "particle", "intj", "num", "contraction"}
KA_POS = {"არსებითი სახელი": "noun", "ზედსართავი სახელი": "adj", "ზმნა": "verb",
          "ზმნიზედა": "adv", "ნაცვალსახელი": "pron", "რიცხვითი სახელი": "num",
          "კავშირი": "conj", "თანდებული": "postp", "შორისდებული": "intj",
          "ნაწილაკი": "particle", "ნაბრუნები ფორმა": "form", "ზმნის ფორმა": "form",
          "ტოპონიმი": "name", "საკუთარი სახელი": "name", "ანდაზა": "proverb",
          "იდიომი": "phrase", "თანდებულიანი ფორმა": "form"}
TEST_WORDS = {"en": ("provincial", "acquiesced", "frippery", "huckster's", "axes", "give up", "out of habit"),
              "ka": ("წიგნებს", "ვლაპარაკობ", "ზეგარდმო", "დათრგუნვად", "მონაბერითა", "ნაბადი")}


def log(message):
    print(message, flush=True)


def sha256(path):
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def storage_check(stats):
    used = sum(p.stat().st_size for folder in (WORK, OUT) for p in folder.rglob("*") if p.is_file())
    stats["peak_work_out_bytes_observed"] = max(used, stats.get("peak_work_out_bytes_observed", 0))
    if used > BUDGET:
        raise RuntimeError("Dictionary workspace exceeded the 8 GB disk budget.")


def fetch(spec, stats):
    destination = WORK / spec["filename"]
    if not spec["sha256"]:
        raise RuntimeError(f"Missing source checksum for {spec['filename']}.")
    if not destination.exists():
        part = destination.with_suffix(destination.suffix + ".part")
        if part.exists() and part.stat().st_size == spec["bytes"]:
            if sha256(part) != spec["sha256"]:
                raise RuntimeError(f"Checksum mismatch: {part}.")
            part.replace(destination)
            return fetch(spec, stats)
        urls = [spec["url"], *spec.get("mirrors", [])]
        for attempt in range(4):
            offset = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": "reader3-dictionaries/1.0 (open dictionary build)"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(urls[attempt % len(urls)], headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206:
                        offset = 0
                    elif not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("Invalid HTTP range response.")
                    with part.open("ab" if offset else "wb") as stream:
                        last_log = time.monotonic()
                        for block in iter(lambda: response.read(1024 * 1024), b""):
                            stream.write(block)
                            offset += len(block)
                            if offset > spec["bytes"]:
                                raise RuntimeError(f"Source changed: {spec['filename']} is larger than its lock.")
                            storage_check(stats)
                            if time.monotonic() - last_log > 30:
                                log(f"Downloading {spec['filename']}: {offset / 1e9:.2f} GB")
                                last_log = time.monotonic()
                if offset != spec["bytes"]:
                    raise OSError(f"Incomplete download: {offset} / {spec['bytes']} bytes")
                part.replace(destination)
                break
            except (OSError, urllib.error.URLError) as error:
                if attempt == 3:
                    raise RuntimeError(f"Cannot download {spec['filename']}: {error}") from error
                log(f"Retrying {spec['filename']}: {error}")
        log(f"Downloaded {spec['filename']}")
    if destination.stat().st_size != spec["bytes"] or sha256(destination) != spec["sha256"]:
        raise RuntimeError(f"Checksum mismatch: {destination}. Upstream may have rotated; do not silently update the lock.")
    storage_check(stats)
    return destination


class Builder:
    def __init__(self, db):
        self.db = db

    def entry(self, lang, headword, pos, source, ipa=None):
        headword = " ".join(headword.split())
        norm = normalize(headword)
        if not norm:
            raise ValueError(f"Empty normalized headword: {headword!r}")
        self.db.execute("INSERT OR IGNORE INTO entries(lang,headword,headword_norm,pos,ipa,source_id) "
                        "VALUES(?,?,?,?,?,?)", (lang, headword, norm, pos, ipa, source))
        row = self.db.execute("SELECT id FROM entries WHERE lang=? AND headword=? AND pos=? AND source_id=?",
                              (lang, headword, pos, source)).fetchone()
        if ipa:
            self.db.execute("UPDATE entries SET ipa=coalesce(ipa,?) WHERE id=?", (short(ipa, 100), row[0]))
        return row[0]

    def senses(self, entry, senses, lang):
        old = self.db.execute("SELECT gloss FROM senses WHERE entry_id=? ORDER BY idx", (entry,)).fetchall()
        seen = {r[0] for r in old}
        count = len(old)
        for gloss, example in senses:
            gloss = short(gloss)
            if not gloss or gloss in seen or count >= MAX_SENSES:
                continue
            count += 1
            seen.add(gloss)
            self.db.execute("INSERT INTO senses VALUES(?,?,?,?,?)",
                            (entry, count, gloss, lang, short(example, 220) if example else None))

    def alias(self, form, lang, lemma, pos, source):
        form, lemma = normalize(form), normalize(lemma)
        if form and lemma and form != lemma:
            self.db.execute("INSERT OR IGNORE INTO _aliases VALUES(?,?,?,?,?)", (form, lang, lemma, pos, source))


def import_wordnet(builder, path, stats):
    db = builder.db
    base = collections.defaultdict(list)
    with zipfile.ZipFile(path) as archive:
        prefix = "oewn2025-plus/"
        notice = []
        for line in archive.read(prefix + "data.noun").decode().splitlines():
            if not line.startswith(" "):
                break
            notice.append(re.sub(r"^\s*\d+\s?", "", line))
        db.execute("UPDATE sources SET attribution=attribution || ? WHERE id=1", ("\n\n" + "\n".join(notice),))
        for filename, pos in (("noun", "noun"), ("verb", "verb"), ("adj", "adj"), ("adv", "adv")):
            synsets = {}
            with archive.open(prefix + "data." + filename) as stream:
                for raw in stream:
                    if raw.startswith(b" ") or not raw.strip():
                        continue
                    data, gloss = raw.decode().rstrip().split(" | ", 1)
                    tokens = data.split()
                    example = next(iter(re.findall(r'"([^"\n]+)"', gloss)), None)
                    definition = re.sub(r';?\s*"[^"\n]*"', "", gloss).strip(" ;")
                    synsets[tokens[0]] = (definition, example)
            with archive.open(prefix + "index." + filename) as stream:
                for raw in stream:
                    if raw.startswith(b" ") or not raw.strip():
                        continue
                    fields = raw.decode().split()
                    headword = fields[0].replace("_", " ")
                    offsets = fields[6 + int(fields[3]):]
                    if len(offsets) != int(fields[2]):
                        raise ValueError("Unexpected WordNet index format.")
                    entry = builder.entry("en", headword, pos, 1)
                    builder.senses(entry, (synsets[o] for o in offsets), "en")
                    base[(normalize(headword), pos)].append(entry)
            with archive.open(prefix + filename + ".exc") as stream:
                for raw in stream:
                    fields = raw.decode().split()
                    if not fields:
                        continue
                    for lemma in fields[1:]:
                        builder.alias(fields[0].replace("_", " "), "en", lemma.replace("_", " "), pos, 1)
            db.commit()
            log(f"Imported WordNet {pos}")
    stats["wordnet_entries"] = db.execute("SELECT count(*) FROM entries WHERE source_id=1").fetchone()[0]
    return base


def lexical_senses(record):
    result = []
    for sense in record.get("senses", []):
        if sense.get("form_of") or sense.get("alt_of") or "no-gloss" in sense.get("tags", []):
            continue
        glosses = sense.get("glosses", [])
        if not glosses:
            continue
        example = next((x["text"] for x in sense.get("examples", [])
                        if x.get("type") == "example" and not x.get("ref") and x.get("text")), None)
        result.append((glosses[-1], example))
    return result


def import_wiktextract(builder, path, base, stats):
    db = builder.db
    # A prefilter only: the JSON root language is checked again after decoding.
    language = re.compile(br'"lang_code"\s*:\s*"(?:en|ka)"')
    started = time.monotonic()
    processed = 0
    translated_headwords = set()
    with gzip.open(path, "rb") as stream:
        for number, raw in enumerate(stream, 1):
            if not language.search(raw):
                continue
            record = json.loads(raw)
            lang = record.get("lang_code")
            if lang not in ("en", "ka"):
                continue
            word, pos = record.get("word", ""), record.get("pos", "unknown")
            norm = normalize(word)
            if not norm:
                continue
            processed += 1
            stats[f"raw_{lang}_records"] = stats.get(f"raw_{lang}_records", 0) + 1
            if lang == "en":
                db.execute("INSERT OR IGNORE INTO _surfaces VALUES(?)", (norm,))
            for sense in record.get("senses", []):
                for relation in ("form_of", "alt_of"):
                    for lemma in sense.get(relation, []):
                        if lemma.get("word"):
                            builder.alias(word, lang, lemma["word"], pos, 2)
            senses = lexical_senses(record)
            translations = [t for t in record.get("translations", [])
                            if t.get("code", t.get("lang_code")) == ("ka" if lang == "en" else "en")
                            and t.get("word") and "dubious" not in t.get("tags", [])]
            if lang == "en" and translations:
                translated_headwords.add(norm)
                if pos not in EN_POS:
                    senses = []
            accepted = lang == "ka" or ((pos in EN_POS or translations) and len(norm) <= 120)
            ipa = next((s["ipa"] for s in record.get("sounds", []) if s.get("ipa")), None)
            existing = base.get((norm, pos), []) if lang == "en" else []
            complement = accepted and (not existing or translations or " " in norm or pos not in MORPHY_RULES)
            targets = existing
            if complement and (senses or translations):
                entry = builder.entry(lang, word, pos, 2, ipa)
                builder.senses(entry, senses, "en")
                targets = [entry]
                for translation in translations:
                    term = short(translation["word"], 120)
                    sense_idx = db.execute("SELECT idx FROM senses WHERE entry_id=? AND gloss=?",
                                           (entry, short(translation.get("sense", "")))).fetchone()
                    db.execute("INSERT OR IGNORE INTO translations VALUES(?,?,?,?)",
                               (entry, "ka" if lang == "en" else "en", term, sense_idx[0] if sense_idx else None))
            if ipa and existing:
                db.executemany("UPDATE entries SET ipa=?,ipa_source_id=2 WHERE id=? AND ipa IS NULL",
                               ((short(ipa, 100), entry) for entry in existing))
            if targets:
                for form in record.get("forms", []):
                    value = form.get("form", "")
                    if not value or "romanization" in form.get("tags", []) or value in ("-", "—"):
                        continue
                    form_norm = normalize(value)
                    if form_norm and form_norm != norm:
                        db.executemany("INSERT OR IGNORE INTO forms VALUES(?,?,?,2)",
                                       ((form_norm, lang, entry) for entry in targets))
            if processed % 25000 == 0:
                db.commit()
                storage_check(stats)
                log(f"Kaikki: {number:,} JSONL lines, {processed:,} EN/KA records, {time.monotonic() - started:.0f}s")
    db.commit()
    stats["raw_jsonl_lines"] = number
    stats["raw_en_ka_translated_headwords"] = len(translated_headwords)
    if not stats.get("raw_en_records") or not stats.get("raw_ka_records"):
        raise RuntimeError("Kaikki extraction has no English or Georgian records.")


def clean_wikitext(text, title=""):
    text = re.sub(r"<!--[\s\S]*?-->|<ref\b[^>]*>[\s\S]*?</ref>|<ref\b[^>]*/>", "", text)
    text = re.sub(r"\[\[(?:ფაილი|სურათი|კატეგორია|File|Image|Category):[^\]]*\]\]", "", text, flags=re.I)

    # shortcut: common inline templates only, expand the whitelist when coverage suffers.
    def template(match):
        parts = [p.strip() for p in match[1].split("|")]
        name, args = parts[0], parts[1:]
        if name == "PAGENAME":
            return title
        if name in ("კ", "lb", "label", "context"):
            return "(" + ", ".join(a for a in args if a and a not in ("ka", "ქართული")) + ") "
        if name in ("l", "m", "თ", "თ+", "t", "t+") and len(args) >= 2:
            return args[1]
        if name in ("ბმული", "გადამისამართება", "ნაბრუნები", "მრავლობითი", "მოქმედებითი", "მიცემითი"):
            return next((a for a in args if a and "=" not in a and a != "ქართული"), "")
        return ""

    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"\{\{([^{}]*)\}\}", template, text)
    text = re.sub(r"\[\[([^\[\]]+)\]\]", lambda m: m[1].split("|")[-1].split("#")[0], text)
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"<[^>]+>|'{2,5}", "", text)
    return " ".join(html.unescape(text).split())


def georgian_sections(text):
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    matches = list(re.finditer(r"^==([^=\n]+)==\s*$", text, re.M))
    sections = []
    for i, match in enumerate(matches):
        heading = clean_wikitext(match[1]).strip()
        if heading == "ქართული":
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append(text[match.end():end])
    return sections


def parse_georgian(text, title):
    """Parse attested # definitions, POS markers and English translation templates."""
    definitions = collections.defaultdict(list)
    aliases, translations = [], []
    unknown = collections.Counter()
    for section in georgian_sections(text):
        pos = "unknown"
        meaning = True
        for line in section.splitlines():
            bold_heading = re.match(r"^'''([^']+):'''\s*$", line.strip())
            if bold_heading:
                meaning = bold_heading[1] == "მნიშვნელობა"
            heading = re.match(r"^(={3,})\s*(.*?)\s*\1\s*$", line)
            if heading:
                label = clean_wikitext(heading[2], title)
                if len(heading[1]) <= 4:
                    meaning = label == "მნიშვნელობა" or len(heading[1]) == 3
                marker = re.search(r"\{\{(?:კატეგორია\|ქართული\||ლემა\|)([^}|]+)", heading[2])
                if marker:
                    pos = KA_POS.get(marker[1].strip(), "unknown")
                    if any(x in heading[2] for x in ("ტოპონიმი", "ქართული გვარი", "საკუთარი სახელი")):
                        pos = "name"
                elif label in KA_POS:
                    pos = KA_POS[label]
            for match in re.finditer(r"\{\{(?:თ\+?|t\+?)\s*\|\s*en\s*\|([^{}|]+)", line):
                term = clean_wikitext(match[1], title)
                if term:
                    translations.append(term)
            for form in re.finditer(r"\{\{(?:თანდებულიანი|ნაბრუნები|მრავლობითი|მოქმედებითი|მიცემითი)\s*\|([^}|]+)", line):
                aliases.append(form[1].strip())
            definition = re.match(r"^(?:#+(?![#:*])|:\s*\[\d+\])\s*(.+)", line.strip())
            if meaning and definition:
                value = definition[1]
                form = re.search(r"\{\{(?:ნაბრუნები|მრავლობითი|მოქმედებითი|მიცემითი)\s*\|([^}|]+)", value)
                if form:
                    aliases.append(form[1].strip())
                    continue
                if pos == "form":
                    lemma = re.search(r"'''\s*\[\[([^\]]+)\]\]\s*'''", value)
                    if lemma:
                        aliases.append(lemma[1].split("|")[0].split("#")[0])
                    continue
                for name in re.findall(r"\{\{([^{}|]+)", value):
                    if name.strip() not in ("კ", "l", "m", "PAGENAME", "ბმული"):
                        unknown[name.strip()] += 1
                gloss = clean_wikitext(value, title)
                if gloss and re.search(r"[ა-ჿ]", gloss):
                    definitions[pos].append((gloss, None))
            if meaning and line.lstrip().startswith("{{მაგალითები|"):
                value = re.search(r"\{\{მაგალითები\|([^{}|]+)", line)
                if value and definitions[pos] and value[1].strip():
                    gloss, _ = definitions[pos][-1]
                    definitions[pos][-1] = (gloss, clean_wikitext(value[1], title))
    return definitions, list(dict.fromkeys(aliases)), list(dict.fromkeys(translations)), unknown


def import_georgian(builder, path, stats):
    db = builder.db
    unknown = collections.Counter()
    pages, ka_pages, defined = 0, 0, 0
    with bz2.open(path, "rb") as stream:
        context = ET.iterparse(stream, events=("start", "end"))
        _, root = next(context)
        for event, element in context:
            if event != "end" or not element.tag.endswith("}page"):
                continue
            if element.findtext("{*}ns") == "0":
                pages += 1
                title = element.findtext("{*}title")
                text = element.findtext("{*}revision/{*}text") or ""
                redirect = element.find("{*}redirect")
                if redirect is not None and re.search(r"[ა-ჿ]", title):
                    builder.alias(title, "ka", redirect.get("title", ""), "", 4)
                if georgian_sections(text):
                    ka_pages += 1
                    definitions, aliases, translations, unsupported = parse_georgian(text, title)
                    unknown.update(unsupported)
                    if any(definitions.values()):
                        defined += 1
                    for pos, senses in definitions.items():
                        if not senses:
                            continue
                        ipa = next(iter(re.findall(r"\{\{IPA\|([^{}|]+)\}\}", "\n".join(georgian_sections(text)))), None)
                        entry = builder.entry("ka", title, pos, 4, ipa)
                        builder.senses(entry, senses, "ka")
                        db.executemany("INSERT OR IGNORE INTO translations VALUES(?,'en',?,NULL)",
                                       ((entry, short(t, 120)) for t in translations))
                    for lemma in aliases:
                        builder.alias(title, "ka", lemma, "", 4)
            root.clear()
    db.commit()
    stats.update(ka_wiki_main_pages=pages, ka_wiki_georgian_pages=ka_pages,
                 ka_wiki_pages_with_definitions=defined, ka_wiki_unsupported_definition_templates=dict(unknown))
    if defined < 1000:
        raise RuntimeError("Unexpectedly few parsed Georgian Wiktionary definitions.")
    log(f"Georgian Wiktionary: {defined:,} pages with definitions / {ka_pages:,} Georgian sections")


class StarDictGlosses(HTMLParser):
    """Fallback only for StarDict lemmas absent from the newer raw Kaikki extract."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.senses = []
        self.definition = False

    def handle_starttag(self, tag, attrs):
        if tag == "li" and self.stack and self.stack[-1] == "ol" and self.stack.count("ol") == 1:
            self.parts = []
            self.definition = True
        if tag not in ("br", "img", "hr", "meta", "link", "input", "wbr"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "li" and self.stack.count("ol") == 1 and self.stack.count("li") == 1 and self.definition and self.parts:
            self.senses.append(("".join(self.parts), None))
            self.definition = False
        if tag in self.stack:
            del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]

    def handle_data(self, data):
        if self.definition and not any(tag in self.stack for tag in ("dl", "ul", "table")):
            self.parts.append(data)


def stardict_records(stream, index=False):
    """Incrementally decode NUL-terminated UTF-8 keys and network-order integers."""
    while True:
        word = bytearray()
        while True:
            byte = stream.read(1)
            if not byte:
                if word:
                    raise ValueError("Truncated StarDict key.")
                return
            if byte == b"\0":
                break
            word.extend(byte)
            if len(word) > 4096:
                raise ValueError("Oversized StarDict key.")
        size = 8 if index else 4
        values = stream.read(size)
        if len(values) != size:
            raise ValueError("Truncated StarDict offset.")
        yield word.decode("utf-8"), struct.unpack(">II" if index else ">I", values)


def import_stardict(builder, path, stats):
    db = builder.db
    needed = {"ka-en.ifo", "ka-en.idx", "ka-en.syn", "ka-en.dict.dz"}
    members = {}
    process = subprocess.Popen(["zstd", "-dc", str(path)], stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                name = Path(member.name).name
                if name in needed and member.isfile():
                    if member.size > 100_000_000 or name in members:
                        raise ValueError("Unexpected StarDict archive member.")
                    destination = WORK / name
                    with archive.extractfile(member) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
                    members[name] = destination
    finally:
        process.stdout.close()
        code = process.wait()
    if code or needed != members.keys():
        raise RuntimeError("Incomplete StarDict archive.")
    info = dict(line.split("=", 1) for line in members["ka-en.ifo"].read_text().splitlines() if "=" in line)
    if "Wiktionary license CC BY-SA 4.0" not in info.get("description", "") or info.get("idxoffsetbits") != "32":
        raise ValueError("Unsupported StarDict format or unverified dictionary license.")
    with members["ka-en.idx"].open("rb") as stream:
        index = list(stardict_records(stream, index=True))
    if len(index) != int(info["wordcount"]):
        raise ValueError("StarDict index count mismatch.")
    lexicon = collections.defaultdict(list)
    for norm, entry in db.execute("SELECT headword_norm,id FROM entries WHERE lang='ka'"):
        lexicon[norm].append(entry)
    english_glosses = {r[0] for r in db.execute("SELECT DISTINCT e.headword_norm FROM entries e "
                                               "JOIN senses s ON s.entry_id=e.id WHERE e.lang='ka' AND s.gloss_lang='en'")}
    fallbacks = 0
    punctuation_heads = 0
    with gzip.open(members["ka-en.dict.dz"], "rb") as stream:
        for word, (offset, length) in index:
            norm = normalize(word)
            if not norm:
                punctuation_heads += 1
                continue
            if norm not in english_glosses:
                stream.seek(offset)
                parser = StarDictGlosses()
                parser.feed(stream.read(length).decode())
                if not parser.senses:
                    raise ValueError(f"Missing definition for StarDict lemma: {word}")
                entry = builder.entry("ka", word, "unknown", 3)
                builder.senses(entry, parser.senses, "en")
                lexicon[norm].append(entry)
                english_glosses.add(norm)
                fallbacks += 1
    count = 0
    empty_aliases = 0
    with members["ka-en.syn"].open("rb") as stream:
        for word, (target,) in stardict_records(stream):
            if target >= len(index):
                raise ValueError("StarDict alias points outside the index.")
            form = normalize(word)
            count += 1
            if not form:
                empty_aliases += 1
                continue
            ids = lexicon[normalize(index[target][0])]
            if not ids:
                raise ValueError("StarDict alias has no lookupable target.")
            db.executemany("INSERT OR IGNORE INTO forms VALUES(?,'ka',?,3)", ((form, entry) for entry in ids))
    if count != int(info["synwordcount"]) or count != 560363:
        raise ValueError("Pinned StarDict alias count mismatch.")
    db.commit()
    stats.update(stardict_alias_records=count, stardict_headwords=len(index),
                 stardict_punctuation_heads_skipped=punctuation_heads,
                 stardict_empty_alias_records_skipped=empty_aliases,
                 stardict_usable_alias_records=count - empty_aliases, stardict_fallback_entries=fallbacks)
    log(f"StarDict: read {count:,} aliases, retained {count - empty_aliases:,} nonempty records; {fallbacks:,} fallback definitions")
    for member in members.values():
        member.unlink()


def finish_forms(builder, stats):
    db = builder.db
    db.execute("INSERT OR IGNORE INTO forms SELECT a.form_norm,a.lang,e.id,a.source_id "
               "FROM _aliases a JOIN entries e ON e.lang=a.lang AND e.headword_norm=a.lemma_norm "
               "AND (a.pos='' OR a.pos=e.pos) ORDER BY a.source_id,a.lang,a.form_norm,e.id")
    stats["unresolved_source_aliases"] = db.execute(
        "SELECT count(*) FROM _aliases a WHERE NOT EXISTS(SELECT 1 FROM entries e "
        "WHERE e.lang=a.lang AND e.headword_norm=a.lemma_norm AND (a.pos='' OR a.pos=e.pos))").fetchone()[0]
    lexicon = collections.defaultdict(list)
    for norm, pos, entry in db.execute("SELECT headword_norm,pos,id FROM entries WHERE lang='en'"):
        lexicon[(norm, pos)].append(entry)
    generated = 0
    for (form,) in db.execute("SELECT form_norm FROM _surfaces ORDER BY form_norm"):
        for lemma, pos in morphy_candidates(form):
            for entry in lexicon.get((lemma, pos), []):
                generated += db.execute("INSERT OR IGNORE INTO forms VALUES(?,'en',?,1)", (form, entry)).rowcount
    stats["morphy_observed_form_rows_added"] = generated
    for pos, rules in MORPHY_RULES.items():
        db.executemany("INSERT INTO morphy_rules VALUES(?,?,?,?)",
                       ((pos, suffix, replacement, i) for i, (suffix, replacement) in enumerate(rules)))
    db.executescript("DROP TABLE _aliases; DROP TABLE _surfaces; "
                     "CREATE INDEX entries_phrase ON entries(lang,headword_norm) WHERE instr(headword_norm,' ')>0;")
    db.commit()
    log(f"Forms: materialized {generated:,} additional Morphy matches")


def coverage(db):
    result = {}
    for source, gloss in (("en", "en"), ("ka", "en"), ("ka", "ka")):
        row = db.execute("SELECT count(DISTINCT e.id),count(DISTINCT e.headword_norm) FROM entries e "
                         "JOIN senses s ON e.id=s.entry_id WHERE e.lang=? AND s.gloss_lang=?",
                         (source, gloss)).fetchone()
        result[f"{source}_{gloss}_entries"] = row[0]
        result[f"{source}_{gloss}_headwords"] = row[1]
    row = db.execute("SELECT count(DISTINCT e.id),count(DISTINCT e.headword_norm),count(*) "
                     "FROM entries e JOIN translations t ON e.id=t.entry_id "
                     "WHERE e.lang='en' AND t.target_lang='ka'").fetchone()
    result.update(en_ka_entries=row[0], en_ka_headwords=row[1], en_ka_translation_rows=row[2])
    for table in ("entries", "senses", "translations", "forms"):
        result[table + "_rows"] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    for lang in ("en", "ka"):
        row = db.execute("SELECT count(*),count(DISTINCT form_norm) FROM forms WHERE lang=?", (lang,)).fetchone()
        result[lang + "_form_rows"], result[lang + "_distinct_forms"] = row
    return result


def main():
    if not shutil.which("zstd"):
        raise SystemExit("The zstd CLI is required for the upstream .tar.zst archive (no Python packages needed).")
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    os.environ["SQLITE_TMPDIR"] = str(WORK)
    sources = json.loads(LOCK.read_text())
    stats = {}
    storage_check(stats)
    paths = {key: fetch(spec, stats) for key, spec in sources.items()}
    temporary = OUT / "reader3-dict-v1.build.sqlite"
    temporary.unlink(missing_ok=True)
    compressed = OUT / "reader3-dict-v1.build.sqlite.gz"
    compressed.unlink(missing_ok=True)
    db = sqlite3.connect(temporary)
    try:
        db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE; PRAGMA cache_size=-65536;" + SCHEMA)
        db.executemany("INSERT INTO sources VALUES(?,?,?,?,?)", (
            (1, "Open English WordNet 2025 Plus + Morphy exceptions", "CC BY 4.0", "https://en-word.net/",
             "Open English WordNet team; John P. McCrae et al. (2019), English WordNet 2019. Derived from Princeton WordNet. "
             "License: https://creativecommons.org/licenses/by/4.0/ . Modified: popup filtering and truncation; morphological mappings."),
            (2, "English Wiktionary via Kaikki / Wiktextract", "CC BY-SA 4.0", "https://en.wiktionary.org/",
             "English Wiktionary contributors; Kaikki.org / Tatu Ylonen, Wiktextract (2022). "
             "For each entry link https://en.wiktionary.org/wiki/<URL-encoded headword> (page history credits authors). "
             "License: https://creativecommons.org/licenses/by-sa/4.0/ . Modified: filtering, short glosses, one IPA/example, aliases."),
            (3, "Wiktionary Georgian-English StarDict aliases", "CC BY-SA 4.0", "https://xxyzz.github.io/wiktionary_stardict/",
             "English Wiktionary contributors; StarDict extraction by xxyzz, 20260928 (snapshot 2026-09-01). "
             "For each lemma link https://en.wiktionary.org/wiki/<URL-encoded headword>. "
             "Dictionary data license confirmed in ka-en.ifo; GPL extraction code is not incorporated. "
             "License: https://creativecommons.org/licenses/by-sa/4.0/ . Modified: normalized aliases and fallback glosses."),
            (4, "Georgian Wiktionary", "CC BY-SA 4.0", "https://ka.wiktionary.org/",
             "Georgian Wiktionary contributors, 2026-10-01 dump. For each entry link "
             "https://ka.wiktionary.org/wiki/<URL-encoded headword> (page history credits authors). "
             "License: https://creativecommons.org/licenses/by-sa/4.0/ . Modified: Georgian-section wikitext parsing, short glosses and translations."),
        ))
        builder = Builder(db)
        base = import_wordnet(builder, paths["wordnet"], stats)
        storage_check(stats)
        import_wiktextract(builder, paths["wiktextract"], base, stats)
        del base
        storage_check(stats)
        import_georgian(builder, paths["kawiktionary"], stats)
        import_stardict(builder, paths["stardict"], stats)
        finish_forms(builder, stats)
        stats.update(coverage(db))
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        date = (datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc) if epoch
                else datetime.datetime.now(datetime.timezone.utc)).isoformat()
        db.executemany("INSERT INTO meta VALUES(?,?)", (
            ("version", "reader3-dict-v1"), ("schema_version", "1"), ("build_date", date),
            ("sources", json.dumps(sources, ensure_ascii=False, sort_keys=True)),
            ("normalization", "NFC, lowercase, curly apostrophes to ASCII, boundary punctuation stripped, internal lexical apostrophes/hyphens preserved, whitespace collapsed"),
            ("coverage", json.dumps(stats, ensure_ascii=False, sort_keys=True)),
            ("database_license", "CC BY-SA 4.0 for the adapted collection; Open English WordNet remains CC BY 4.0; source notices retained"),
        ))
        db.commit()
        db.execute("ANALYZE")
        db.commit()
        db.execute("VACUUM")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("SQLite integrity or foreign-key check failed.")
        if temporary.stat().st_size > 400_000_000:
            raise RuntimeError("Database exceeds the 400 MB target; refine filtering before publishing.")
    finally:
        db.close()
    storage_check(stats)
    with temporary.open("rb") as source, compressed.open("wb") as target:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, mtime=0, fileobj=target) as stream:
            shutil.copyfileobj(source, stream, 1024 * 1024)
    storage_check(stats)
    temporary.replace(DATABASE)
    compressed.replace(DATABASE.with_suffix(".sqlite.gz"))
    stats.update(database_bytes=DATABASE.stat().st_size, gzip_bytes=DATABASE.with_suffix(".sqlite.gz").stat().st_size,
                 database_sha256=sha256(DATABASE), gzip_sha256=sha256(DATABASE.with_suffix(".sqlite.gz")))
    (OUT / "coverage.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
    (OUT / "SHA256SUMS").write_text(f"{stats['database_sha256']}  {DATABASE.name}\n"
                                    f"{stats['gzip_sha256']}  {DATABASE.name}.gz\n")
    for path in paths.values():
        path.unlink()
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    log(f"Built {DATABASE}; raw downloads deleted.")


if __name__ == "__main__":
    main()
