# reader3 offline dictionaries, v1

This desktop pipeline implements the offline part of `PLAN.md` §4.3 and §5. It builds one lookup database for English and Georgian books. It does not modify the Android app or publish a release.

## Run

Python 3.9+ and the `zstd` command are required. No Python packages, venv, sudo, credentials, or network access at lookup time are needed. All paths resolve relative to these scripts, so the commands also work from another current directory.

```sh
python3 -I tools/dictionaries/test_dictionary.py
python3 -I tools/dictionaries/build.py
python3 -I tools/dictionaries/query.py "acquiesced" --lang en
python3 -I tools/dictionaries/query.py "წიგნებს" --lang ka
```

In this workspace, prefix shell commands with `rtk`, as required by its AGENTS instructions. `-I` isolates Python from user packages and `PYTHONPATH`; scripts explicitly add only their own resolved directory for sibling imports.

Outputs, all ignored by git:

- `out/reader3-dict-v1.sqlite`: the database, with a hard limit of **400,000,000 bytes**.
- `out/reader3-dict-v1.sqlite.gz`: deterministic gzip framing (`mtime=0`, no embedded filename), level 9.
- `out/coverage.json`: measured direction counts, alias counts, sizes, hashes, and parser omissions.
- `out/SHA256SUMS`: checksums for both distribution files.

Download/cache files and SQLite temporary files stay in `work/`. Successful builds delete raw downloads and extracted StarDict members. Failed builds preserve downloads for retry and leave the previous final database in place. Partial HTTP downloads resume where supported; source byte counts and SHA-256 must match before ingestion. Lookup opens SQLite with `mode=ro`, including when `--db PATH` overrides the default.

`sources.lock.json` pins the exact source bytes. WordNet, StarDict, and the Georgian dump have dated URLs. **Kaikki's URL rotates**: the build refuses changed bytes instead of silently producing a different v1. After that URL rotates, exact reproduction needs a preserved copy of the locked gzip placed at `work/wiktextract.jsonl.gz`. Upstream does not promise permanent snapshot availability. To intentionally update sources, inspect their licenses, dates, formats, and hashes, update the lock, then regenerate the report; do not bypass checksum verification.

Build date defaults to current UTC. Set `SOURCE_DATE_EPOCH` to the same Unix timestamp for repeatable build-date metadata. Measured storage telemetry depends on existing files; SQLite page layout and gzip bytes can also vary across Python/SQLite/zlib versions. Source content, insertion order, schema and filtering are pinned. This is a reproducible ingestion pipeline, not a claim of cross-platform byte-identical SQLite files.

## Sources and licenses

Only these sources are downloaded:

