-- ============================================================================
-- 40_anomaly_window.sql — the analytical core
-- ----------------------------------------------------------------------------
-- This is the primary anomaly path, NOT the Lua UDF. Keeping the whole
-- detection in plain SQL is a deliberate risk decision (docs/decisions.md
-- ADR-002): the materialised tables below are what the API reads, so the
-- dashboard keeps working even if UDF registration is unavailable.
--
-- WHY WINDOW ON THE DAILY AGGREGATE AND NOT ON THE RAW FACT TABLE
--   SAMPLE_LOG is ~289k rows; WARD_DAILY is 24 x 4 x 752 = 72,192. Sorting and
--   windowing the smaller set is what keeps a refresh sub-second on the
--   2 vCPU / 6 GB local VM. The raw table is only ever scanned by the
--   GROUP BY that builds the aggregate (a columnar scan — the honest win).
-- ============================================================================

OPEN SCHEMA WARDQ;

-- ---------------------------------------------------------------------------
-- STEP 1 — ward x parameter x day aggregate. Also the breach counter.
-- A breach is any reading outside the PARAMETER_LIMITS bounds; limits are DATA.
-- ---------------------------------------------------------------------------
TRUNCATE TABLE WARDQ.WARD_DAILY;

INSERT INTO WARDQ.WARD_DAILY
    (SAMPLE_DATE, WARD_ID, PARAM_CODE, N_SAMPLES, AVG_VALUE, MIN_VALUE, MAX_VALUE,
     BREACH_FLAG, GENERATED_AT)
SELECT
    s.SAMPLE_DATE,
    s.WARD_ID,
    s.PARAM_CODE,
    COUNT(s.VALUE_DOUBLE) AS N_SAMPLES,
    AVG(s.VALUE_DOUBLE)   AS AVG_VALUE,
    MIN(s.VALUE_DOUBLE)   AS MIN_VALUE,
    MAX(s.VALUE_DOUBLE)   AS MAX_VALUE,
    SUM(CASE WHEN (p.THRESHOLD_HI IS NOT NULL AND s.VALUE_DOUBLE > p.THRESHOLD_HI)
               OR (p.THRESHOLD_LO IS NOT NULL AND s.VALUE_DOUBLE < p.THRESHOLD_LO)
             THEN 1 ELSE 0 END) AS BREACH_FLAG,
    CURRENT_TIMESTAMP
FROM WARDQ.SAMPLE_LOG s
JOIN WARDQ.PARAMETER_LIMITS p ON p.PARAM_CODE = s.PARAM_CODE
WHERE s.VALUE_DOUBLE IS NOT NULL
GROUP BY s.SAMPLE_DATE, s.WARD_ID, s.PARAM_CODE;

-- ---------------------------------------------------------------------------
-- VIEW — 30-day trailing baseline (EXCLUDING the current day, so a spike is
-- never allowed to dilute its own reference) and the z-score against it.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_WARD_DAY_STAT AS
SELECT
    SAMPLE_DATE,
    WARD_ID,
    PARAM_CODE,
    AVG_VALUE,
    BREACH_FLAG,
    -- Exasol has no DATEDIFF; DAYS_BETWEEN(later, earlier) is the supported form
    -- and returns a positive integer, which is what the spine-day index needs.
    DAYS_BETWEEN(SAMPLE_DATE, DATE '2024-10-01') AS DAY_IDX,
    AVG(AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE
                         ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)   AS MOVING_AVG,
    STDDEV(AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE
                            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS BASELINE_STDDEV,
    COUNT(AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE
                           ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)  AS BASELINE_N
FROM WARDQ.WARD_DAILY;

CREATE OR REPLACE VIEW WARDQ.V_WARD_DAY_Z AS
SELECT
    d.*,
    CASE WHEN d.BASELINE_STDDEV IS NULL OR d.BASELINE_STDDEV = 0 OR d.BASELINE_N < 7
         THEN NULL
         ELSE (d.AVG_VALUE - d.MOVING_AVG) / d.BASELINE_STDDEV
    END AS Z_SCORE
FROM WARDQ.V_WARD_DAY_STAT d;

-- ---------------------------------------------------------------------------
-- VIEW — longest run of consecutive breach days, via gaps-and-islands.
--   rn  = row order within the series
--   cum = running count of breach days
--   rn - cum is constant across a run of NON-breach days and shifts at each
--   breach, so grouping by it isolates each contiguous breach island.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_BREACH_ISLAND AS
SELECT
    WARD_ID,
    PARAM_CODE,
    SAMPLE_DATE,
    CASE WHEN BREACH_FLAG > 0
         THEN ROW_NUMBER() OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE)
              - SUM(CASE WHEN BREACH_FLAG > 0 THEN 1 ELSE 0 END)
                OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE)
         ELSE NULL
    END AS ISLAND_ID
