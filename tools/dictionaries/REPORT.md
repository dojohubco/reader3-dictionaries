# reader3 dictionary v1 — measured coverage

Built at 2026-10-12T02:32:07.109784+00:00 from the four checksum-pinned sources in `sources.lock.json`. Python 3.14.7, SQLite 3.51.2. Counts are measured from the final database; headword counts use distinct normalized keys, while entry counts include separate POS/source records.

- **EN→EN:** 675,878 headwords; 753,120 entries with English definitions.
- **KA→EN:** 23,641 headwords; 26,127 entries with an English gloss or explicit English translation. Within that total, 22,598 headwords / 23,052 entries have English glosses.
- **EN→KA:** 18,470 English headwords with ≥1 Georgian translation; 19,705 entries and 31,862 translation rows. This is 2.73% of the 677,046 English lookup headwords. The raw extract had 18,470 translated English headwords.
- **KA→KA:** 7,653 headwords; 7,912 entries with Georgian definitions. Parsed 7,663 definition-bearing pages from 9,091 Georgian-section pages in 26,453 main-namespace pages. Inflection-only pages are aliases, not counted definitions.
- **Forms:** EN 729,015 distinct forms / 835,582 mappings; KA 637,454 distinct forms / 794,500 mappings.
- **StarDict aliases:** all 560,363 records read and target bounds checked; 560,346 usable records mapped, 17 empty `-` placeholders excluded. One punctuation-only headword (`჻`) is excluded and has no alias references. 489 fallback English-gloss entries recover older StarDict targets absent from the raw extract's English-gloss inventory.
- **Final size:** 225,722,368 bytes = **225.72 MB** / 215.27 MiB. Gzip: 78,547,962 bytes = **78.55 MB** / 74.91 MiB.
- **Disk use:** observed `work/` + `out/` peak 3.31 GB; transient SQLite sort/VACUUM files were not continuously sampled. The expanded ~23.9 GB JSONL was never written. Raw downloads and extracted StarDict members were deleted after successful publication.

Database: `tools/dictionaries/out/reader3-dict-v1.sqlite`. Compressed distribution copy: `tools/dictionaries/out/reader3-dict-v1.sqlite.gz`. Neither is committed.

## Gaps and license limits

`out of habit` has no exact dictionary entry; the fallback finds **out of**, and the CLI explicitly labels that as a partial match. `ზეგარდმო` and `მონაბერითა` have no normalized entry/form in this build; neither those titles nor the `მონაბერი` lemma appears in the Georgian Wiktionary snapshot. No Georgian suffix guesses or invented meanings are added.

EN→KA remains sparse relative to the English lexicon. Georgian definitions cover 7,653 lemmas rather than the plan's approximate 9.5k estimate. Source-defined aliases are not contextual or universally complete Georgian lemmatization. 148,918 staged source relations have no retained same-POS lemma and are omitted; all usable StarDict `.syn` targets nevertheless resolve. WordNet is preferred for existing basic lemma/POS definitions, so its limited senses can omit meanings present in Wiktionary. Examples can illustrate a WordNet synset using a synonym of the selected word.

The Georgian parser handles common templates, not full MediaWiki/Lua expansion. Unsupported inline definition templates (name → occurrences): `{"!": 48, "link": 3, "senseid": 3, "ავტორი": 16, "მაგალითები": 3, "მაგალითი": 3, "მცირე": 6, "საბა": 27, "უმართებულო ჩაწერა": 6}`. Some qualifiers or template-only information may be lost. Source POS/gloss correctness has not been independently audited.