- [Open English WordNet 2025 Plus](https://github.com/globalwordnet/english-wordnet): the [2025 Plus WNDB ZIP](https://en-word.net/static/english-wordnet-2025-plus.zip), including Morphy exception files. **CC BY 4.0**. The complete notice shipped in its data header, including the Princeton WordNet notice and disclaimer, is preserved in `sources.attribution`. The header has an older copyright year; the actual archive version is pinned separately.
- [Kaikki's raw English-edition Wiktextract extract](https://kaikki.org/dictionary/rawdata.html): English and Georgian records from the 2026-09-02 English Wiktionary dump, extracted 2026-10-03. **CC BY-SA 4.0** for the Wiktionary text. Raw data is used; Kaikki's deprecated, postprocessed dictionary files, which merge other sources, are excluded. [Wiktextract's format documentation](https://github.com/tatuylonen/wiktextract) describes the fields.
- [xxyzz's 20260928 Georgian-English StarDict snapshot](https://github.com/xxyzz/wiktionary_stardict/releases/tag/20260928): its `.ifo` declares **CC BY-SA 4.0** for the dictionary data, 23,021 indexed headwords, and **560,363 `.syn` aliases**. The repository's extraction code is GPL-3.0; none of that code is copied or executed. Only the explicitly licensed dictionary data is ingested. Images, CSS, and other resources are excluded.
- [Georgian Wiktionary, 2026-10-01 pages-articles dump](https://dumps.wikimedia.org/kawiktionary/20261001/), via a [Wikimedia-listed mirror](https://meta.wikimedia.org/wiki/Mirroring_Wikimedia_project_XML_dumps): **CC BY-SA 4.0**. Its published SHA-1 and our SHA-256 are in the lock. Only main-namespace pages and Georgian language sections contribute definitions.

[Wikimedia's reuse terms](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content) require attribution, license information, and notice of modifications. The adapted dictionary collection is marked CC BY-SA 4.0 in `meta.database_license`; WordNet retains its CC BY 4.0 notice. A private GitHub release is still redistribution: retain these notices and the ShareAlike terms with the database.

The app's About/licenses screen can read `sources` directly. For a Wiktionary result, also link its source page using the **original `headword`**, URL-encoded, under `https://en.wiktionary.org/wiki/` for source 2/3 or `https://ka.wiktionary.org/wiki/` for source 4; page histories credit individual contributors. When `ipa_source_id` is present, credit that source as well. Changes are recorded in the attribution text: filtering, normalization, parser extraction, and truncation.

Wiktionary can contain third-party quotations with different rights. Kaikki examples are retained only when explicitly marked `type=example` and lacking a citation `ref`. Quotations, audio, images, and references are omitted. Georgian `ციტატა` quotation blocks and resource sections are omitted; only the dictionary's definition text and simple `მაგალითები` usage examples are retained. Upstream licensing is relied upon; individual contributors' copyright chains have not been audited.

No content is downloaded from ena.ge, ganmarteba.ge, dictionary.ge, translate.ge, Freelang, or UniMorph. Links to external references inside Wiktionary pages are not followed or stored as definitions.

## Filtering and storage budget

The ~2.98 GB raw gzip is read one JSONL line at a time. The ~23.9 GB expanded extract is **never written to disk**. A byte-level language prefilter precedes decoding; the JSON root's `lang_code` is then checked. The pinned source hash makes the accepted serialization explicit. ZIP data, bz2 XML pages, and `.syn` aliases are processed incrementally; only the small WordNet synset maps and StarDict index are held in memory. StarDict decompression uses the installed `zstd` CLI, with an allowlist of four members and size validation, rather than unpacking arbitrary archive paths.

The normal build requires roughly 3–5 GB at peak, including the raw gzip, database, indices, VACUUM, and compression. The script checks its `work/` + `out/` files against an 8 GB budget. `peak_work_out_bytes_observed` is a sampled value; it is not a continuous measurement of SQLite's transient sort/VACUUM files. Existing outputs count towards the budget.

English WordNet is the base, with sense order taken from its index files. English Wiktionary contributes missing lemma/POS combinations, multiword expressions, function words, and entries carrying Georgian translations. Duplicate basic WordNet definitions are not copied merely to repeat the same lemma/POS. IPA from Wiktionary can enrich an existing WordNet entry with separate provenance. English form-only and alternative-spelling senses become aliases, rather than popup entries saying only “past tense of …”.

English Wiktionary's lexical POS allowlist is noun, verb, adjective, adverb, phrase, prepositional/adverbial phrase, proverb, conjunction, pronoun, determiner, preposition, postposition, article, particle, interjection, numeral, and contraction. Other POS, including proper names and affixes, are retained as translation-only entries when they have a Georgian translation. English normalized headwords over 120 characters are excluded. Archaic and obsolete lexical senses remain useful for books and are retained.

Entries merge repeated etymologies for the same source, original headword, and POS. Each entry has at most six distinct senses, each with a gloss of at most 320 characters and at most one 220-character example. One IPA is retained, without accent ranking or pronunciation generation. Translations are deduplicated per entry and target language; `sense_idx` is assigned only for an exact match to a retained gloss, otherwise NULL. A NULL translation must not be presented as attached to a particular sense.

KA→EN primarily uses raw Kaikki Georgian records. StarDict's older HTML provides a short-gloss fallback if a `.syn` target has no English gloss in the newer extract; every index target is validated. All **560,363 raw `.syn` records** must be read successfully. Punctuation-only headwords and empty/`-` inflection placeholders are excluded, with their counts reported; every usable alias must resolve. Normalized aliases can deduplicate, or map to several entries/POS/sources; raw alias count, distinct normalized form count, and final mapping-row count are different measurements.

KA→KA parses numbered `#` definitions and older `:[n]` definitions within meaning sections, POS markers, explicit IPA, English translation templates, redirects, and explicitly identified inflected forms. Inflection descriptions become aliases, not counted lexical definitions. Known inline templates and links are simplified; this is not a full MediaWiki/Lua expansion engine. Unsupported definition-template names are counted in `coverage.json`. Upgrade the parser when those omissions materially affect the books being read.

## Schema and Android lookup contract

This is plain SQLite, `user_version=1`, using ordinary B-tree indices and `WITHOUT ROWID` tables. It needs no FTS extension. It is suitable for a separate read-only Android SQLite connection; the Android/Room integration and download/install flow are subsequent work.

```sql
meta(key PRIMARY KEY, value)
sources(id PRIMARY KEY, name, license, url, attribution)
entries(id PRIMARY KEY, lang, headword, headword_norm, pos, ipa,
        source_id REFERENCES sources, ipa_source_id NULL REFERENCES sources)
senses(entry_id REFERENCES entries, idx, gloss, gloss_lang, example,
       PRIMARY KEY(entry_id, idx))
translations(entry_id REFERENCES entries, target_lang, text, sense_idx NULL,
             PRIMARY KEY(entry_id, target_lang, text))
forms(form_norm, lang, entry_id REFERENCES entries, source_id REFERENCES sources,
      PRIMARY KEY(lang, form_norm, entry_id))
morphy_rules(pos, suffix, replacement, priority, PRIMARY KEY(pos, priority))
```

`translations(entry_id,sense_idx)` also has a foreign key to `senses`. `forms.source_id` credits one origin of that mapping: the first imported origin wins when several sources provide identical `(lang,form_norm,entry_id)`. It is separate from the definition's source. Rules materialized against observed English surface forms use source 1 to identify the Morphy rule source; the entry retains its own lexical provenance. Build-only alias/surface staging tables are dropped.

- Exact index: `entries_lookup(lang, headword_norm)`.
- Forms index: the composite `forms` primary key starts with `(lang, form_norm)`.
- Phrase index: `entries_phrase(lang, headword_norm) WHERE instr(headword_norm,' ')>0`.
- Senses/translations primary keys start with `entry_id` for popup fetches.

Normalization is identical for ingestion and lookup:

1. Unicode NFC and Unicode lowercase. This also maps modern Georgian Mtavruli capitals to Mkhedruli; it does not transliterate historical Georgian scripts.
2. Curly/modifier apostrophes `’`, `‘`, `ʼ` → ASCII `'`; Unicode lexical hyphens `‐`, `‑` → `-`.
3. Punctuation becomes whitespace except internal apostrophes/hyphens, preserving `huckster's` and `re-sign`. Boundary apostrophes, hyphens and spaces are stripped. This means punctuation-only selections have no result and affix boundaries are not distinguished in normalized lookup.
4. Collapse whitespace, then NFC again. WordNet `_` collocations are converted to spaces before normalization. Diacritics are retained; SQLite's ASCII-only `lower()` must not replace this normalization in the app.

Lookup, demonstrated in `dictionary.py` / `query.py`:

1. Normalize the selected word/phrase; fetch **all** entries with matching `(lang, headword_norm)`.
2. If there is no exact entry, join **all** matching `forms` rows to entries, preserving multiple lemmas and POS.
3. If still missing and English, apply the stored, POS-specific [WordNet Morphy suffix rules](https://wordnet.princeton.edu/documentation/morphy7wn), plus possessive stripping, and accept only candidates actually present in that POS. Irregular exceptions and rule matches for observed English Wiktionary surface headwords are already materialized in `forms` during the build. No Georgian suffix guessing is performed.
4. If still missing and multiword, try longest contiguous phrases of 2–8 tokens within a selection of at most 16 tokens using the partial phrase index. Exact phrase selections such as `give up` already succeed in step 1. Shorter matches are labelled **partial phrase matches**; they do not define the whole selection. This fallback does not invent meanings for unattested phrases or reorder words.
5. Return an explicit miss. The app can then show its separately labelled AI block, as specified in the plan.

The CLI prints the route, matched lemma/POS, one IPA where available, up to six deduplicated senses **per gloss language and lemma/POS group**, one example per sense, and translations. Source priority is WordNet, raw Wiktionary, StarDict fallback, then Georgian Wiktionary. Multiple sources for a lemma remain separately attributable in the database even though the CLI groups them for display.

## Verification

`test_dictionary.py` uses small synthetic fixtures to test WordNet offset parsing/sense order, exception aliases, malformed StarDict records, quotation removal, Georgian language/meaning boundaries, old/new definition styles, normalization, ambiguity, POS filtering, exact/form/Morphy/phrase precedence, SQL indices, sense limits, foreign keys, read-only access, and checksum rejection. Tests require no downloads.

The full builder checks source hashes, pinned `.syn` count, StarDict target bounds and license, SQLite integrity and foreign keys, and final size before replacing the output. `REPORT.md` records the full-build measurements and actual CLI output for the requested words. Counts describe dictionary coverage; they do not measure accuracy or contextual translation quality. Phone latency, Android SQLite/Room integration, and real-book selection behavior have not been tested here.