FROM WARDQ.WARD_DAILY;

CREATE OR REPLACE VIEW WARDQ.V_BREACH_RUN AS
SELECT
    WARD_ID,
    PARAM_CODE,
    ISLAND_MONTH,
    MAX(RUN_LEN) AS CONSECUTIVE_RUN
FROM (
    -- one row per contiguous breach island: its length and its start month
    SELECT
        WARD_ID,
        PARAM_CODE,
        ISLAND_ID,
        SUBSTR(CAST(MIN(SAMPLE_DATE) AS VARCHAR(32)), 1, 7) AS ISLAND_MONTH,
        COUNT(*)                                       AS RUN_LEN
    FROM WARDQ.V_BREACH_ISLAND
    WHERE ISLAND_ID IS NOT NULL
    GROUP BY WARD_ID, PARAM_CODE, ISLAND_ID
) i
GROUP BY WARD_ID, PARAM_CODE, ISLAND_MONTH;

-- ---------------------------------------------------------------------------
-- VIEW — 12-month deterioration slope, in units per day.
-- Ordinary-least-squares by hand because Exasol has no REGR_SLOPE:
--   slope = (n*Sxy - Sx*Sy) / (n*Sxx - Sx^2)
-- Computed over a trailing 365-row window on the daily series.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_WARD_PARAM_SLOPE AS
SELECT
    WARD_ID,
    PARAM_CODE,
    SAMPLE_DATE,
    CASE WHEN (n * SXX - SX * SX) = 0 THEN NULL
         ELSE (n * SXY - SX * SY) / (n * SXX - SX * SX)
    END AS SLOPE_12M
FROM (
    -- The trailing-365-day window is repeated per aggregate rather than using a
    -- named WINDOW clause: Exasol's support for that clause is not documented
    -- and a named window that is silently rejected would break the whole file.
    SELECT
        WARD_ID,
        PARAM_CODE,
        SAMPLE_DATE,
        COUNT(AVG_VALUE)         OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) AS n,
        SUM(DAY_IDX)             OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) AS SX,
        SUM(AVG_VALUE)           OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) AS SY,
        SUM(DAY_IDX * AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) AS SXY,
        SUM(DAY_IDX * DAY_IDX)   OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) AS SXX
    FROM WARDQ.V_WARD_DAY_STAT
);

-- ---------------------------------------------------------------------------
-- VIEW — the monthly rollup the heatmap and leaderboard are built from.
-- One row per ward x parameter x calendar month.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_WARD_MONTH_STAT AS
SELECT
    SUBSTR(CAST(z.SAMPLE_DATE AS VARCHAR(32)), 1, 7) AS SAMPLE_MONTH,
    z.WARD_ID,
    z.PARAM_CODE,
    AVG(z.AVG_VALUE)                           AS MONTH_AVG,
    AVG(z.MOVING_AVG)                          AS MOVING_AVG,
    AVG(z.Z_SCORE)                             AS Z_SCORE,
    MAX(ABS(z.Z_SCORE))                        AS Z_SCORE_PEAK,
    SUM(z.BREACH_FLAG)                         AS BREACH_DAYS,
    COUNT(*)                                   AS N_DAYS,
    AVG(sl.SLOPE_12M)                          AS SLOPE_12M
