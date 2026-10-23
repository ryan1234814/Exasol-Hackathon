# Saved demo queries

Six single-statement SQL files. Each one answers a question a ward officer would
actually ask, and each one is the **same statement** the API runs behind the
scene, so a number on screen can be proven on stage.

They are deliberately free of comments and of a trailing semicolon, because
`exakit sql --file` refuses anything that is not a single read statement — a
leading `--` line is enough to make it reject the file. That is the difference
between a demo query that can be pasted live and one that cannot.

```bash
# the live "show me the SQL" moment, one command
exakit sql --file db/sql/complaint_vs_lab_disagreement.sql

# or through exapump, which prints the raw result
exapump sql -p starter-kit < db/sql/latest_risk.sql
```

| File | Question it answers | What it proves |
|---|---|---|
| `latest_risk.sql` | Which ward do I visit today, and why? | The composite risk score decomposes into the four published components |
| `monsoon_turbidity.sql` | Does the monsoon hit downstream wards harder? | Planted signal 1: downstream turbidity runs materially higher Jul–Sep |
| `outbreak_detection.sql` | Is there an acute contamination event? | Planted signal 3: the ward-12 coliform cluster shows up as consecutive z ≥ 3 days |
| `deteriorating_wards.sql` | Which wards are getting worse slowly? | Planted signal 4: a trend with no spike is still caught, via the 12-month OLS slope |
| `complaint_vs_lab_disagreement.sql` | When should I doubt my own instruments? | Planted signal 5: sensor-only breaches with zero lab-confirmed breaches, side by side with citizen volume |
| `complaint_category_mix.sql` | What are people actually saying about this ward? | The rule-engine categorisation, with one representative quote per category |

`backend/tests/test_sql_snapshots.py` runs all six against a live database and
asserts each returns rows — a query that quietly returns nothing is a broken
demo, not a clean result.
