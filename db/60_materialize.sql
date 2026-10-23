-- ============================================================================
-- 60_materialize.sql — build the derived layer the API actually reads
-- ----------------------------------------------------------------------------
-- Run AFTER complaints have been loaded (COMPLAINT_SUMMARY is derived from
-- COMPLAINT). Idempotent: every table is TRUNCATE-then-INSERT, so `make refresh`
-- can be run any number of times and produces the same numbers.
--
-- Uses the Lua RISK_SCORE UDF. If UDF registration is unavailable, run
-- 61_materialize_no_udf.sql instead — same columns, same arithmetic.
-- ============================================================================

OPEN SCHEMA WARDQ;

-- ---------------------------------------------------------------------------
-- 1. ANOMALY_EVENT — one row per ward x parameter x month that is worth a
--    human's attention. Rows that are statistically flat are dropped so the
--    triage queue stays short.
-- ---------------------------------------------------------------------------
TRUNCATE TABLE WARDQ.ANOMALY_EVENT;

INSERT INTO WARDQ.ANOMALY_EVENT
    (SAMPLE_MONTH, WARD_ID, PARAM_CODE, MOVING_AVG, BASELINE_STDDEV, Z_SCORE,
     BREACH_DAYS, CONSECUTIVE_RUN, SLOPE_12M, SEVERITY, GENERATED_AT)
SELECT
    m.SAMPLE_MONTH,
    m.WARD_ID,
    m.PARAM_CODE,
    m.MOVING_AVG,
    NULL AS BASELINE_STDDEV,
    m.Z_SCORE,
    m.BREACH_DAYS,
    COALESCE(r.CONSECUTIVE_RUN, 0) AS CONSECUTIVE_RUN,
    m.SLOPE_12M,
    CASE WHEN ABS(m.Z_SCORE) >= 3 OR COALESCE(r.CONSECUTIVE_RUN, 0) >= 5 THEN 'high'
         WHEN ABS(m.Z_SCORE) >= 2 OR m.BREACH_DAYS >= 8                  THEN 'medium'
         ELSE 'low' END,
    CURRENT_TIMESTAMP
FROM WARDQ.V_WARD_MONTH_STAT m
LEFT JOIN WARDQ.V_BREACH_RUN r
       ON  r.WARD_ID      = m.WARD_ID
       AND r.PARAM_CODE   = m.PARAM_CODE
       AND r.ISLAND_MONTH = m.SAMPLE_MONTH
WHERE m.Z_SCORE IS NOT NULL OR m.BREACH_DAYS > 0;

-- ---------------------------------------------------------------------------
-- 2. COMPLAINT_SUMMARY — the citizen signal, rolled up to match the lab signal
--    grain (ward x month), so the two can be compared without a join skew.
-- ---------------------------------------------------------------------------
TRUNCATE TABLE WARDQ.COMPLAINT_SUMMARY;

INSERT INTO WARDQ.COMPLAINT_SUMMARY
    (SAMPLE_MONTH, WARD_ID, CATEGORY, N_COMPLAINTS, N_HIGH_SEV, SAMPLE_TEXT, GENERATED_AT)
SELECT
    SUBSTR(CAST(RECEIVED_TS AS VARCHAR(32)), 1, 7) AS SAMPLE_MONTH,
    WARD_ID,
    COALESCE(CATEGORY, 'other')                AS CATEGORY,
    COUNT(*)                                   AS N_COMPLAINTS,
    SUM(CASE WHEN SEVERITY = 'high' THEN 1 ELSE 0 END) AS N_HIGH_SEV,
    MAX(RAW_TEXT)                              AS SAMPLE_TEXT,
    CURRENT_TIMESTAMP
FROM WARDQ.COMPLAINT
WHERE WARD_ID IS NOT NULL AND RECEIVED_TS IS NOT NULL
GROUP BY SUBSTR(CAST(RECEIVED_TS AS VARCHAR(32)), 1, 7), WARD_ID, COALESCE(CATEGORY, 'other');

