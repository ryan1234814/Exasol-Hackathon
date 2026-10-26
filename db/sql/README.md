# Saved demo queries

Ten single-statement SQL files. Each one answers a question a ward officer would
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
| `forecast_eta.sql` | How long until this ward breaches its limit? | The ETA arithmetic in full — the same CASE the forecast card explains, over `V_WARD_FORECAST` |
| `sensor_vs_lab.sql` | Which breaches are my instruments, not my water? | The `lab_confirmed` / `instrument_suspect` verdict, beside contamination complaint volume |
| `ward_month_matrix.sql` | What does a year of this city look like at a glance? | The 600-cell month × ward matrix the heatmap and the replay slider read |
| `morning_brief.sql` | What are the three things to do today? | The ranked ward with all four risk components and its complaint rollup — the brief's inputs |

`backend/tests/test_sql_snapshots.py` runs all ten against a live database and
asserts each returns rows — a query that quietly returns nothing is a broken
demo, not a clean result.
