# Problem statement

**WARDQ — Ward-Level Water Quality & Complaint Triage** · ExaThon India 2026, Civic / Sustainability

The one-page argument. The long version is in the [README](../README.md); the slide
version is [slide 2 of the pitch deck](../pitch-deck/WARDQ-Pitch-Deck.pdf).

---

## Who has the problem

**The ward health officer.** She holds 15,063 citizen complaints but not the
instruments. Her morning list is ordered by who complained loudest, because that is
the only thing that arrives with a number attached. There is no dated forecast to
rank against, so she cannot tell a bad week from a bad ward.

**The water utility engineer.** Probe alarms and lab confirmations live in two
registers that never meet. Ward 51 Indiranagar shows **22 pH probe breaches and zero
lab confirmations**; Ward 3 Powai shows 11 probe and 40 lab-confirmed breaches. He
cannot tell a fouled electrode from contaminated water, so the safe habit becomes
discounting every alarm — including the one that matters.

**1,002,700 residents** across 24 wards and 224,230 connections. **9 of the 24 wards
sit downstream of the intake**: they pay for contamination they did not produce, and
their first real warning is the clinic queue.

## Why it matters

A water supply emits three signals on three clocks:

| Signal | Arrives | What it means |
|---|---|---|
| The probe | hours | Turbidity doubles at 11 pm; chlorine decays below 0.2 mg/L |
| The lab | 7–14 days | Coliform plates need incubation and a technician |
| The clinic | weeks | Diarrhoeal cases appear in PHC registers |

Almost every municipal dashboard reports the **last** one, because it is the only one
with a count already attached. By the time illness confirms the failure, the exposure
window has closed and the only remaining action is *response*, not *prevention*.

Between the probe and the clinic there are roughly **three weeks** in which a flushing
order, a chlorine correction or a probe calibration still changes the outcome. Nothing
in the municipal stack is built to act inside that window. **That window is the
product.**

## What the gap looks like on real data

| Measure | Value |
|---|---|
| Residents served by the 24 wards | **1,002,700** |
| Ward × parameter pairs already past their limit | **24 of 96** |
| Notice available before the next crossing (Ward 191, turbidity) | **26 days** |
| Crossings that appear in an illness report yet | **0** |
| Readings usable for a monthly mean | **97.01%** (253 of 8,448 cells have no result) |

## What WARDQ does instead

It computes the risk from the instruments first, corroborates it with the citizens
second, and dates the forecast:

> `Ward 191 · Turbidity 4.695 NTU · +0.0118/day · crosses the 5 NTU limit in 26 days`

Three design commitments follow from the problem:

1. **Rank by measurement, not volume.** `RISK_SCORE` is computed in-database from
   anomaly, breach days, slope and complaint density — a signal from the instruments,
   a confirmation from the citizens.
2. **Publish the uncertainty.** Every forecast carries a band; the defect rate is a
   first-class number (97.01% complete, 3% unusable) instead of a footnote.
3. **Keep the receipt.** Every figure names the SQL file that produced it, so any
   claim in this repository can be checked in two clicks.

## What is out of scope

The readings in this dataset are generated in SQL (monsoon intrusions, a chronic
under-dosing ward, a coliform cluster, probe drift). The pipeline, the detectors and
the SQL are real; the water is not. The deployment is one Exasol Personal node with no
replication, and the forecast is a straight line by design. See
**Data honesty & limits** in the [README](../README.md#data-honesty--limits).
