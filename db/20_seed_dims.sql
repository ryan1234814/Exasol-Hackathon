-- ============================================================================
-- 20_seed_dims.sql — ward and parameter dimensions
-- Thresholds live here as DATA, not code, so a ward officer can see exactly
-- which limit was breached and change it without a redeploy.
-- Limits are aligned to BIS 10500:2012 acceptability ranges.
-- ============================================================================

-- Table definitions live in 10_schema.sql and are NOT repeated here: a second
-- CREATE OR REPLACE would silently override it (dropping the distribution and
-- partition clauses) depending on which file ran last. This file only seeds.

OPEN SCHEMA WARDQ;

TRUNCATE TABLE WARDQ.WARD;

INSERT INTO WARDQ.WARD (WARD_ID, WARD_NAME, CITY, CITY_ZONE, POPULATION, CONNECTIONS, DOWNSTREAM) VALUES
 ( 1,'Ward 12 - Andheri East',   'Mumbai',    'H-Front',      58200, 13400, FALSE),
 ( 2,'Ward 2 - Bandra West',     'Mumbai',    'H-East',       41300,  9800, FALSE),
 ( 3,'Ward 4 - Dharavi',         'Mumbai',    'S-East',       62700, 11200, TRUE),
 ( 4,'Ward 5 - Govandi',         'Mumbai',    'S-East',       49800,  8600, TRUE),
 ( 5,'Ward 6 - Borivali West',   'Mumbai',    'R-Central',    53100, 12050, FALSE),
 ( 6,'Ward 7 - Kurla South',     'Mumbai',    'G-North',      57400, 12980, TRUE),
 ( 7,'Ward 8 - Malad East',      'Mumbai',    'K-West',       46900, 10450, TRUE),
 ( 8,'Ward 9 - Mulund West',     'Mumbai',    'L-East',       38600,  8900, FALSE),
 ( 9,'Ward 3 - Powai',           'Mumbai',    'K-East',       29400,  6700, FALSE),
 (10,'Ward 10 - Santacruz East', 'Mumbai',    'H-West',       44100, 10100, FALSE),
 (11,'Ward 1 - Worli',           'Mumbai',    'A-Drc',        24800,  5900, FALSE),
 (12,'Ward 11 - Vile Parle East','Mumbai',    'K-West',       47200, 10800, TRUE),
 (13,'Ward 44 - Koramangala',    'Bengaluru', 'South',        36500,  8400, FALSE),
 (14,'Ward 51 - Indiranagar',    'Bengaluru', 'East',         31200,  7300, FALSE),
 (15,'Ward 68 - Jayanagar',      'Bengaluru', 'South',        34700,  8050, FALSE),
 (16,'Ward 198 - Rajajinagar',   'Bengaluru', 'West',         42600,  9700, FALSE),
 (17,'Ward 86 - Yelahanka',      'Bengaluru', 'North',        28900,  6600, FALSE),
 (18,'Ward 84 - Whitefield',     'Bengaluru', 'East',         45300, 10350, TRUE),
 (19,'Ward 178 - Electronic City','Bengaluru','Bommanahalli', 39800,  9100, TRUE),
 (20,'Ward 107 - Malleshwaram',  'Bengaluru', 'West',         33100,  7700, FALSE),
 (21,'Ward 191 - Banashankari',  'Bengaluru', 'South',        40200,  9300, TRUE),
 (22,'Ward 78 - Kalyan Nagar',   'Bengaluru', 'East',         35600,  8200, FALSE),
 (23,'Ward 97 - HSR Layout',     'Bengaluru', 'Bommanahalli', 37400,  8600, FALSE),
 (24,'Ward 205 - Peenya',        'Bengaluru', 'North',        43900, 10050, TRUE);

-- ---------------------------------------------------------------------------
-- Parameters and their acceptability limits.
-- THRESHOLD_LO / THRESHOLD_HI are NULL where the limit is one-sided.
-- ---------------------------------------------------------------------------
TRUNCATE TABLE WARDQ.PARAMETER_LIMITS;

INSERT INTO WARDQ.PARAMETER_LIMITS (PARAM_CODE, PARAM_NAME, UNIT, THRESHOLD_LO, THRESHOLD_HI) VALUES
 ('TURBIDITY','Turbidity',        'NTU',       NULL, 5.0),
 ('CHLORINE', 'Residual Chlorine','mg/L',       0.2, 1.0),
 ('COLIFORM', 'Total Coliform',   'CFU/100ml',  NULL, 0.0),
 ('PH',       'pH',               'pH',         5.5, 8.5);
