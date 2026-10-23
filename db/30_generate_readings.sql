-- ============================================================================
-- 30_generate_readings.sql — deterministic synthetic sample log (~289k rows)
-- ----------------------------------------------------------------------------
-- 24 wards x 4 parameters x 752 days x 4 sampling stations = 288,768 rows,
-- spanning 2024-10-01 .. 2026-10-21.
--
-- Generated IN SQL (no CSV, no Python generator) on purpose:
--   * re-runs produce byte-identical data, so the benchmark is comparable
--     across runs and the demo cannot drift from the PRD's numbers;
--   * a Python generator failing can never block the demo;
--   * it mirrors the starter kit's own bundled dataset pattern
--     (kit/data/datasets/energy/02_load_data.sql).
--
-- TRUNCATE runs first so a re-run cannot double-insert.
--
-- PLANTED SIGNALS — the anomaly detector is only as good as these, and each is
-- tied to DIMENSION DATA rather than a hardcoded ward list where possible, so
-- the story survives a change of wards:
--   1. Monsoon turbidity spike (Jul-Sep) — amplified for WARD.DOWNSTREAM wards
--   2. Chronic chlorine under-dosing .... ward 5
--   3. One-off coliform outbreak ........ ward 12, day 365-386 (Oct 2025)
--   4. Slow deterioration (trend, not spike) ward 21, turbidity up + chlorine down
--   5. Sensor drift false positive ...... wards 9 & 14, STATION 4 ONLY, whose
--      rows are LAB_VERIFIED = FALSE: the sensor breaches pH while every
--      lab-verified station is compliant. This is what makes
--      sql/complaint_vs_lab_disagreement.sql possible.
--   6. ~3% missing results, so the ingest validation report has real work to do
-- ============================================================================

OPEN SCHEMA WARDQ;

TRUNCATE TABLE WARDQ.SAMPLE_LOG;

INSERT INTO WARDQ.SAMPLE_LOG
    (SAMPLE_ID, WARD_ID, PARAM_CODE, SAMPLE_DATE, SAMPLE_TS,
     VALUE_DOUBLE, STATION_ID, SOURCE_STATION, LAB_VERIFIED)
