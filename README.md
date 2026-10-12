# reader3 offline dictionaries

Four independently downloadable offline SQLite dictionary packs for English and Georgian EPUB reading. No app code or credentials are published here.

| Pack | Download (gzip) | Installed (SQLite) |
| --- | ---: | ---: |
| English (`en-en`) | 69.64 MB | 175.52 MB |
| ქართული განმარტებითი (`ka-ka`) | 1.65 MB | 8.86 MB |
| English → ქართული (`en-ka`) | 1.72 MB | 4.59 MB |
| ქართული → English (`ka-en`) | 7.31 MB | 44.17 MB |

- **English**: EN-EN definitions from Open English WordNet 2025 Plus and English Wiktionary, with English form/Morphy aliases.
- **ქართული განმარტებითი**: KA-KA Georgian Wiktionary definitions, with matching Georgian form-to-lemma aliases.
- **English → ქართული**: EN-KA translations from English Wiktionary/Kaikki, with English forms and Morphy rules. Coverage is sparse (18,470 translated headwords).
- **ქართული → English**: KA-EN English glosses and translations from Wiktionary/Kaikki and StarDict, including Georgian form-to-lemma aliases.

Each pack has the same schema (`user_version=1`) and its own source notices, metadata and lookup indexes. Packs work independently. Source entry IDs are preserved across packs. Translation packs preserve only needed glosses and sense references. Form aliases are also mapped to entries with the same normalized lemma/POS across sources. No Georgian suffix guessing is added.

Download from the [v2026.10.12 release](https://github.com/dojohubco/reader3-dictionaries/releases/tag/v2026.10.12). The app reads the [latest catalog](https://github.com/dojohubco/reader3-dictionaries/releases/latest/download/catalog.json); its versioned asset URLs, compressed SHA-256 and download/installed sizes pin each transfer. Files are release assets, not Git blobs.

## Build

The complete standard-library Python ingestion pipeline is in [tools/dictionaries](tools/dictionaries/README.md); locked source URLs, dates and hashes are in [sources.lock.json](tools/dictionaries/sources.lock.json). [split_packs.py](tools/dictionaries/split_packs.py) splits an existing v1 database without fetching sources:

```sh
python3 -I tools/dictionaries/test_dictionary.py
python3 -I tools/dictionaries/build.py
python3 -I tools/dictionaries/split_packs.py --db tools/dictionaries/out/reader3-dict-v1.sqlite --out packs
python3 -I tools/dictionaries/query.py provincial --lang en --db packs/en-en.sqlite
```

The splitter uses SQL with an 8 MiB page cache and disk-backed temporary work, writes gzip in 64 KiB blocks, retains provenance, VACUUMs each pack, and checks integrity and foreign keys. The original build is described in [REPORT.md](tools/dictionaries/REPORT.md). Kaikki rotates its upstream URL: a future exact rebuild needs a preserved copy of the checksum-pinned input. Splitting the preserved database does not need those source downloads. SQLite/gzip layout may differ between SQLite/zlib versions.

## Sources and licenses

The adapted data packs are **CC BY-SA 4.0**, including ShareAlike for redistributed adaptations of Wiktionary data. Open English WordNet content retains **CC BY 4.0** and its Princeton WordNet attribution/notice. These data licenses apply to the data packs; they do not apply to the private reader3 Android code.

- [Open English WordNet 2025 Plus](https://github.com/globalwordnet/english-wordnet), including Morphy exceptions: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and the Princeton WordNet notice.
- English Wiktionary, raw [Kaikki/Wiktextract](https://kaikki.org/dictionary/rawdata.html) extraction (2026-09-02 dump / 2026-10-03 extraction): [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
- [Georgian-English StarDict data](https://github.com/xxyzz/wiktionary_stardict/releases/tag/20260928): CC BY-SA 4.0 as declared by its `.ifo`. Its GPL extraction code is not included or executed.
- [Georgian Wiktionary 2026-10-01](https://dumps.wikimedia.org/kawiktionary/20261001/): CC BY-SA 4.0.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for complete retained source notices, attribution and modifications. Each SQLite file also contains these in `sources.attribution` and the adapted collection notice in `meta.database_license`. For individual Wiktionary entries, credit contributors by linking the original headword page and its history: `https://en.wiktionary.org/wiki/<headword>` for sources 2/3, `https://ka.wiktionary.org/wiki/<headword>` for source 4. Also retain IPA/form provenance.

Changes include source filtering, normalization, text extraction/truncation, quotation/resource omission, separation by direction and alias mapping between matching lemma/POS entries. No audio, images or private app files are included. Source coverage and correctness are not guarantees of contextual translation accuracy.
