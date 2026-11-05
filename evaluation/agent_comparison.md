# Agent Comparison: Agent-Generated vs Human-Written Profiles

This document compares the output of the metadata agent (`agents/metadata_agent.py`) and the semantic agent (`agents/semantic_agent.py`) with the human-written profiles from Assignment 1. Those profiles are the data dictionaries in `data_dictionaries/` and the EDA notebooks in `EDA/`.

All numbers come from `python run_pipeline.py --offline`. That command evaluates semantic run `test_001` on both datasets, and the results are saved in `outputs/agent_integration/test_001_evaluation_results.json`.

## Method

| What is evaluated | Human reference | How it is scored |
|---|---|---|
| Metadata statistics | Independent pandas recalculation; row counts and keys from the EDA notebooks | Every null count, distinct count, min, max, mean and median must match. Both the pandas and the SQL (DuckDB) results are checked. |
| Metadata agent on raw data | Data-quality problems found in the EDA notebooks | Each problem is **detected** (reported directly), **visible** (inferable, but not flagged) or **missed** |
| Semantic descriptions | Data dictionaries, plus a manual review of each column | Units and value codes are compared automatically. Each column's meaning is judged by hand as correct, partially correct or incorrect. |
| Cross-dataset relationships | 14 column pairs that mean the same thing in both datasets, taken from the data dictionaries | How many pairs the agent finds, and whether they are correct |

## Results

| Measure | Heart | Cardio | Total |
|---|---|---|---|
| Metadata statistics correct | 196 / 196 | 184 / 184 | **380 / 380** |
| Primary key identified | yes | yes | 2 / 2 |
| Raw-data problems: detected / visible / missed | 2 / 0 / 2 | 0 / 2 / 1 | **2 / 2 / 3** of 7 |
| Column meaning correct | 14 / 16 | 13 / 15 | **27 / 31 (87%)** |
| Value codes fully correct | 8 / 9 | 7 / 8 | **15 / 17** |
| Units correct, where the dictionary gives one | 5 / 5 | 4 / 5 (+1 hedged guess) | **9 / 10**, 0 wrong |
| Errors the agent flagged itself | 2 / 2 | 1 / 2 | **3 / 4** |
| Relationships found | | | **3 / 14** (all 3 correct) |

## Metadata agent

**Accuracy.** Every statistic it reports is correct, and the pandas and SQL paths agree. Row and column counts match the EDA notebooks (297 × 16 and 1,000 × 15), and it identifies `patient_id` and `patientid` as the primary keys.

**What it misses.** We also ran it on the original, uncleaned CSVs:

| Problem found in the EDA | Agent |
|---|---|
| Heart: 4 missing `ca` values, 2 missing `thal` values | Detected (null counts) |
| Heart: rare categories (`restecg = 1` has 4 patients, `thal = 6` has 18) | Missed |
| Cardio: 53 cholesterol readings of 0 that are really missing | Visible only: `null_count = 0`, but `min = 0` |
| Cardio: undocumented `slope = 0` (180 rows) | Visible only: appears as `min = 0`, with no count |
| Cardio: all missing cholesterol values belong to `target = 1` patients | Missed |

Most misses have the same cause. The agent counts how often each value occurs only for text columns, but almost every categorical column in these datasets is stored as a number. As a result, rare and undocumented codes never show up. The agent also treats only empty cells as missing, so zeros used as placeholders go unnoticed.

**Relationships.** `possible_relationships` matches only columns with identical names. It finds `age`, `oldpeak` and `slope`, but misses the other 11 pairs whose names differ, such as `sex`/`gender`, `trestbps`/`restingBP` and `thalach`/`maxheartrate`. Matched columns may also be coded differently: chest pain is coded 1–4 in heart and 0–3 in cardio, and cardio `slope` has the extra code 0.

## Semantic agent

**Accuracy.** It got the meaning right for 27 of 31 columns, and no description was completely wrong. Every unit it stated matches the dictionaries. The four partially correct columns each show a different kind of error:

| Column | Agent said | Data dictionary | Error type |
|---|---|---|---|
| heart `thal` | "Thalassemia result" (codes correct) | Thallium stress test result | Prior knowledge applied wrongly |
| heart `num` | Vessel count 0–3 *or* disease score | 0 = no disease, 1–4 = disease present | Confused with a neighbouring column (`ca`) |
| cardio `slope` | 0 = upsloping … 3 = unknown | 0 = undocumented, 1 = upsloping, 2 = flat, 3 = downsloping | Correct labels assigned to the wrong codes |
| cardio `noofmajorvessels` | Vessels "with significant narrowing" | Number of major vessels | Unsupported detail stated as fact, and not flagged |

**Where its knowledge comes from.** For heart columns, the agent stated value meanings such as `cp`: 1 = typical angina … 4 = asymptomatic with no hedging. Its evidence was only the column name and value range, which cannot reveal what each code means. The meanings are correct because the model recognises the well-known UCI Heart Disease dataset. On cardio, where the same concepts have different column names, it flagged 7 of 15 columns as uncertain, compared with 3 of 16 on heart. It also added details that neither dataset supports, such as "measured at admission" for cardio blood pressure. Its accuracy on these datasets is therefore partly memory, and it would likely be lower on a less familiar dataset.

**Inconsistent output.** The `semantic_type` field has no fixed set of values. In the heart output it holds measurement types such as `binary_categorical`; in the cardio output from the same run, it mostly holds domain labels such as `vital_sign` and `demographic`. Code that consumes this field cannot rely on it.

**Information it cannot see.** Both agents read the cleaned CSVs, so they cannot know about cleaning steps: that cholesterol zeros were converted to missing values, or that heart `disease` was derived from `num > 0`. The human profiles record both.

## Limitations

- **One LLM run.** The semantic agent does not fix its randomness, so another run could give different answers. Each live run of `run_pipeline.py` is saved under a new test number, so runs can be compared.
- **One reviewer.** The meaning verdicts (`MANUAL_REVIEW` in `agents/agent_integration.py`) are one person's judgment. They apply to `test_001` only.
- **Uncertain references.** The human profiles themselves are unsure about a few columns, such as the unit of `oldpeak` and the meaning of cardio `slope = 0`.
- **Heuristic parsing.** Value codes are read from free text. One label equivalence (`cholesterol_missing`) is set by hand.
- **Two datasets.** Both follow the UCI heart-disease format, which makes them easier for the semantic agent than an unfamiliar dataset would be.

## Suggested improvements

1. **Metadata agent:** count values for every column with few distinct values, whatever its data type, and report zeros and other placeholder values.
2. **Semantic agent:** limit `semantic_type` to a fixed list, return value codes as a structured `{code: label}` field, and flag any meaning inferred from the column name alone.
3. **Both agents:** pass each dataset's cleaning notes or data dictionary to the semantic agent as context.
