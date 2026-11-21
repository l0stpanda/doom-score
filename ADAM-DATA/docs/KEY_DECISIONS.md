# Key decisions

The decisions that most affect how to read the results, one line each. The full log (D01–D108, with
alternatives and reasons) lives in tag `adam-full-pipeline`:
`git show adam-full-pipeline:ADAM-DATA/DECISIONS.md`.

| ID | Decision |
|---|---|
| D10 | Standing = within-league-season percentile of win %, `(average rank − 1)/(n − 1) × 100`; worst 0, best 100 |
| D07 | NHL win % = points % (overtime/shootout losses count as half a win) |
| D11 | Doom = 100 − mean percentile over the franchise's next three **played** seasons; no label unless all three exist |
| D29 | Prediction moment: MLB Nov 15 of t, NHL Jun 15 of t+1; every feature must be known by then |
| D03, D05, D06 | One franchise id through moves and renames; the current team name is used for every season |
| D59 | Features are within-league-season percentiles (`_lpct`), so leagues and eras share one scale |
| D61 | Model features chosen by concept, not by correlation with the outcome |
| D63 | MLB "underlying quality" excluded: it is Pythagorean win %, a near-duplicate of run margin |
| D64 | Walk-forward backtest: season T is predicted by a model trained only on seasons ≤ T−3 (labels known by then) |
| D72 | Uncertainty of model differences: moving-block bootstrap over test seasons (blocks of 3) |
| D76 | Model choice: the simplest model within noise of the best → **MLB = standings only (B1), NHL = elastic net** |
| D86 | Six pre-registered MLB features did not beat standings beyond noise; BaseRuns margin alone did but is future work |
| D54, D79 | NHL expected goals (xG) not used: MoneyPuck's xG model saw future seasons (soft leakage); Corsi used instead |
| D57 | No NHL payroll data, so the NHL model has no spending term |
| D80 | 80% intervals = split conformal from walk-forward errors of earlier seasons (≥ 2 calibration seasons needed) |
| D99, D100 | `p_doom75` = chance doom ends ≥ 75 given the prediction; bands Low < 10%, Moderate 10–30%, High 30–50%, Very high ≥ 50% |
| D88 | 3-year paths come from per-horizon models, shifted so their average equals the headline doom score |
| D92 | Live seasons (MLB 2024–26, NHL 2023–25) use models refit on all earlier labelled seasons; not strictly out-of-sample |
| D90 | No Baseball-Reference data is used anywhere |

Repository note: on `adam` the slim table also carries five non-model columns (three MLB context percentiles,
`team_id`, `logo_url`), so the dashboard rebuilds from that one file.
