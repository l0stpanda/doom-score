# Archive

Historical or superseded files, kept for reference (moved with `git mv`, so their history is intact). Nothing in
the build reads from here. Reasons below; see `docs/cleanup_plan.md` for the full inventory.

| Path | Why archived |
|---|---|
| `docs/FEATURE_CROSSWALK.md` | Concept → league-column crosswalk; superseded by `docs/FEATURES.md` and `docs/CROSS_LEAGUE_HANDOFF.md` (`build_crosswalk.py` now writes `reports/feature_crosswalk.md`) |
| `docs/DATA_DICTIONARY.md` | Column dictionary of the 104-column full table; superseded by `docs/DATA.md` + `docs/FEATURES.md`, still the most detailed per-column reference |
| `docs/DATASET_GUIDE.md` | Long groupmate guide (feature-by-feature notes, sports primer); replaced by the condensed docs |
| `docs/DATA_COLLECTION.md` | Long "how the data was built" guide; replaced by `docs/DATA.md` and `docs/PROJECT_LOG.md` |
| `docs/doc_stats.json`, `docs/make_doc_stats.py` | Generator and numbers for the two guides above (paths not updated; will not run from here) |
| `src/make_data_dictionary.py` | Generator of `DATA_DICTIONARY.md`; not part of the build any more |
| `prompts/mlb_nhl_data_prompt.md` | Phase 1–4 data-build instructions (historical) |
| `prompts/doom_modeling_prompt.md` | Phase M1–V1 modeling instructions (historical) |
| `reports/phase1*`–`phase4*`, `crosswalk_checks.csv`, `full_rerun_log.txt` | Data-build phase reports, checks and logs; rewritten to `reports/` only by `build_all.py --from-raw` |
| `data/front_office_spans.csv` | GM/coach spans parsed from Wikipedia (phase 2 provenance for tenure features); not read by the build |
