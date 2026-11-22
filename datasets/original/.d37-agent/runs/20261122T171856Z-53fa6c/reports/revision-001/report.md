# D37 investigation — 20261122T171856Z-53fa6c

Generated from saved evidence only. No cloud reasoning or generated code was executed during reporting.

## Inventory and coverage

Sources: 2; components: 2.

| Component ID | Kind | Sources | Status | Coverage |
|---|---|---|---|---|
| `6820cb45…` | table | Cardiovascular_Disease_Dataset.csv | complete | full: 1000/1000 rows |
| `ac2c1978…` | table | heart_disease.csv | complete | full: 303/303 rows |

## Measurements and evidence

### Component `6820cb45…`

**Method:** `table_profile_v2`. **Status:** complete.

**Coverage:** ```json
{
  "examined": 1000,
  "mode": "full",
  "seed": null,
  "selection": "All data rows",
  "total": 1000,
  "unit": "rows"
}
```

**Measured facts:**

```json
{
  "column_count": 14,
  "columns": {
    "age": {
      "candidate_key": false,
      "distinct_count": 61,
      "dtype": "int64",
      "max": 80.0,
      "mean": 49.242,
      "median": 49.0,
      "min": 20.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 17.864730185048543,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "chestpain": {
      "candidate_key": false,
      "distinct_count": 4,
      "dtype": "int64",
      "max": 3.0,
      "mean": 0.98,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.9531571268728511,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 420,
            "value": 0
          },
          {
            "count": 312,
            "value": 2
          },
          {
            "count": 224,
            "value": 1
          },
          {
            "count": 44,
            "value": 3
          }
        ]
      }
    },
    "exerciseangia": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.498,
      "median": 0.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.5002461856388775,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 502,
            "value": 0
          },
          {
            "count": 498,
            "value": 1
          }
        ]
      }
    },
    "fastingbloodsugar": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.296,
      "median": 0.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.45671938057476014,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 704,
            "value": 0
          },
          {
            "count": 296,
            "value": 1
          }
        ]
      }
    },
    "gender": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.765,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.4242109792956271,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 765,
            "value": 1
          },
          {
            "count": 235,
            "value": 0
          }
        ]
      }
    },
    "maxheartrate": {
      "candidate_key": false,
      "distinct_count": 129,
      "dtype": "int64",
      "max": 202.0,
      "mean": 145.477,
      "median": 146.0,
      "min": 71.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 34.190268285660544,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "noofmajorvessels": {
      "candidate_key": false,
      "distinct_count": 4,
      "dtype": "int64",
      "max": 3.0,
      "mean": 1.222,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.9775846110039129,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 344,
            "value": 1
          },
          {
            "count": 275,
            "value": 0
          },
          {
            "count": 265,
            "value": 2
          },
          {
            "count": 116,
            "value": 3
          }
        ]
      }
    },
    "oldpeak": {
      "candidate_key": false,
      "distinct_count": 63,
      "dtype": "float64",
      "max": 6.2,
      "mean": 2.7077,
      "median": 2.4,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 1.720753236725621,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "patientid": {
      "candidate_key": true,
      "distinct_count": 1000,
      "dtype": "int64",
      "max": 9990855.0,
      "mean": 5048704.412,
      "median": 4952508.5,
      "min": 103368.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 2895904.5004878514,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "restingBP": {
      "candidate_key": false,
      "distinct_count": 95,
      "dtype": "int64",
      "max": 200.0,
      "mean": 151.747,
      "median": 147.0,
      "min": 94.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 29.965228280557213,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "restingrelectro": {
      "candidate_key": false,
      "distinct_count": 3,
      "dtype": "int64",
      "max": 2.0,
      "mean": 0.748,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.7701227753346146,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 454,
            "value": 0
          },
          {
            "count": 344,
            "value": 1
          },
          {
            "count": 202,
            "value": 2
          }
        ]
      }
    },
    "serumcholestrol": {
      "candidate_key": false,
      "distinct_count": 344,
      "dtype": "int64",
      "max": 602.0,
      "mean": 311.447,
      "median": 318.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 132.44380148406927,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "slope": {
      "candidate_key": false,
      "distinct_count": 4,
      "dtype": "int64",
      "max": 3.0,
      "mean": 1.54,
      "median": 2.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 1.0036968702787747,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 322,
            "value": 2
          },
          {
            "count": 299,
            "value": 1
          },
          {
            "count": 199,
            "value": 3
          },
          {
            "count": 180,
            "value": 0
          }
        ]
      }
    },
    "target": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.58,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.49380547166252003,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 580,
            "value": 1
          },
          {
            "count": 420,
            "value": 0
          }
        ]
      }
    }
  },
  "duplicate_row_count": 0,
  "profile_scope": "full",
  "row_count": 1000
}
```

