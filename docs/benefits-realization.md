# Benefits realization

Benefits realization compares operational observations with the matching quarterly plan after an investment has been selected. It is a management review workflow, not a second valuation model. Imported observations do not change investment assumptions, cash flows, NPV, portfolio selection or the implementation schedule.

## CSV template

Download the current template from **Delivery Plan → Benefits**. It contains one row for each selected initiative and reporting quarter. Complete these fields:

| Field | Rule |
|---|---|
| `company_id` | Must equal the active case ID: `dhl_supply_chain`, `allianz` or `bmw_group` |
| `initiative_id` | Must be a registered initiative in that case |
| `quarter` | Whole-number relative reporting quarter, currently 1–6 |
| `reporting_period_end` | ISO date on a calendar quarter end; quarter/date progression must align |
| `observed_benefit_EUR_k` | Finite EUR thousands; zero and negative values are permitted |
| `currency` | Must be `EUR`; no FX conversion is performed |
| `source` | A 3–200 character source description |
| `observation_date` | ISO date on or after period end and not in the future |
| `confidence` | `high`, `medium` or `low` |
| `revision` | Positive whole number identifying the supplied revision |
| `is_simulated` | `true` only for clearly fictional demonstration data; otherwise `false` |

Each file may contain only one row for a company, initiative and reporting quarter. Upload a replacement file to revise an observation; duplicate rows in one file are rejected. The complete accepted file remains in browser session memory and is cleared on company change or when the user selects **Clear observations**. It is not written to the repository or application database.

## Comparison rules

The reporting-period selector limits the review to quarters through the chosen period. Portfolio and initiative comparisons use planned benefit only for rows with a matching observation. Missing rows remain unavailable and reduce observation coverage; they are never converted to zero.

Variance is `observed benefit − planned benefit` for matching periods. Percentage variance is unavailable when the matching plan is zero. A quarterly observation is material when absolute variance is at least €50k and percentage variance is at least 20%; when plan is zero, the €50k absolute threshold applies. An initiative requires follow-up when any reported quarter is material. The interface also identifies missing periods and low-confidence measurements.

Observed benefit is an operational measurement, not investment cash flow or proof of causation. Managers should validate the baseline, benefit definition, source, confounding changes and attribution evidence before acting on a variance.
