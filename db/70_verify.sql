-- ============================================================================
-- 70_verify.sql — post-load assertions
-- ----------------------------------------------------------------------------
-- Two jobs:
--   (a) catch the quoted-identifier trap (a CSV-loaded table whose columns came
--       through lowercase breaks every downstream query with "object not found"
--       — this surfaces it here instead of in the UI), and
--   (b) prove each PLANTED SIGNAL is actually DETECTABLE by the pipeline.
--       A dashboard whose anomaly detector finds nothing is a dead demo, and
--       "the data contains a monsoon spike" is not the same claim as
--       "40_anomaly_window.sql finds the monsoon spike".
--
-- Run it against a FRESH connection, not the session that created the objects:
-- a local deployment can acknowledge a DDL batch right after boot without
-- having persisted it.
-- ============================================================================

OPEN SCHEMA WARDQ;

SELECT CHECK_NAME, EXPECTED, ACTUAL, CHECK_RESULT FROM (

    -- ---- structural -------------------------------------------------------
    SELECT '01 sample_log volume' AS CHECK_NAME,
           '>= 280000' AS EXPECTED,
           CAST(COUNT(*) AS VARCHAR(40)) AS ACTUAL,
           CASE WHEN COUNT(*) >= 280000 THEN 'PASS' ELSE 'FAIL' END AS CHECK_RESULT
    FROM WARDQ.SAMPLE_LOG

    UNION ALL
    SELECT '02 ward_daily volume', '>= 70000',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) >= 70000 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.WARD_DAILY

    UNION ALL
    SELECT '03 uppercase identifiers survive', 'VALUE_DOUBLE resolvable',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.SAMPLE_LOG WHERE VALUE_DOUBLE IS NOT NULL

    -- ---- planted signal 1: monsoon turbidity spike ------------------------
    UNION ALL
    SELECT '04 monsoon turbidity spike detectable', 'max month avg > 4 NTU',
           CAST(ROUND(MAX(CASE WHEN SUBSTR(m.SAMPLE_MONTH,6,2) IN ('07','08','09')
                               THEN m.MONTH_AVG END), 2) AS VARCHAR(40)),
           CASE WHEN MAX(CASE WHEN SUBSTR(m.SAMPLE_MONTH,6,2) IN ('07','08','09')
                              THEN m.MONTH_AVG END) > 4.0 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.V_WARD_MONTH_STAT m
    JOIN WARDQ.WARD w ON w.WARD_ID = m.WARD_ID
    WHERE m.PARAM_CODE = 'TURBIDITY' AND w.DOWNSTREAM

    -- ---- planted signal 2: chronic chlorine under-dosing ------------------
    UNION ALL
    SELECT '05 ward 5 chlorine under-dosing', 'avg < 0.2 mg/L',
           CAST(ROUND(AVG(m.MONTH_AVG), 3) AS VARCHAR(40)),
           CASE WHEN AVG(m.MONTH_AVG) < 0.2 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.V_WARD_MONTH_STAT m
    WHERE m.PARAM_CODE = 'CHLORINE' AND m.WARD_ID = 5

    -- ---- planted signal 3: coliform outbreak ------------------------------
    UNION ALL
    SELECT '06 ward 12 coliform outbreak', 'max >= 20 CFU',
           CAST(MAX(s.VALUE_DOUBLE) AS VARCHAR(40)),
           CASE WHEN MAX(s.VALUE_DOUBLE) >= 20 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.SAMPLE_LOG s
    WHERE s.PARAM_CODE = 'COLIFORM' AND s.WARD_ID = 12

    UNION ALL
    SELECT '07 outbreak raises a HIGH anomaly', '>= 1 high row',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) >= 1 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.ANOMALY_EVENT
    WHERE WARD_ID = 12 AND PARAM_CODE = 'COLIFORM' AND SEVERITY = 'high'

    -- ---- planted signal 4: slow deterioration (trend, not spike) ----------
    UNION ALL
    SELECT '08 ward 21 turbidity slope positive', 'max slope > 0.001',
           CAST(ROUND(MAX(m.SLOPE_12M), 5) AS VARCHAR(40)),
           CASE WHEN MAX(m.SLOPE_12M) > 0.001 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.V_WARD_MONTH_STAT m
    WHERE m.PARAM_CODE = 'TURBIDITY' AND m.WARD_ID = 21

    -- ---- planted signal 5: sensor drift is a FALSE POSITIVE ---------------
    -- the drifted pH readings must be breachable while every lab-verified
    -- reading in the same ward stays compliant
    UNION ALL
    SELECT '09 sensor-only pH breaches exist', 'sensor>0 and lab=0',
           CAST(SUM(SENSOR_BREACHES) AS VARCHAR(40)) || ' / ' ||
           CAST(SUM(LAB_BREACHES) AS VARCHAR(40)),
           CASE WHEN SUM(SENSOR_BREACHES) > 0 AND SUM(LAB_BREACHES) = 0
                THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.V_LAB_VS_SENSOR
    WHERE PARAM_CODE = 'PH' AND WARD_ID IN (9, 14)

    -- ---- derived layer populated ------------------------------------------
    UNION ALL
    SELECT '10 risk table populated', '> 400 ward-months',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) > 400 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.WARD_MONTH_RISK

    UNION ALL
    SELECT '11 risk scores in range', '0..100',
           CAST(ROUND(MIN(RISK_SCORE),1) AS VARCHAR(40)) || ' .. ' ||
           CAST(ROUND(MAX(RISK_SCORE),1) AS VARCHAR(40)),
           CASE WHEN MIN(RISK_SCORE) >= 0 AND MAX(RISK_SCORE) <= 100.01
                THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.WARD_MONTH_RISK

    UNION ALL
    SELECT '12 ranks assigned per month', 'rank 1 exists',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) >= 10 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.WARD_MONTH_RISK WHERE RANK_IN_MONTH = 1

    UNION ALL
    SELECT '13 complaints loaded', '> 0',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.COMPLAINT

    UNION ALL
    SELECT '14 complaints categorised', '>= 90% non-null',
           CAST(COUNT(CATEGORY) AS VARCHAR(40)) || ' / ' || CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(CATEGORY) >= 0.9 * COUNT(*) THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.COMPLAINT

    UNION ALL
    SELECT '15 complaint summary populated', '> 0',
           CAST(COUNT(*) AS VARCHAR(40)),
           CASE WHEN COUNT(*) > 0 THEN 'PASS' ELSE 'FAIL' END
    FROM WARDQ.COMPLAINT_SUMMARY
)
ORDER BY CHECK_NAME;
