# Measurement inputs: IC test GMX v2

Run 2026-10-08T05:00:08Z. 500 addresses declared, 500 payloads, 39,945 trades; 152 scored after the trade floors.

| Item | SHA-256 |
|---|---|
| payloads manifest, 500 files (published here) | b98fcde64a17022c9c5cc9d89dae79bcf3ba44d3c5beb44d92788e453d086a96 |
| full result JSON (withheld, per-agent table) | 72f6a62b5a4c6637b191c77305cdf55afd13d1b52517f7e32bd2d62b6e7bf0f1 |
| aggregate result JSON (published here) | 528c3f792957d6839b95428d607cc3e7c897238c7042d367ec9cddfc7d1611de |
| wallets_gmx_addresses.txt, sorted by address, addresses only (published here) | a6bde4c9b6c37265e2d241ffb0d7f7e35d87369246fddef1e378f45ba62284cb |
| wallets_gmx.txt (withheld, per-agent statistics) | ace994d6b341481967d4761b1331133880557f4acc49d80c4f012327fc0eec81 |
| gmx_discover_raw.json (withheld) | 2fbb044d9374ac1beee40187e6aae2d26f500c942cca2a96b8000b42aae64c8b |
| feed_yaaf_gmx.py (collector/) | 12ec33a2333b1bfd8740b37594e0ea5c2d60fb1a049ff5faafec75b3465478d1 |
| discover_gmx.py (collector/) | 5be9ec7a33cb43cb32eba39390a6e5178b84fcedb9e5e205ae7bfbfdd40a3888 |
| collectors/gmx.py (collector/) | 5f7c0e1d97b8e5d4183daee034d5ddb8e52749d5b45e90dac8a7b4c742995967 |
| store/sqlite.py, pre-edit version from the .bak (collector/) | 8b75edd24f1287121c834d8134fa03633488c425eddcaaf7770d69d5536fbade |
| store/sqlite.py, current (not published) | 17dfee0e7169187ca4902aed9e80c9f9eaa806f265585f8e8045a295791ba07a |
| yaaf_score_v5_formal.py (scorer/ in this repo) | 4a399818f60969c03ac09e46f2416805ab625471e7c4c9be8aa9d32d6b687680 |
| ic_test_gmx_v2.py (docs/evidence/ in this repo) | f3d843fde721933251294fea019bc516b1eb75c34021d27f679035361fa584dd |
| ic_test_gmx.py (docs/evidence/ in this repo) | e4880dc60a2f1acaa1c74b89208885a87f37748b9dbdf12d614b3dd3e9beb544 |
| selection_check.py (analysis/) | 416b594887486dad3544e4a94d9187c931ffe23c88f4d3a274abad3f5febd16b |
| selection_check2.py (analysis/) | 270aaf92a99093cc5256d002c17bdb3bfde276e39122f81d36580735cf71ffc3 |
| selection_check3.py (analysis/) | e09a7a12a4058a8b4aa87ca89eee83ffce8d2016e4b353a10755f41401fbe30b |
| weights_diag2.py (analysis/) | 587673109f7352a355c83b60b9fe1b9746d42610ffc491ba838850763c28945b |
| _summary.json, the 500 payloads concatenated by the collector (withheld, per-agent statistics) | be8739e76375c3bface23fc929dec8bfa2384cc57d218a0b320552e1de9101a8 |
| private evidence tarball (not published) | ad1478b5a5856f4226e36aeb2075113e45eef6e2010564a2a80372e5fdefee3b |

## Checked on the host when this record was written

- Payloads: all 500 verify against the manifest; 39,945 trades.
- Scorer: the commit that introduced the file as it ran is 1058f9a2f2be6721c6ddcfcaddbfecd75e933da9 de 2026-10-07 13:01:16 +0000; blob 3c0aa19f4af007d56ccea41937af1712b433fc22.
- *Corrected after this file was first committed.* It previously named scorer_commit b579e56a23f266dc18fa917c14c8e1278f863b54. That check passed, because b579e56a's tree contains the same blob, but b579e56a did not touch the scorer: `git log -1 -- scorer/yaaf_score_v5_formal.py` returns the commit above, earlier the same day. Naming b579e56a dated the scorer later than it is and pointed an auditor at a commit about the public API. The correction is recorded rather than amended, because the history of the corrections is part of the evidence.
- gmx_discover_raw.json: encontrado, mtime 2026-10-06 13:39:02.279398689 +0000, 500 identico aos 500: True
- Source paths of the analysis scripts: /root/aiagentregistry-observatory/selection_check.py /root/selection_check2.py /root/aiagentregistry-observatory/selection_check3.py

## What this record does and does not establish

- Collector provenance: observatory_commit is None in the result. The collector was not under version control when the run happened. feed_yaaf_gmx.py has mtime 2026-10-08 03:31Z, before the first payload (04:41Z): consistent with being the version that ran, not proof.
- Measurement script: ic_test_gmx_v2.py and ic_test_gmx.py in this repository are byte-identical to the working-tree copies. The working-tree copy of ic_test_gmx_v2.py has mtime 04:02Z, before the run (05:00:08Z).
- Protocol documents: first committed 2026-10-08T14:06:57Z, about nine hours AFTER the run. This record does not claim a pre-registration that a third party can verify. See the addendum in IC_PROTOCOL_v2.md.
- Universe: the 500 addresses are the output of discover_gmx.py (v1), not discover_gmx_v2.py. The evidence is the default output file, the line format, the default min_trades of 10 (the minimum among the 500 is exactly 10), and a top-half / bottom-half split by aggregate dollar PnL. The arguments actually passed were not recorded. The universe is therefore outcome-selected; see the addendum in IC_PROTOCOL_v2.md before reading any figure from it.
- store/sqlite.py published here is the pre-edit version. The later version only adds nonce functions; compute_yaf_metrics does not touch the database.
- analysis/ holds the scripts behind the tables in the v2 addendum (selection_check*.py) and the outcome-blind weight diagnostic (weights_diag2.py). They hardcode host paths and read the withheld per-agent result and wallet files, so they are inspectable here and re-runnable only with those files.
- Withheld because they carry per-agent statistics: the per-agent table (observacoes, 152 rows), the full result JSON, wallets_gmx.txt, gmx_discover_raw.json. Their hashes are above; the canonical-JSON hash of the per-agent table is in the aggregate file.
- To re-run ic_test_gmx_v2.py: it hardcodes OBS=/root/aiagentregistry-observatory and SCORER=/root/yaaf/scorer and reads payloads from OBS/yaaf_payloads_gmx. Mirror that layout rather than editing the script, because editing it changes its hash.
- The payload directory holds **501** files against a manifest of 500. The extra one is `_summary.json`, the same 500 records concatenated by the collector: top-level list, each element carrying `agent_id`, `metrics`, `source`, `trades`, `ts`. It is not an input. `ic_test_gmx_v2.py` line 147 excludes it by rule, not by accident: `[f for f in sorted(PAYLOADS.glob("*.json")) if not f.stem.startswith("_")]`. Its mtime is 2026-10-08T04:50:19Z, ten minutes before the run at 05:00:08Z, so it was present and skipped by that filter, which is why the count is 500 and not 501. The manifest covers the 500 inputs and deliberately not this file. It is withheld for the same reason as the payloads: per-agent statistics, keyed by address. Its hash is in the table above, so an auditor can confirm the file they find is the file described here without being given it.

## Precondition for every future measurement

No measurement is canonical unless the hash manifest of its inputs, and the commit of the collector and scorer that produced them, are committed in the same commit as its result.