**Saved artifacts** (paths relative to run directory):

- `artifacts/tool-48a0c8021069bc54/attempt-001/tables/e6c0e478a627c9cd/profile/missing_values.png` (image/png)
- `artifacts/tool-48a0c8021069bc54/attempt-001/tables/e6c0e478a627c9cd/profile/numeric_distributions.png` (image/png)

**Assembled metadata (not independently remeasured):**

```json
{
  "component_id": "component_6820cb4505cf327a65423a24d654640e66096b48f9291af74bdb0156372f31af",
  "result_count": 1,
  "results": [
    {
      "artifacts": [
        {
          "artifact_id": "table_plot_e6c0e478a627c9cd_0",
          "media_type": "image/png",
          "relative_path": "artifacts/tool-48a0c8021069bc54/attempt-001/tables/e6c0e478a627c9cd/profile/missing_values.png"
        },
        {
          "artifact_id": "table_plot_e6c0e478a627c9cd_1",
          "media_type": "image/png",
          "relative_path": "artifacts/tool-48a0c8021069bc54/attempt-001/tables/e6c0e478a627c9cd/profile/numeric_distributions.png"
        }
      ],
      "component_id": "component_6820cb4505cf327a65423a24d654640e66096b48f9291af74bdb0156372f31af",
      "coverage": {
        "examined": 1000,
        "mode": "full",
        "seed": null,
        "selection": "All data rows",
        "total": 1000,
        "unit": "rows"
      },
      "inputs": [
        "source_95974f73a3179f4d052c001d94cb0a7fb6425852476ba4889fe384db9cec48e8"
      ],
      "limitations": [],
      "measurements": {
        "column_count": 14,
        "columns": {
          "age": {
            "candidate_key": false,
            "distinct_count": 61,
            "dtype": "int64",
            "max": 80.0,
            "mean": 49.242,
            "median": 49.0,
            "min": 20.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 17.864730185048543,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "chestpain": {
            "candidate_key": false,
            "distinct_count": 4,
            "dtype": "int64",
            "max": 3.0,
            "mean": 0.98,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.9531571268728511,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 420,
                  "value": 0
                },
                {
                  "count": 312,
                  "value": 2
                },
                {
                  "count": 224,
                  "value": 1
                },
                {
                  "count": 44,
                  "value": 3
                }
              ]
            }
          },
          "exerciseangia": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.498,
            "median": 0.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.5002461856388775,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 502,
                  "value": 0
                },
                {
                  "count": 498,
                  "value": 1
                }
              ]
            }
          },
          "fastingbloodsugar": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.296,
            "median": 0.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.45671938057476014,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 704,
                  "value": 0
                },
                {
                  "count": 296,
                  "value": 1
                }
              ]
            }
          },
          "gender": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.765,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.4242109792956271,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 765,
                  "value": 1
                },
                {
                  "count": 235,
                  "value": 0
                }
              ]
            }
          },
          "maxheartrate": {
            "candidate_key": false,
            "distinct_count": 129,
            "dtype": "int64",
            "max": 202.0,
            "mean": 145.477,
            "median": 146.0,
            "min": 71.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 34.190268285660544,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "noofmajorvessels": {
            "candidate_key": false,
            "distinct_count": 4,
            "dtype": "int64",
            "max": 3.0,
            "mean": 1.222,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.9775846110039129,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 344,
                  "value": 1
                },
                {
                  "count": 275,
                  "value": 0
                },
                {
                  "count": 265,
                  "value": 2
                },
                {
                  "count": 116,
                  "value": 3
                }
              ]
            }
          },
          "oldpeak": {
            "candidate_key": false,
            "distinct_count": 63,
            "dtype": "float64",
            "max": 6.2,
            "mean": 2.7077,
            "median": 2.4,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 1.720753236725621,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "patientid": {
            "candidate_key": true,
            "distinct_count": 1000,
            "dtype": "int64",
            "max": 9990855.0,
            "mean": 5048704.412,
            "median": 4952508.5,
            "min": 103368.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 2895904.5004878514,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "restingBP": {
            "candidate_key": false,
            "distinct_count": 95,
            "dtype": "int64",
            "max": 200.0,
            "mean": 151.747,
            "median": 147.0,
            "min": 94.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 29.965228280557213,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "restingrelectro": {
            "candidate_key": false,
            "distinct_count": 3,
            "dtype": "int64",
            "max": 2.0,
            "mean": 0.748,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.7701227753346146,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 454,
                  "value": 0
                },
                {
                  "count": 344,
                  "value": 1
                },
                {
                  "count": 202,
                  "value": 2
                }
              ]
            }
          },
          "serumcholestrol": {
            "candidate_key": false,
            "distinct_count": 344,
            "dtype": "int64",
            "max": 602.0,
            "mean": 311.447,
            "median": 318.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 132.44380148406927,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "slope": {
            "candidate_key": false,
            "distinct_count": 4,
            "dtype": "int64",
            "max": 3.0,
            "mean": 1.54,
            "median": 2.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 1.0036968702787747,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 322,
                  "value": 2
                },
                {
                  "count": 299,
                  "value": 1
                },
                {
                  "count": 199,
                  "value": 3
                },
                {
                  "count": 180,
                  "value": 0
                }
              ]
            }
          },
          "target": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.58,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.49380547166252003,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 580,
                  "value": 1
                },
                {
                  "count": 420,
                  "value": 0
                }
              ]
            }
          }
        },
        "duplicate_row_count": 0,
        "profile_scope": "full",
        "row_count": 1000
      },
      "method": "table_profile_v2",
      "parameters": {
        "format": "csv",
        "max_source_bytes": 26214400,
        "sampling": "none"
      },
      "result_id": "r-tool-48a0c8021069bc54",
      "schema_version": "1.0",
      "status": "complete"
    }
  ],
  "schema_version": "1.0",
  "source_ids": [
    "source_95974f73a3179f4d052c001d94cb0a7fb6425852476ba4889fe384db9cec48e8"
  ]
}
```