-- ---------------------------------------------------------------------------
-- 3. WARD_MONTH_RISK — one row per ward per month: the morning heatmap.
--    The worst-performing parameter carries the ward's score, and every
--    component is stored normalised to 0..1 so the UI can show WHY.
--
--    SLOPE_SCORE is normalised per parameter against the steepest slope seen
--    for that parameter, because a turbidity slope of 0.01 NTU/day and a pH
--    slope of 0.01 pH/day are not comparable magnitudes.
-- ---------------------------------------------------------------------------
TRUNCATE TABLE WARDQ.WARD_MONTH_RISK;

INSERT INTO WARDQ.WARD_MONTH_RISK
    (SAMPLE_MONTH, WARD_ID, RISK_SCORE, Z_COMPONENT, BREACH_COMPONENT,
     SLOPE_COMPONENT, COMPLAINT_COMP, COMPLAINT_DENSITY, WORST_PARAM,
     RANK_IN_MONTH, GENERATED_AT)
SELECT
    SAMPLE_MONTH,
    WARD_ID,
    RISK_SCORE,
    Z_COMPONENT,
    BREACH_COMPONENT,
    SLOPE_COMPONENT,
    COMPLAINT_COMP,
    COMPLAINT_DENSITY,
    WORST_PARAM,
    RANK() OVER (PARTITION BY SAMPLE_MONTH ORDER BY RISK_SCORE DESC) AS RANK_IN_MONTH,
    GENERATED_AT
FROM (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY p.SAMPLE_MONTH, p.WARD_ID
                           ORDER BY p.RISK_SCORE DESC, p.WORST_PARAM) AS RN
    FROM (
        SELECT
            s.SAMPLE_MONTH,
            s.WARD_ID,
            s.PARAM_CODE                                                    AS WORST_PARAM,
            WARDQ.RISK_SCORE(s.Z_SCORE, s.BREACH_RATIO, s.SLOPE_SCORE,
                             s.COMPLAINT_DENSITY)                           AS RISK_SCORE,
            LEAST(1.0, ABS(COALESCE(s.Z_SCORE, 0)) / 4.0)                   AS Z_COMPONENT,
            s.BREACH_RATIO                                                  AS BREACH_COMPONENT,
            s.SLOPE_SCORE                                                   AS SLOPE_COMPONENT,
            LEAST(1.0, s.COMPLAINT_DENSITY / 5.0)                           AS COMPLAINT_COMP,
            s.COMPLAINT_DENSITY,
            CURRENT_TIMESTAMP                                               AS GENERATED_AT
        FROM (
            SELECT
                m.SAMPLE_MONTH,
                m.WARD_ID,
                m.PARAM_CODE,
                m.Z_SCORE,
                CAST(m.BREACH_DAYS AS DOUBLE) / NULLIF(m.N_DAYS, 0)         AS BREACH_RATIO,
                LEAST(1.0, ABS(m.SLOPE_12M)
                     / NULLIF(MAX(ABS(m.SLOPE_12M)) OVER (PARTITION BY m.PARAM_CODE), 0))
                                                                            AS SLOPE_SCORE,
                COALESCE(c.N_COMPLAINTS, 0) * 1000.0
                    / NULLIF(w.CONNECTIONS, 0)                              AS COMPLAINT_DENSITY
            FROM WARDQ.V_WARD_MONTH_STAT m
            JOIN WARDQ.WARD w ON w.WARD_ID = m.WARD_ID
            LEFT JOIN (
                SELECT SAMPLE_MONTH, WARD_ID, SUM(N_COMPLAINTS) AS N_COMPLAINTS
                FROM WARDQ.COMPLAINT_SUMMARY
                GROUP BY SAMPLE_MONTH, WARD_ID
            ) c ON c.SAMPLE_MONTH = m.SAMPLE_MONTH AND c.WARD_ID = m.WARD_ID
        ) s
    ) p
) x
WHERE RN = 1;

-- Record the refresh so the UI footer can honestly say "data as of ...".
INSERT INTO WARDQ.LOAD_RUN (RUN_TS, STEP, ROWS_LOADED, ELAPSED_MS, LOAD_SOURCE)
SELECT CURRENT_TIMESTAMP, 'materialize_risk',
       (SELECT COUNT(*) FROM WARDQ.WARD_MONTH_RISK), NULL,
       'db/60_materialize.sql';
