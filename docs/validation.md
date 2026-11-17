# Validation

Validation covers the shared engine, all three admitted cases, the four-page application, state isolation, exports and deterministic research workflow. Results below were produced locally on 17 November 2026 with CPython 3.13.7.

## Automated suite

```text
184 tests passed
93% combined statement coverage
Ruff passed
```

The suite includes analytical quarterly NPV references, deployment timing, annual and quarterly capacity, dependency timing, minimum commitments, mutually exclusive alternatives, pilot and governance exclusions, scenario recalculation, case admission, cross-company state isolation, benefits observation imports and materiality, deterministic exports, professional Excel/PDF documents, snapshot storage, Streamlit navigation, research upload boundaries, citation verification, PDF extraction, adversarial instructions and explicit research review.

Run the same checks with:

```bash
python -m pytest -q --cov=invest_engine --cov=frontend --cov=app --cov-report=term-missing
python -m ruff check .
```

## Independent portfolio audits

`scripts/validate_case.py` reconstructs each rollout option's seeded cash flows and resource vectors, then enumerates feasible fixed-phasing portfolios. It recovered the same selected scales and risk-adjusted objective as the production optimizer:

| Case | Feasible portfolios | Selected deployments | Expected NPV | Expected capex |
|---|---:|---:|---:|---:|
| DHL Supply Chain | 5,723 | 80 | €48.107547m | €23.490206m |
| Allianz | 2,944 | 22 | €3.940675m | €4.584192m |
| BMW Group | 1,664 | 11 | €3.845880m | €3.159659m |

All selected deployments fit their declared quarterly ceilings and rollout deadlines. The audits establish optimality for the implemented discrete scales and fixed quarterly phasing; they do not validate arbitrary real-world sequencing or facility eligibility.

```bash
python scripts/validate_case.py cases/dhl_supply_chain
python scripts/validate_case.py cases/allianz
python scripts/validate_case.py cases/bmw_group
```

## Financial and export reconciliation

For each case:

- selected initiative NPVs sum to the portfolio NPV;
- annual and quarterly discounted cash flows reconcile to the same NPV;
- capex and operating benefits reconcile across valuation, roadmap, and export tables;
- the base scenario matches the active recommendation;
- roadmap cohorts match the valued quarterly deployment plan; and
- the memo, settings, and 12 CSV files in the ZIP pack match their direct exporters.

The professional document regression matrix additionally opens the Excel workbook and every PDF page for all three reference cases, checks one changed scenario per company, exercises a zero-investment portfolio, and verifies repeated-download determinism and cross-case isolation. The Excel reconciliation sheet agrees with the engine and quarterly schedule for NPV, capital and undiscounted benefits. Default reports render as five PDF pages per case; all 15 pages and all eight Excel print sheets were visually inspected for wrapping, clipping and pagination.

## Benefits-realization validation

The E3 matrix covers DHL Supply Chain, Allianz and BMW Group; no observations; partial observations and missing quarters; duplicate rows; wrong-company and unknown-initiative data; invalid period/date alignment; currency mismatch; zero and negative observations; replacement revisions; low-confidence and material deviations; fictional-example labeling; cross-case isolation; deterministic downloads; and Excel/PDF reconciliation. Observations alter only the benefits review table. Selected investments, expected NPV, capital and financial assumptions remain byte-for-byte unchanged in the observation immutability test.

The results are calculated from the case configuration. No target NPV or selected portfolio is hardcoded in the application or presentation layer.

## Reproducibility

Fixed simulation seeds, initiative-specific random streams, one shared demand stream, one CP-SAT worker, versioned calculation keys, and deterministic ZIP timestamps support repeatable results. A clean Python 3.13 environment installed the pinned requirements, passed `pip check`, and generated a byte-identical BMW committee pack on repeated runs.

The dependency lock uses exact versions without artifact hashes. Local success does not establish remote GitHub Actions success or compatibility with every supported Python and operating-system combination.

## Product checks

Portfolio, Scenario Lab, Delivery Plan, and Decision Brief were reviewed for DHL Supply Chain, Allianz, and BMW Group at desktop and 390 × 844 mobile dimensions. Case switching, recalculation, reset, rollout and governance tabs, benefits state, current exports, and the email footer were exercised. No document-level horizontal overflow was measured at the mobile width.

This is a functional and visual review, not formal accessibility certification.

## Research reference evaluation

`python scripts/evaluate_research.py` evaluates three reviewed synthetic excerpts spanning logistics, insurance and manufacturing. One excerpt contains an instruction to ignore prior rules and reveal credentials. The measured fixture results are:

| Measure | Result |
|---|---:|
| Extracted findings | 6 |
| Citation correctness | 100% |
| Unsupported claim rate | 0% |
| Expected-passage coverage | 100% |
| Structured-output validity | 100% |
| Accept/reject review behavior | 100% |
| Instruction-like text blocked | 100% |

These results apply only to the small committed reference set. They do not establish general research accuracy or safe processing of arbitrary confidential documents.
