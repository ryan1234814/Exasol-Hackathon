-- ============================================================================
-- 50_udf_ward_risk.lua.sql — in-database composite risk score
-- ----------------------------------------------------------------------------
-- LUA, deliberately: Lua is integrated into the Exasol engine itself, whereas
-- Python/Java UDFs need the external script-languages container, which is not
-- part of a local Exasol Personal deployment. See docs/decisions.md (ADR-003).
--
-- This UDF is on the critical path ONLY for the scoring step. If registration
-- is refused (privileges, memory, or an older runtime), run
-- 61_materialize_no_udf.sql instead — it is the identical expression inlined as
-- SQL and produces byte-identical columns, so the API and UI do not change.
--
-- All four inputs are expected to be already normalised to 0..1 by the caller
-- except COMPLAINT_DENSITY, which is complaints per 1000 connections.
-- ============================================================================

CREATE OR REPLACE LUA SCALAR SCRIPT WARDQ.RISK_SCORE
    (Z_SCORE DOUBLE, BREACH_RATIO DOUBLE, SLOPE_SCORE DOUBLE, COMPLAINT_DENSITY DOUBLE)
    RETURNS DOUBLE
AS
-- Component weights. Documented rather than magic, because a ward officer has
-- to be able to ask "why is my ward 78?" and get an arithmetic answer.
local W_ANOMALY   = 35.0   -- how far this month sits outside its own baseline
local W_BREACH    = 30.0   -- what share of days violated a BIS limit
local W_TREND     = 15.0   -- slow deterioration, invisible to a threshold check
local W_COMPLAINT = 20.0   -- what citizens are actually reporting

-- Complaint density is saturating: 5 per 1000 connections per month is already
-- a bad month, so anything beyond that must not dominate the score.
local DENSITY_SATURATION = 5.0

local function clamp01(x)
    if x == nil then return 0.0 end
    if x < 0.0 then return 0.0 end
    if x > 1.0 then return 1.0 end
    return x
end

function run(ctx)
    -- |z| is used because a parameter can be anomalous in either direction:
    -- residual chlorine going too LOW is a real failure, and so is going high.
    local anomaly   = clamp01(math.abs(ctx.Z_SCORE) / 4.0)
    local breach    = clamp01(ctx.BREACH_RATIO)
    local trend     = clamp01(ctx.SLOPE_SCORE)
    local complaints = clamp01((ctx.COMPLAINT_DENSITY or 0.0) / DENSITY_SATURATION)

    local score = anomaly * W_ANOMALY
                + breach  * W_BREACH
                + trend   * W_TREND
                + complaints * W_COMPLAINT

    return score
end
/