#### Coded columns in Cardiovascular\_Disease\_Dataset.csv

Profiled 1000 of 1000 rows.

**gender**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column gender)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 1 | 765 | No definition found | Needs verification (unresolved) |
| 0 | 235 | No definition found | Needs verification (unresolved) |

**chestpain**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column chestpain)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 420 | No definition found | Needs verification (unresolved) |
| 2 | 312 | No definition found | Needs verification (unresolved) |
| 1 | 224 | No definition found | Needs verification (unresolved) |
| 3 | 44 | No definition found | Needs verification (unresolved) |

**fastingbloodsugar**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column fastingbloodsugar)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 704 | No definition found | Needs verification (unresolved) |
| 1 | 296 | No definition found | Needs verification (unresolved) |

**restingrelectro**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column restingrelectro)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 454 | No definition found | Needs verification (unresolved) |
| 1 | 344 | No definition found | Needs verification (unresolved) |
| 2 | 202 | No definition found | Needs verification (unresolved) |

**exerciseangia**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column exerciseangia)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 502 | No definition found | Needs verification (unresolved) |
| 1 | 498 | No definition found | Needs verification (unresolved) |

**slope**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column slope)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 2 | 322 | No definition found | Needs verification (unresolved) |
| 1 | 299 | No definition found | Needs verification (unresolved) |
| 3 | 199 | No definition found | Needs verification (unresolved) |
| 0 | 180 | No definition found | Needs verification (unresolved) |