FROM WARDQ.V_WARD_DAY_Z z
LEFT JOIN WARDQ.V_WARD_PARAM_SLOPE sl
       ON  sl.WARD_ID    = z.WARD_ID
       AND sl.PARAM_CODE = z.PARAM_CODE
       AND sl.SAMPLE_DATE = z.SAMPLE_DATE
GROUP BY SUBSTR(CAST(z.SAMPLE_DATE AS VARCHAR(32)), 1, 7), z.WARD_ID, z.PARAM_CODE;

-- ---------------------------------------------------------------------------
-- VIEW — lab-verified readings only. The planted pH sensor drift lives on
-- unverified station 4 of wards 9 and 14, so this view is what proves a
-- "breach" is an instrument artefact rather than a real water-quality event.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_LAB_VS_SENSOR AS
SELECT
    SUBSTR(CAST(s.SAMPLE_DATE AS VARCHAR(32)), 1, 7) AS SAMPLE_MONTH,
    s.WARD_ID,
    w.WARD_NAME,
    s.PARAM_CODE,
    p.UNIT,
    p.THRESHOLD_LO,
    p.THRESHOLD_HI,
    SUM(CASE WHEN s.LAB_VERIFIED AND ((p.THRESHOLD_HI IS NOT NULL AND s.VALUE_DOUBLE > p.THRESHOLD_HI)
        OR (p.THRESHOLD_LO IS NOT NULL AND s.VALUE_DOUBLE < p.THRESHOLD_LO))
        THEN 1 ELSE 0 END) AS LAB_BREACHES,
    SUM(CASE WHEN NOT s.LAB_VERIFIED AND ((p.THRESHOLD_HI IS NOT NULL AND s.VALUE_DOUBLE > p.THRESHOLD_HI)
        OR (p.THRESHOLD_LO IS NOT NULL AND s.VALUE_DOUBLE < p.THRESHOLD_LO))
        THEN 1 ELSE 0 END) AS SENSOR_BREACHES,
    SUM(CASE WHEN s.LAB_VERIFIED THEN 1 ELSE 0 END)     AS LAB_READINGS,
    SUM(CASE WHEN NOT s.LAB_VERIFIED THEN 1 ELSE 0 END) AS SENSOR_READINGS
FROM WARDQ.SAMPLE_LOG s
JOIN WARDQ.PARAMETER_LIMITS p ON p.PARAM_CODE = s.PARAM_CODE
JOIN WARDQ.WARD w      ON w.WARD_ID = s.WARD_ID
WHERE s.VALUE_DOUBLE IS NOT NULL
GROUP BY SUBSTR(CAST(s.SAMPLE_DATE AS VARCHAR(32)), 1, 7), s.WARD_ID, w.WARD_NAME,
         s.PARAM_CODE, p.UNIT, p.THRESHOLD_LO, p.THRESHOLD_HI;

-- ---------------------------------------------------------------------------
-- VIEW — the headline "citizens say one thing, the lab says another" join.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW WARDQ.V_WARD_MONTH_SIGNAL AS
SELECT
    m.SAMPLE_MONTH,
    m.WARD_ID,
    w.WARD_NAME,
    w.CITY,
    w.CONNECTIONS,
    m.PARAM_CODE,
    m.MONTH_AVG,
    m.MOVING_AVG,
    m.Z_SCORE,
    m.Z_SCORE_PEAK,
    m.BREACH_DAYS,
    m.SLOPE_12M,
    COALESCE(c.N_COMPLAINTS, 0) AS N_COMPLAINTS
FROM WARDQ.V_WARD_MONTH_STAT m
JOIN WARDQ.WARD w ON w.WARD_ID = m.WARD_ID
LEFT JOIN (
    SELECT SAMPLE_MONTH, WARD_ID, SUM(N_COMPLAINTS) AS N_COMPLAINTS
    FROM WARDQ.COMPLAINT_SUMMARY GROUP BY SAMPLE_MONTH, WARD_ID
) c ON c.SAMPLE_MONTH = m.SAMPLE_MONTH AND c.WARD_ID = m.WARD_ID;