[WordNet is CC BY 4.0](https://github.com/globalwordnet/english-wordnet/blob/main/LICENSE.md); [Wiktionary reuse uses CC BY-SA 4.0 attribution/ShareAlike terms](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content). The StarDict data license is confirmed in its pinned `.ifo`; its GPL generator code is not incorporated. Notices, source-page attribution instructions, IPA provenance, and modification notices are stored in the database. Quotation records, images/audio, external reference sections, and all prohibited dictionary sites are excluded. Individual contributors' copyright chains were not audited. See [README.md](README.md) for source URLs and distribution obligations. Kaikki rotates its source URL; its pinned source must be preserved separately for future exact reproduction after rotation.

## Verification and requested lookups

11 fixture tests passed. All four source SHA-256 hashes were checked; the Georgian mirror also matched Wikimedia's published SHA-1. The live downloader was checked with a fresh WordNet download. Final SQLite integrity and foreign keys passed; form/entry languages match, normalized keys are nonempty, and no entry exceeds six stored senses. Decompressing the complete gzip reproduces the SQLite SHA-256. Exact/form/phrase query plans use indexed SEARCH paths:

```text
exact: SEARCH entries USING COVERING INDEX entries_lookup (lang=? AND headword_norm=?)
forms: SEARCH forms USING PRIMARY KEY (lang=? AND form_norm=?)
phrase: SEARCH entries USING COVERING INDEX entries_phrase (lang=? AND headword_norm=?)
```

These are desktop checks. Android/Room installation, phone latency, book selection, and the app popup UI have not been tested. The CLI was invoked separately for every word below:

- `provincial` (en): **exact** → provincial.
- `acquiesced` (en): **forms** → acquiesce.
- `frippery` (en): **exact** → frippery.
- `huckster's` (en): **morphy** → huckster.
- `axes` (en): **forms** → ax, axe, axis.
- `give up` (en): **exact** → give up.
- `out of habit` (en): **phrase** → out of.
- `წიგნებს` (ka): **forms** → წიგნი.
- `ვლაპარაკობ` (ka): **forms** → ლაპარაკობს.
- `ზეგარდმო` (ka): **none**; no offline result.
- `დათრგუნვად` (ka): **forms** → თრგუნავს.
- `მონაბერითა` (ka): **none**; no offline result.
- `ნაბადი` (ka): **exact** → ნაბადი.

Actual `python3 -I tools/dictionaries/query.py "<selection>" --lang en|ka` output:

```text
provincial [en] → provincial (exact)
Lemma: provincial · noun · /pɹəˈvɪn(t)ʃəl/
  1. [en] (Roman Catholic Church) an official in charge of an ecclesiastical province acting under the superior general of a religious order
     e.g. the general of the Jesuits receives monthly reports from the provincials
  2. [en] a country person
Lemma: provincial · adj · /pɹəˈvɪn(t)ʃəl/
  1. [en] of or associated with a province
     e.g. provincial government
  2. [en] characteristic of the provinces or their people
     e.g. deeply provincial and conformist
  3. [en] Of or pertaining to a province.
     e.g. a provincial government
  4. [en] Constituting a province.
  5. [en] Exhibiting the ways or manners of a province; characteristic of the inhabitants of a province.
  6. [en] Not cosmopolitan; limited in outlook; narrow; illiberal.
  → ka: პროვინციული

acquiesced [en] → acquiesced (forms)
Lemma: acquiesce · verb · /ˌækwiˈɛs/
  1. [en] to agree or express agreement
     e.g. The Maestro assented to the request for an encore

frippery [en] → frippery (exact)
Lemma: frippery · noun · /ˈfɹɪpəɹi/
  1. [en] something of little value or significance

huckster's [en] → huckster's (morphy)
Lemma: huckster · noun · /ˈhʌkstɚ/
  1. [en] a seller of shoddy goods
  2. [en] a person who writes radio or tv advertisements

axes [en] → axes (forms)
Lemma: ax · noun · /æks/
  1. [en] an edge tool with a heavy bladed head mounted across a handle
Lemma: axe · noun · /æks/
  1. [en] an edge tool with a heavy bladed head mounted across a handle
  2. [en] A tool for felling trees or chopping wood etc. consisting of a heavy head flattened to a blade on one side, and a handle attached to it.
  3. [en] An ancient weapon consisting of a head that has one or two blades and a long handle.
  4. [en] A dismissal or rejection.
     e.g. His girlfriend/boss/schoolmaster gave him the axe.
  5. [en] A drastic reduction or cutback.
     e.g. the Beeching Axe
  6. [en] A gigging musician's particular instrument, especially a guitar in rock music or a saxophone in jazz.
  → ka: ნაჯახი; ცული
Lemma: axis · noun · /ˈæksɪs/
  1. [en] in World War II the alliance of Germany and Italy in 1936 which later included Japan and other nations
     e.g. the Axis opposed the Allies in World War II
  2. [en] a straight line through a body or figure that satisfies certain conditions
  3. [en] the main stem or central part about which plant organs or plant parts such as branches are arranged
  4. [en] a group of countries in special alliance
  5. [en] the 2nd cervical vertebra; serves as a pivot for turning the head
  6. [en] the center around which something rotates
  → ka: ღერძი
Lemma: ax · verb · /æks/
  1. [en] chop or split with an ax
     e.g. ax wood
  2. [en] terminate
     e.g. they will ax the research program
Lemma: axe · verb · /æks/
  1. [en] chop or split with an ax
     e.g. ax wood
  2. [en] terminate
     e.g. they will ax the research program

give up [en] → give up (exact)
Lemma: give up · verb
  1. [en] lose (something) or lose the right to (something) by some error, offense, or crime
     e.g. you've forfeited your right to name your successor
  2. [en] give up with the intent of never claiming again
     e.g. Abandon your life to God
  3. [en] give up in the face of defeat of lacking hope; admit defeat
     e.g. In the second round, the challenger gave up
  4. [en] put an end to a state or an activity
     e.g. Quit teasing your little brother
  5. [en] give up what is not strictly needed
     e.g. he asked if they could spare one of their horses to speed his journey
  6. [en] part with a possession or right
     e.g. I am relinquishing my bedroom to the long-term house guest
  → ka: ბარდება; დათმობს; თავს ანებებს; თავს დაანებებს; თმობს; მიატოვებს; ნებდება; ფარ-ხმალს ყრის; ჩაბარდება; ხელს აიღებს; ხელს იღებს
Lemma: give up · adj
  1. [en] Become fully taken over by a certain quality, activity, trait, etc.

out of habit [en] → out of habit (phrase)
Partial phrase match within the selection.
Lemma: out of · adv
  1. [en] motivated by
     e.g. idleness is the trait of being idle out of a reluctance to work
Lemma: out of · prep · /ˈaʊt əv/
  1. [en] From the inside to the outside of.
     e.g. The audience came out of the theater.
  2. [en] So as no longer to be in a given condition or state.
     e.g. I have fallen out of love with you.
  3. [en] From a thing or place as a source, place of origin etc.
     e.g. He ate out of a big bowl.
  4. [en] Stating the port in which a boat has been registered.
     e.g. There's the Titanic out of Liverpool.
  5. [en] Taken from among; expressing a fraction of (a larger number);
     e.g. Only three out of a thousand are born with this rare disease.
  6. [en] Born from a given mother.
     e.g. She's a lovely little filly, by Big Lad, out of Damsel in Distress.

წიგნებს [ka] → წიგნებს (forms)
Lemma: წიგნი · noun · [t͡sʼiɡni]
  1. [en] book
  1. [ka] რაიმე დაბეჭდილი ტექსტის შემცველი ფურცლები, ერთად აკინძული.
  2. [ka] ვრცელი ლიტერატურული ნაწარმოების დიდი ქვეგანაყოფი.
  3. [ka] დავთრის სახით აკინძული სუფთა ფურცლები (ზოგჯერ გრაფებად დაყოფილი) სპეციალური დანიშნულებისა.
  4. [ka] (ძველი) წერილი, ბარათი.
  5. [ka] (სასაუბრო) კითხვა, წერა-კითხვა.
  6. [ka] (ძველი) წერილობითი საბუთი, ხელწერილი.
  → en: book; ledger; script; volume

ვლაპარაკობ [ka] → ვლაპარაკობ (forms)
Lemma: ლაპარაკობს · verb · [ɫäpʼäɾäkʼo̞bs]
  1. [en] to talk, to speak
  2. [en] to speak

ზეგარდმო [ka] → ზეგარდმო (none)
No offline result.

დათრგუნვად [ka] → დათრგუნვად (forms)
Lemma: თრგუნავს · verb · [tʰɾɡunäfs]
  1. [en] to suppress, to repress

მონაბერითა [ka] → მონაბერითა (none)
No offline result.

ნაბადი [ka] → ნაბადი (exact)
Lemma: ნაბადი · noun · [näbädi]
  1. [en] shepherd's cloak made of wool
  2. [en] shorn wool or fabric
  1. [ka] მოთელილი მატყლისაგან განსაკუთრებული წესით დამზადებული წამოსასხამი.
  2. [ka] მოთელილი მატყლი, სქელი ქსოვილის მსგავსად დამზადებული.
  3. [ka] რთული ფუძის მეორე შემადგენელი ნაწილი.
     e.g. გუდა-ნაბადი
  → en: burka
```

SHA-256:

```text
464f8f9c96e5a60788fa6fddc2dd21f389895796db6d1bd1ecd54e59528fa943  reader3-dict-v1.sqlite
e7a57d051e093fbd51bcd87dc461c869047f79e8d819c793a7c0aa1d8b96519d  reader3-dict-v1.sqlite.gz
```


## Four-pack distribution, 2026.10.12

Split the preserved `reader3-artifacts/reader3-dict-v1.sqlite` without downloading any source again. The source SHA-256 remains `464f8f9c96e5a60788fa6fddc2dd21f389895796db6d1bd1ecd54e59528fa943`.

| Pack | Gzip bytes | SQLite bytes | Gzip SHA-256 |
| --- | ---: | ---: | --- |
| `en-en` | 69,639,898 | 175,521,792 | `e9630c4efd40c49f80b99ce261cea6e1bd2da7a91aa49de50eb76bbd0a7c2b85` |
| `ka-ka` | 1,647,419 | 8,855,552 | `dc672f3be221ee464c595c03150efad3d3d48597b0452be0a83ceac71d1ecd10` |
| `en-ka` | 1,720,883 | 4,587,520 | `07e2f9d368c0f8cbced15dfccb1de39ce9f420872526fc1abb49dfd552c257cb` |
| `ka-en` | 7,311,021 | 44,167,168 | `721a5f92955923133d03bb3c045adee4ee546b496951dcf4708696827340aaf7` |

Each pack passed VACUUM, integrity_check and foreign_key_check. Direction/source entry IDs remain unchanged; source aliases are also mapped to the same normalized lemma/POS in the selected pack. English morphology is self-contained in both English packs. The splitter self-check passed and confirmed the source file was not modified.

Standalone Python lookup checks passed: `en-en`: provincial, acquiesced (forms), give up, coquetry; `en-ka`: provincial, give up, books (forms); `ka-ka`: წიგნებს (forms), ნაბადი; `ka-en`: წიგნებს (forms), ვლაპარაკობ (forms), ნაბადი. The source has no Georgian translation for every English word; the split does not invent one. Full rendered output is in the artifact directory's `packs/verification.json`.

[Public data repository](https://github.com/dojohubco/reader3-dictionaries) and [release v2026.10.12](https://github.com/dojohubco/reader3-dictionaries/releases/tag/v2026.10.12) contain the build pipeline, attribution/LICENSE/NOTICE and all five requested assets. Anonymous `curl -q -fsIL` returned 200 for all four gzip files, the versioned catalog and `/releases/latest/download/catalog.json`; a subsequent anonymous catalog GET matched the embedded Android catalog exactly.

Android implementation and physical-phone evidence are recorded separately in `docs/dev-screens/dictionary-catalog/README.md`. The adapted data remains CC BY-SA 4.0 with WordNet CC BY 4.0/Princeton notices; the app source repository is not pushed.
