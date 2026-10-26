-- ============================================================================
-- 45_forecast_view.sql — the inputs a breach forecast needs, per ward x param
-- ----------------------------------------------------------------------------
-- Run AFTER 40_anomaly_window.sql (it reads WARD_DAILY, which 40 builds, and
-- V_WARD_PARAM_SLOPE, which 40 defines). It creates a VIEW and writes no data,
-- so a refresh order that skips it only costs the forecast endpoint, never the
-- dashboard.
--
-- WHY A VIEW AND NOT A MATERIALISED TABLE
--   WARD_DAILY is 72,192 rows and V_WARD_PARAM_SLOPE is a window over it. A
--   forecast request filters to ONE ward x ONE parameter before the slope
--   window is materialised by the engine, and the whole aggregate over the
--   289k-row fact table measures 15 ms on this VM (BENCHMARK_RESULTS,
--   S1_scan_aggregate). Adding a fourth table to 10/60/61/70 to save single
--   digit milliseconds would be surface area without a measured win.
--
-- WHY NO ETA ARITHMETIC HERE
--   DAYS_TO_BREACH has four branches (upper limit, lower limit, wrong-way
--   slope, already breached) and each one is a different sentence on stage.
--   Keeping the branching in backend/forecast.py means it is unit-testable
--   without a database, and this view stays a plain fact provider.
--
-- DIALECT NOTES (each one is a real failure this project already hit)
--   * DAYS_BETWEEN(later, earlier) is used instead of ADD_DAYS(d, -30): the
--     negative offset form is not used anywhere else in this repo and is not
--     worth being the first place it is tried.
--   * Months are never derived from DATE_TRUNC; the API compares the
--     'YYYY-MM' strings it already stores.
--   * ROW_NUMBER() picks the latest slope row rather than a correlated
--     MAX(SAMPLE_DATE) subquery, so V_WARD_PARAM_SLOPE is scanned once.
--   * The comment rides on CREATE VIEW as COMMENT IS. A standalone
--     COMMENT ON VIEW fails with 0A000 "Feature not supported" in this build
--     and would abort the file after the view had already been created.
-- ============================================================================

OPEN SCHEMA WARDQ;

CREATE OR REPLACE VIEW WARDQ.V_WARD_FORECAST AS
WITH last_day AS (
    SELECT MAX(SAMPLE_DATE) AS D FROM WARDQ.WARD_DAILY
),
recent AS (
    SELECT
        d.WARD_ID,
        d.PARAM_CODE,
        l.D                    AS LAST_DATE,
        AVG(d.AVG_VALUE)       AS RECENT_AVG,
        STDDEV(d.AVG_VALUE)    AS RECENT_STDDEV,
        COUNT(d.AVG_VALUE)     AS RECENT_N
    FROM WARDQ.WARD_DAILY d, last_day l
    WHERE DAYS_BETWEEN(l.D, d.SAMPLE_DATE) <= 30
    GROUP BY d.WARD_ID, d.PARAM_CODE, l.D
),
slope AS (
    SELECT WARD_ID, PARAM_CODE, SLOPE_12M
    FROM (
        SELECT
            WARD_ID,
            PARAM_CODE,
            SLOPE_12M,
            ROW_NUMBER() OVER (PARTITION BY WARD_ID, PARAM_CODE
                               ORDER BY SAMPLE_DATE DESC) AS RN
        FROM WARDQ.V_WARD_PARAM_SLOPE
    ) ranked
    WHERE RN = 1
)
SELECT
    r.WARD_ID,
    w.WARD_NAME,
    w.CITY,
    w.CITY_ZONE,
    w.DOWNSTREAM,
    r.PARAM_CODE,
    p.PARAM_NAME,
    p.UNIT,
    p.THRESHOLD_LO,
    p.THRESHOLD_HI,
    r.LAST_DATE,
    r.RECENT_AVG,
    r.RECENT_STDDEV,
    r.RECENT_N,
    s.SLOPE_12M
FROM recent r
JOIN WARDQ.WARD w             ON w.WARD_ID   = r.WARD_ID
JOIN WARDQ.PARAMETER_LIMITS p ON p.PARAM_CODE = r.PARAM_CODE
LEFT JOIN slope s             ON s.WARD_ID   = r.WARD_ID
                             AND s.PARAM_CODE = r.PARAM_CODE
COMMENT IS
    'Per ward x parameter: 30-day mean/stddev and the trailing 12-month slope, the raw inputs for the breach-ETA forecast (branching lives in backend/forecast.py)';
