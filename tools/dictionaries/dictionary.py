"""Normalization and read-only lookup shared by the builder and popup demo."""

import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "out/reader3-dict-v1.sqlite"
MAX_SENSES = 6
MORPHY_RULES = {
    "noun": (("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"),
             ("ches", "ch"), ("shes", "sh"), ("men", "man"), ("ies", "y")),
    "verb": (("s", ""), ("ies", "y"), ("es", "e"), ("es", ""),
             ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")),
    "adj": (("er", ""), ("est", ""), ("er", "e"), ("est", "e")),
}


def normalize(text):
    text = unicodedata.normalize("NFC", text).lower()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "ʼ": "'",
                                       "‐": "-", "‑": "-"}))
    text = "".join(" " if unicodedata.category(c).startswith("P")
                   and c not in "'-" else c for c in text)
    return unicodedata.normalize("NFC", " ".join(text.split()).strip("'- "))


def short(text, limit=320):
    text = " ".join(unicodedata.normalize("NFC", text).split())
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0] + "…"


def morphy_candidates(form, rules=MORPHY_RULES):
    """Return candidates with POS; callers must check them against the lexicon."""
    result = []
    if form.endswith("'s"):
        result.extend((form[:-2], pos) for pos in ("noun", "name"))
    elif form.endswith("s'"):
        result.extend((form[:-1], pos) for pos in ("noun", "name"))
    for pos, pairs in rules.items():
        for suffix, replacement in pairs:
            if len(form) > len(suffix) and form.endswith(suffix):
                result.append((form[:-len(suffix)] + replacement, pos))
    return list(dict.fromkeys(result))


def connect(path=DATABASE):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def lookup(db, text, lang):
    word = normalize(text)
    if not word or len(word) > 256:
        return "none", word, []
    exact = db.execute(
        "SELECT * FROM entries WHERE lang=? AND headword_norm=? ORDER BY source_id,id",
        (lang, word)).fetchall()
    if exact:
        return "exact", word, exact
    forms = db.execute(
        "SELECT e.* FROM forms f JOIN entries e ON e.id=f.entry_id "
        "WHERE f.lang=? AND f.form_norm=? ORDER BY e.source_id,e.id",
        (lang, word)).fetchall()
    if forms:
        return "forms", word, forms
    if lang == "en":
        rules = {}
        for row in db.execute("SELECT pos,suffix,replacement FROM morphy_rules ORDER BY pos,priority"):
            rules.setdefault(row["pos"], []).append((row["suffix"], row["replacement"]))
        matches = {}
        for lemma, pos in morphy_candidates(word, rules):
            for row in db.execute(
                    "SELECT * FROM entries WHERE lang='en' AND headword_norm=? AND pos=?",
                    (lemma, pos)):
                matches[row["id"]] = row
        if matches:
            return "morphy", word, sorted(matches.values(), key=lambda r: (r["source_id"], r["id"]))
    tokens = word.split()
    # shortcut: contiguous phrases in at most 16 selected tokens, expand for sentence search.
    if 2 <= len(tokens) <= 16:
        for width in range(min(8, len(tokens)), 1, -1):
            phrases = list(dict.fromkeys(" ".join(tokens[i:i + width])
                                        for i in range(len(tokens) - width + 1)))
            marks = ",".join("?" for _ in phrases)
            rows = db.execute(
                f"SELECT * FROM entries WHERE lang=? AND instr(headword_norm,' ')>0 "
                f"AND headword_norm IN ({marks}) ORDER BY source_id,id", (lang, *phrases)).fetchall()
            if rows:
                return "phrase", word, rows
    return "none", word, []


def render(db, text, lang):
    route, normalized, rows = lookup(db, text, lang)
    lines = [f"{text} [{lang}] → {normalized} ({route})"]
    if not rows:
        return "\n".join(lines + ["No offline result."])
    if route == "phrase":
        lines.append("Partial phrase match within the selection.")
    groups = {}
    for row in rows:
        groups.setdefault((row["headword_norm"], row["pos"]), []).append(row)
    for group in groups.values():
        first = group[0]
        ipa = next((r["ipa"] for r in group if r["ipa"]), None)
        lines.append(f"Lemma: {first['headword']} · {first['pos']}" + (f" · {ipa}" if ipa else ""))
        seen = set()
        counts = {}
        translations = []
        for entry in group:
            for sense in db.execute("SELECT * FROM senses WHERE entry_id=? ORDER BY idx", (entry["id"],)):
                key = (sense["gloss_lang"], sense["gloss"])
                code = sense["gloss_lang"]
                if key in seen or counts.get(code, 0) >= MAX_SENSES:
                    continue
                seen.add(key)
                counts[code] = counts.get(code, 0) + 1
                lines.append(f"  {counts[code]}. [{code}] {sense['gloss']}")
                if sense["example"]:
                    lines.append(f"     e.g. {sense['example']}")
            translations.extend(db.execute(
                "SELECT target_lang,text,sense_idx FROM translations WHERE entry_id=? "
                "ORDER BY target_lang,text", (entry["id"],)).fetchall())
        for target in sorted({r["target_lang"] for r in translations}):
            terms = list(dict.fromkeys(r["text"] for r in translations if r["target_lang"] == target))
            lines.append(f"  → {target}: " + "; ".join(terms))
    return "\n".join(lines)