WITH
d AS (
    SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3
    UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7
    UNION ALL SELECT 8 UNION ALL SELECT 9
),
days AS (
    SELECT a.n * 1000 + b.n * 100 + c.n * 10 + e.n AS day_idx
    FROM d a, d b, d c, d e
    WHERE a.n * 1000 + b.n * 100 + c.n * 10 + e.n < 752
),
stn AS (
    SELECT 1 AS s UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
),
prm AS (
    SELECT PARAM_CODE,
           CASE PARAM_CODE WHEN 'TURBIDITY' THEN 0 WHEN 'CHLORINE' THEN 1
                           WHEN 'COLIFORM'  THEN 2 ELSE 3 END AS ord
    FROM WARDQ.PARAMETER_LIMITS
),
grid AS (
    SELECT
        w.WARD_ID,
        w.WARD_NAME,
        w.DOWNSTREAM,
        p.PARAM_CODE,
        p.ord,
        dy.day_idx,
        s.s                                                   AS station_id,
        ADD_DAYS(DATE '2024-10-01', dy.day_idx)               AS sample_date,
        CASE WHEN EXTRACT(MONTH FROM ADD_DAYS(DATE '2024-10-01', dy.day_idx)) IN (7, 8, 9)
             THEN 1 ELSE 0 END                                AS monsoon,
        dy.day_idx / 751.0                                    AS progress
    FROM WARDQ.WARD w
    CROSS JOIN prm  p
    CROSS JOIN days dy
    CROSS JOIN stn  s
)
SELECT
    -- unique and arithmetic, so no ROW_NUMBER() sort over 289k rows is needed
    ((WARD_ID * 4 + (station_id - 1)) * 752 + day_idx) * 4 + ord AS SAMPLE_ID,
    WARD_ID,
    PARAM_CODE,
    sample_date,
    ADD_MINUTES(CAST(sample_date AS TIMESTAMP), (station_id - 1) * 240 + 420) AS SAMPLE_TS,

    -- ~3% of samples were taken but the result was never recorded
    CASE WHEN MOD(day_idx * 31 + WARD_ID * 7 + station_id * 13 + ord * 3, 100) < 3
         THEN NULL
         ELSE
             CASE PARAM_CODE

                 -- ----------------------------------------------------------
                 WHEN 'TURBIDITY' THEN
                       1.35
                     + 0.45 * SIN(day_idx * 2.0 * PI() / 365.0)
                     + monsoon * CASE WHEN DOWNSTREAM THEN 4.30 ELSE 0.90 END
                     + CASE WHEN WARD_ID = 21 THEN 2.10 * progress ELSE 0 END
                     + CASE WHEN WARD_ID =  5 THEN 0.35             ELSE 0 END
                     + (MOD(day_idx * 7919 + WARD_ID * 104729 + station_id * 13 + 5, 100) / 100.0 - 0.5) * 0.70

                 -- ----------------------------------------------------------
                 WHEN 'CHLORINE' THEN
                       0.62
                     + 0.05 * SIN(day_idx * 2.0 * PI() / 365.0)
                     - monsoon * CASE WHEN DOWNSTREAM THEN 0.16 ELSE 0.03 END
                     - CASE WHEN WARD_ID = 21 THEN 0.46 * progress ELSE 0 END
                     - CASE WHEN WARD_ID =  5 THEN 0.50             ELSE 0 END
                     + (MOD(day_idx * 6151 + WARD_ID * 2003 + station_id * 17 + 11, 100) / 100.0 - 0.5) * 0.10

                 -- ----------------------------------------------------------
                 WHEN 'COLIFORM' THEN
                       GREATEST(0.0,
                           (MOD(day_idx * 104729 + WARD_ID * 7919 + station_id * 29 + 7, 13) - 4) / 4.0)
                     + CASE WHEN WARD_ID = 12 AND day_idx BETWEEN 365 AND 386
                            THEN 22.0 + MOD(day_idx * 13 + station_id * 7, 10)
                            ELSE 0 END
                     + monsoon * CASE WHEN DOWNSTREAM THEN 5.50 ELSE 0.60 END
                     + CASE WHEN WARD_ID = 5 THEN 2.60 ELSE 0 END

                 -- ----------------------------------------------------------
                 ELSE   -- PH: the drifting sensor (station 4 of wards 9/14) walks
                       -- below 5.5 while every lab-verified station stays compliant
                       7.25
                     + 0.12 * SIN(day_idx * 2.0 * PI() / 180.0)
                     - CASE WHEN WARD_ID IN (9, 14) AND station_id = 4
                            THEN 1.95 * progress ELSE 0 END
                     + (MOD(day_idx * 3571 + WARD_ID * 913 + station_id * 23 + 3, 100) / 100.0 - 0.5) * 0.16
             END
    END AS VALUE_DOUBLE,

    station_id,
    WARD_NAME || ' - Stn ' || station_id AS SOURCE_STATION,

    CASE WHEN WARD_ID IN (9, 14) AND station_id = 4 THEN FALSE ELSE TRUE END AS LAB_VERIFIED
FROM grid;

-- Record the load so the UI footer and the PRD quote a real number, not a guess.
INSERT INTO WARDQ.LOAD_RUN (RUN_TS, STEP, ROWS_LOADED, ELAPSED_MS, LOAD_SOURCE)
SELECT CURRENT_TIMESTAMP, 'generate_sample_log',
       (SELECT COUNT(*) FROM WARDQ.SAMPLE_LOG),
       NULL,
       'db/30_generate_readings.sql (deterministic, seed-free SQL)';