**noofmajorvessels**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column noofmajorvessels)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 1 | 344 | No definition found | Needs verification (unresolved) |
| 0 | 275 | No definition found | Needs verification (unresolved) |
| 2 | 265 | No definition found | Needs verification (unresolved) |
| 3 | 116 | No definition found | Needs verification (unresolved) |

**target**

Observed counts and 0 missing values. Evidence from [Cardiovascular\_Disease\_Dataset.csv (column target)](../../results/tool-48a0c8021069bc54/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 1 | 580 | No definition found | Needs verification (unresolved) |
| 0 | 420 | No definition found | Needs verification (unresolved) |

**Needs verification** for **gender**. No dictionary entry links to this column.

**Needs verification** for **chestpain**. No dictionary entry links to this column.

**Needs verification** for **fastingbloodsugar**. No dictionary entry links to this column.

**Needs verification** for **restingrelectro**. No dictionary entry links to this column.

**Needs verification** for **exerciseangia**. No dictionary entry links to this column.

**Needs verification** for **slope**. No dictionary entry links to this column.

**Needs verification** for **noofmajorvessels**. No dictionary entry links to this column.

**Needs verification** for **target**. No dictionary entry links to this column.

Optional model interpretation failed. Model interpretation failed (TimeoutError).

### Component `ac2c1978…`

**Method:** `table_profile_v2`. **Status:** complete.

**Coverage:** ```json
{
  "examined": 303,
  "mode": "full",
  "seed": null,
  "selection": "All data rows",
  "total": 303,
  "unit": "rows"
}
```

**Measured facts:**

```json
{
  "column_count": 15,
  "columns": {
    "age": {
      "candidate_key": false,
      "distinct_count": 41,
      "dtype": "int64",
      "max": 77.0,
      "mean": 54.43894389438944,
      "median": 56.0,
      "min": 29.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 9.038662442446746,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "ca": {
      "candidate_key": false,
      "distinct_count": 4,
      "dtype": "float64",
      "max": 3.0,
      "mean": 0.6722408026755853,
      "median": 0.0,
      "min": 0.0,
      "null_count": 4,
      "null_percentage": 1.3201320132013201,
      "std": 0.9374383177242163,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 176,
            "value": 0.0
          },
          {
            "count": 65,
            "value": 1.0
          },
          {
            "count": 38,
            "value": 2.0
          },
          {
            "count": 20,
            "value": 3.0
          }
        ]
      }
    },
    "chol": {
      "candidate_key": false,
      "distinct_count": 152,
      "dtype": "int64",
      "max": 564.0,
      "mean": 246.69306930693068,
      "median": 241.0,
      "min": 126.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 51.77691754263704,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "cp": {
      "candidate_key": false,
      "distinct_count": 4,
      "dtype": "int64",
      "max": 4.0,
      "mean": 3.1584158415841586,
      "median": 3.0,
      "min": 1.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.9601256119600138,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 144,
            "value": 4
          },
          {
            "count": 86,
            "value": 3
          },
          {
            "count": 50,
            "value": 2
          },
          {
            "count": 23,
            "value": 1
          }
        ]
      }
    },
    "exang": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.32673267326732675,
      "median": 0.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.46979446452231655,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 204,
            "value": 0
          },
          {
            "count": 99,
            "value": 1
          }
        ]
      }
    },
    "fbs": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.1485148514851485,
      "median": 0.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.35619787492797644,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 258,
            "value": 0
          },
          {
            "count": 45,
            "value": 1
          }
        ]
      }
    },
    "num": {
      "candidate_key": false,
      "distinct_count": 5,
      "dtype": "int64",
      "max": 4.0,
      "mean": 0.9372937293729373,
      "median": 0.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 1.2285356879701044,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 164,
            "value": 0
          },
          {
            "count": 55,
            "value": 1
          },
          {
            "count": 36,
            "value": 2
          },
          {
            "count": 35,
            "value": 3
          },
          {
            "count": 13,
            "value": 4
          }
        ]
      }
    },
    "oldpeak": {
      "candidate_key": false,
      "distinct_count": 40,
      "dtype": "float64",
      "max": 6.2,
      "mean": 1.0396039603960396,
      "median": 0.8,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 1.1610750220686348,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "patient_id": {
      "candidate_key": true,
      "distinct_count": 303,
      "dtype": "int64",
      "max": 302.0,
      "mean": 151.0,
      "median": 151.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 87.61278445523804,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "restecg": {
      "candidate_key": false,
      "distinct_count": 3,
      "dtype": "int64",
      "max": 2.0,
      "mean": 0.9900990099009901,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.9949712915251782,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 151,
            "value": 0
          },
          {
            "count": 148,
            "value": 2
          },
          {
            "count": 4,
            "value": 1
          }
        ]
      }
    },
    "sex": {
      "candidate_key": false,
      "distinct_count": 2,
      "dtype": "int64",
      "max": 1.0,
      "mean": 0.6798679867986799,
      "median": 1.0,
      "min": 0.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.46729882777012993,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 206,
            "value": 1
          },
          {
            "count": 97,
            "value": 0
          }
        ]
      }
    },
    "slope": {
      "candidate_key": false,
      "distinct_count": 3,
      "dtype": "int64",
      "max": 3.0,
      "mean": 1.6006600660066006,
      "median": 2.0,
      "min": 1.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 0.6162261453459619,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 142,
            "value": 1
          },
          {
            "count": 140,
            "value": 2
          },
          {
            "count": 21,
            "value": 3
          }
        ]
      }
    },
    "thal": {
      "candidate_key": false,
      "distinct_count": 3,
      "dtype": "float64",
      "max": 7.0,
      "mean": 4.73421926910299,
      "median": 3.0,
      "min": 3.0,
      "null_count": 2,
      "null_percentage": 0.6600660066006601,
      "std": 1.939705769378644,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": false,
        "values": [
          {
            "count": 166,
            "value": 3.0
          },
          {
            "count": 117,
            "value": 7.0
          },
          {
            "count": 18,
            "value": 6.0
          }
        ]
      }
    },
    "thalach": {
      "candidate_key": false,
      "distinct_count": 91,
      "dtype": "int64",
      "max": 202.0,
      "mean": 149.6072607260726,
      "median": 153.0,
      "min": 71.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 22.875003276980376,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    },
    "trestbps": {
      "candidate_key": false,
      "distinct_count": 50,
      "dtype": "int64",
      "max": 200.0,
      "mean": 131.68976897689768,
      "median": 130.0,
      "min": 94.0,
      "null_count": 0,
      "null_percentage": 0.0,
      "std": 17.59974772958769,
      "value_frequencies": {
        "max_distinct": 20,
        "numeric": true,
        "sampled": false,
        "truncated": true,
        "values": []
      }
    }
  },
  "duplicate_row_count": 0,
  "profile_scope": "full",
  "row_count": 303
}
```

**Saved artifacts** (paths relative to run directory):

- `artifacts/tool-78a58871dee88408/attempt-001/tables/ae77b16c5872a209/profile/missing_values.png` (image/png)
- `artifacts/tool-78a58871dee88408/attempt-001/tables/ae77b16c5872a209/profile/numeric_distributions.png` (image/png)

**Assembled metadata (not independently remeasured):**

```json
{
  "component_id": "component_ac2c19784483e689c5a5d136a6a334511466a5d1495a7d5b614d266e4ca2ce4c",
  "result_count": 1,
  "results": [
    {
      "artifacts": [
        {
          "artifact_id": "table_plot_ae77b16c5872a209_0",
          "media_type": "image/png",
          "relative_path": "artifacts/tool-78a58871dee88408/attempt-001/tables/ae77b16c5872a209/profile/missing_values.png"
        },
        {
          "artifact_id": "table_plot_ae77b16c5872a209_1",
          "media_type": "image/png",
          "relative_path": "artifacts/tool-78a58871dee88408/attempt-001/tables/ae77b16c5872a209/profile/numeric_distributions.png"
        }
      ],
      "component_id": "component_ac2c19784483e689c5a5d136a6a334511466a5d1495a7d5b614d266e4ca2ce4c",
      "coverage": {
        "examined": 303,
        "mode": "full",
        "seed": null,
        "selection": "All data rows",
        "total": 303,
        "unit": "rows"
      },
      "inputs": [
        "source_1ef6549ed7bef167e124f057ee14ebb4650b72aaaef58aeafdc3a703787113ce"
      ],
      "limitations": [],
      "measurements": {
        "column_count": 15,
        "columns": {
          "age": {
            "candidate_key": false,
            "distinct_count": 41,
            "dtype": "int64",
            "max": 77.0,
            "mean": 54.43894389438944,
            "median": 56.0,
            "min": 29.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 9.038662442446746,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "ca": {
            "candidate_key": false,
            "distinct_count": 4,
            "dtype": "float64",
            "max": 3.0,
            "mean": 0.6722408026755853,
            "median": 0.0,
            "min": 0.0,
            "null_count": 4,
            "null_percentage": 1.3201320132013201,
            "std": 0.9374383177242163,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 176,
                  "value": 0.0
                },
                {
                  "count": 65,
                  "value": 1.0
                },
                {
                  "count": 38,
                  "value": 2.0
                },
                {
                  "count": 20,
                  "value": 3.0
                }
              ]
            }
          },
          "chol": {
            "candidate_key": false,
            "distinct_count": 152,
            "dtype": "int64",
            "max": 564.0,
            "mean": 246.69306930693068,
            "median": 241.0,
            "min": 126.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 51.77691754263704,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "cp": {
            "candidate_key": false,
            "distinct_count": 4,
            "dtype": "int64",
            "max": 4.0,
            "mean": 3.1584158415841586,
            "median": 3.0,
            "min": 1.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.9601256119600138,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 144,
                  "value": 4
                },
                {
                  "count": 86,
                  "value": 3
                },
                {
                  "count": 50,
                  "value": 2
                },
                {
                  "count": 23,
                  "value": 1
                }
              ]
            }
          },
          "exang": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.32673267326732675,
            "median": 0.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.46979446452231655,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 204,
                  "value": 0
                },
                {
                  "count": 99,
                  "value": 1
                }
              ]
            }
          },
          "fbs": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.1485148514851485,
            "median": 0.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.35619787492797644,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 258,
                  "value": 0
                },
                {
                  "count": 45,
                  "value": 1
                }
              ]
            }
          },
          "num": {
            "candidate_key": false,
            "distinct_count": 5,
            "dtype": "int64",
            "max": 4.0,
            "mean": 0.9372937293729373,
            "median": 0.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 1.2285356879701044,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 164,
                  "value": 0
                },
                {
                  "count": 55,
                  "value": 1
                },
                {
                  "count": 36,
                  "value": 2
                },
                {
                  "count": 35,
                  "value": 3
                },
                {
                  "count": 13,
                  "value": 4
                }
              ]
            }
          },
          "oldpeak": {
            "candidate_key": false,
            "distinct_count": 40,
            "dtype": "float64",
            "max": 6.2,
            "mean": 1.0396039603960396,
            "median": 0.8,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 1.1610750220686348,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "patient_id": {
            "candidate_key": true,
            "distinct_count": 303,
            "dtype": "int64",
            "max": 302.0,
            "mean": 151.0,
            "median": 151.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 87.61278445523804,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "restecg": {
            "candidate_key": false,
            "distinct_count": 3,
            "dtype": "int64",
            "max": 2.0,
            "mean": 0.9900990099009901,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.9949712915251782,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 151,
                  "value": 0
                },
                {
                  "count": 148,
                  "value": 2
                },
                {
                  "count": 4,
                  "value": 1
                }
              ]
            }
          },
          "sex": {
            "candidate_key": false,
            "distinct_count": 2,
            "dtype": "int64",
            "max": 1.0,
            "mean": 0.6798679867986799,
            "median": 1.0,
            "min": 0.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.46729882777012993,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 206,
                  "value": 1
                },
                {
                  "count": 97,
                  "value": 0
                }
              ]
            }
          },
          "slope": {
            "candidate_key": false,
            "distinct_count": 3,
            "dtype": "int64",
            "max": 3.0,
            "mean": 1.6006600660066006,
            "median": 2.0,
            "min": 1.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 0.6162261453459619,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 142,
                  "value": 1
                },
                {
                  "count": 140,
                  "value": 2
                },
                {
                  "count": 21,
                  "value": 3
                }
              ]
            }
          },
          "thal": {
            "candidate_key": false,
            "distinct_count": 3,
            "dtype": "float64",
            "max": 7.0,
            "mean": 4.73421926910299,
            "median": 3.0,
            "min": 3.0,
            "null_count": 2,
            "null_percentage": 0.6600660066006601,
            "std": 1.939705769378644,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": false,
              "values": [
                {
                  "count": 166,
                  "value": 3.0
                },
                {
                  "count": 117,
                  "value": 7.0
                },
                {
                  "count": 18,
                  "value": 6.0
                }
              ]
            }
          },
          "thalach": {
            "candidate_key": false,
            "distinct_count": 91,
            "dtype": "int64",
            "max": 202.0,
            "mean": 149.6072607260726,
            "median": 153.0,
            "min": 71.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 22.875003276980376,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          },
          "trestbps": {
            "candidate_key": false,
            "distinct_count": 50,
            "dtype": "int64",
            "max": 200.0,
            "mean": 131.68976897689768,
            "median": 130.0,
            "min": 94.0,
            "null_count": 0,
            "null_percentage": 0.0,
            "std": 17.59974772958769,
            "value_frequencies": {
              "max_distinct": 20,
              "numeric": true,
              "sampled": false,
              "truncated": true,
              "values": []
            }
          }
        },
        "duplicate_row_count": 0,
        "profile_scope": "full",
        "row_count": 303
      },
      "method": "table_profile_v2",
      "parameters": {
        "format": "csv",
        "max_source_bytes": 26214400,
        "sampling": "none"
      },
      "result_id": "r-tool-78a58871dee88408",
      "schema_version": "1.0",
      "status": "complete"
    }
  ],
  "schema_version": "1.0",
  "source_ids": [
    "source_1ef6549ed7bef167e124f057ee14ebb4650b72aaaef58aeafdc3a703787113ce"
  ]
}
```

#### Coded columns in heart\_disease.csv

Profiled 303 of 303 rows.

**sex**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column sex)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 1 | 206 | No definition found | Needs verification (unresolved) |
| 0 | 97 | No definition found | Needs verification (unresolved) |

