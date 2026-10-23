-- ============================================================================
-- 61_materialize_no_udf.sql — step 3 of the refresh, WITHOUT the Lua UDF
-- ----------------------------------------------------------------------------
-- WHEN TO RUN IT: only if `exapump sql < db/50_udf_ward_risk.lua.sql` or the
-- WARDQ.RISK_SCORE call inside 60_materialize.sql failed. Because Exasol
-- autocommits per statement, 60 will already have completed steps 1 and 2
-- (ANOMALY_EVENT, COMPLAINT_SUMMARY) before it fails on step 3 — so this file
-- contains ONLY step 3 and is run straight afterwards. Nothing is duplicated,
-- which is what keeps the two scoring paths from drifting apart.
--
-- The expression below is the exact arithmetic of 50_udf_ward_risk.lua.sql,
-- inlined. It produces identical columns and identical values, so the API and
-- the React UI need no change whatsoever.
-- ============================================================================

OPEN SCHEMA WARDQ;

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
            s.PARAM_CODE AS WORST_PARAM,
            -- ---- inlined WARDQ.RISK_SCORE: 35 / 30 / 15 / 20 weights ----
            LEAST(1.0, ABS(COALESCE(s.Z_SCORE, 0)) / 4.0) * 35.0
          + LEAST(1.0, GREATEST(0.0, COALESCE(s.BREACH_RATIO, 0))) * 30.0
          + LEAST(1.0, GREATEST(0.0, COALESCE(s.SLOPE_SCORE, 0))) * 15.0
          + LEAST(1.0, GREATEST(0.0, COALESCE(s.COMPLAINT_DENSITY, 0)) / 5.0) * 20.0
                                                                            AS RISK_SCORE,
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

INSERT INTO WARDQ.LOAD_RUN (RUN_TS, STEP, ROWS_LOADED, ELAPSED_MS, LOAD_SOURCE)
SELECT CURRENT_TIMESTAMP, 'materialize_risk_no_udf',
       (SELECT COUNT(*) FROM WARDQ.WARD_MONTH_RISK), NULL,
       'db/61_materialize_no_udf.sql';