**cp**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column cp)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 4 | 144 | No definition found | Needs verification (unresolved) |
| 3 | 86 | No definition found | Needs verification (unresolved) |
| 2 | 50 | No definition found | Needs verification (unresolved) |
| 1 | 23 | No definition found | Needs verification (unresolved) |

**fbs**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column fbs)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 258 | No definition found | Needs verification (unresolved) |
| 1 | 45 | No definition found | Needs verification (unresolved) |

**restecg**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column restecg)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 151 | No definition found | Needs verification (unresolved) |
| 2 | 148 | No definition found | Needs verification (unresolved) |
| 1 | 4 | No definition found | Needs verification (unresolved) |

**exang**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column exang)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 204 | No definition found | Needs verification (unresolved) |
| 1 | 99 | No definition found | Needs verification (unresolved) |

**slope**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column slope)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 1 | 142 | No definition found | Needs verification (unresolved) |
| 2 | 140 | No definition found | Needs verification (unresolved) |
| 3 | 21 | No definition found | Needs verification (unresolved) |

**ca**

Observed counts and 4 missing values. Evidence from [heart\_disease.csv (column ca)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0.0 | 176 | No definition found | Needs verification (unresolved) |
| 1.0 | 65 | No definition found | Needs verification (unresolved) |
| 2.0 | 38 | No definition found | Needs verification (unresolved) |
| 3.0 | 20 | No definition found | Needs verification (unresolved) |

**thal**

Observed counts and 2 missing values. Evidence from [heart\_disease.csv (column thal)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 3.0 | 166 | No definition found | Needs verification (unresolved) |
| 7.0 | 117 | No definition found | Needs verification (unresolved) |
| 6.0 | 18 | No definition found | Needs verification (unresolved) |

**num**

Observed counts and 0 missing values. Evidence from [heart\_disease.csv (column num)](../../results/tool-78a58871dee88408/v001.json).

| Observed value | Count | Dictionary definitions and citations | Status |
|---|---:|---|---|
| 0 | 164 | No definition found | Needs verification (unresolved) |
| 1 | 55 | No definition found | Needs verification (unresolved) |
| 2 | 36 | No definition found | Needs verification (unresolved) |
| 3 | 35 | No definition found | Needs verification (unresolved) |
| 4 | 13 | No definition found | Needs verification (unresolved) |

**Needs verification** for **sex**. No dictionary entry links to this column.

**Needs verification** for **cp**. No dictionary entry links to this column.

**Needs verification** for **fbs**. No dictionary entry links to this column.

**Needs verification** for **restecg**. No dictionary entry links to this column.

**Needs verification** for **exang**. No dictionary entry links to this column.

**Needs verification** for **slope**. No dictionary entry links to this column.

**Needs verification** for **ca**. No dictionary entry links to this column.

**Needs verification** for **thal**. No dictionary entry links to this column.

**Needs verification** for **num**. No dictionary entry links to this column.

Optional model interpretation failed. Model interpretation failed (TimeoutError).

## Follow-up analyses

No saved follow-up analyses.

## Reproducibility and caveats

- Tool measurements are quoted from validated saved ToolResult records; sampled measurements are not full-dataset claims.
- Saved interpretations are labeled as model interpretations, not verified measurements.
- The companion marimo notebook reads saved run artifacts and redraws supported PNGs without model calls or executing generated analysis code.
- Original data remain untouched. Run input hashes, seeds, environment and provenance are retained in the run manifest/checkpoint when available.
- Extracted text may contain sensitive information; review outputs before sharing.

**Discovery limitations:**

- Discovery is read-only but is not a complete sandbox against concurrent filesystem changes.
- Discovery uses file signatures, extensions, and bounded prefix reads; parsing is handled by downstream tools.
- Filename exclusions cannot detect arbitrary secrets stored inside otherwise eligible files.
- Format labels are candidates, not validated file contents.
- Hidden entries, common credential names, caches, generated output directories, and symlinks are excluded.
- No Excel sheets, image pixels, document contents, or collection associations are inspected.
- ZIP-based Office formats are identified by internal filenames, not by validating workbook or document content.

