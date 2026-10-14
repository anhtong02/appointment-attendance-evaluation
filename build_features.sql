-- Rebuilds feat_appointments from stg_appointments.
-- Safe to re-run: drops and recreates. Raw and staging are untouched.

DROP TABLE IF EXISTS feat_appointments;

CREATE TABLE feat_appointments AS
WITH base AS (
    SELECT
        *,
        appointment_date - CAST(scheduled_at AS DATE) AS lead_time_days
    FROM stg_appointments
),

-- 6 bad rows removed here so they can't appear as anyone's prior history
clean AS (
    SELECT * FROM base
    WHERE lead_time_days >= 0    -- 5 rows booked after the appointment date
      AND age >= 0               -- 1 row with age -1
),

-- Prior history: appointments that had already HAPPENED before this one
-- was BOOKED. Two different date columns, which is why this can't be a
-- window function.
history AS (
    SELECT
        a.appointment_id,
        count(b.appointment_id) AS prior_app,
        coalesce(sum(CASE WHEN b.no_show = true THEN 1 END), 0) AS prior_noshow
    FROM clean a
    LEFT JOIN clean b
        ON  b.patient_id = a.patient_id
        AND CAST(a.scheduled_at AS DATE) > b.appointment_date
    GROUP BY a.appointment_id
),

-- Neighborhood volume. Uses row counts only, never the target, so this is
-- not target encoding and does not leak. Rare categories get pooled because
-- 81 one-hot columns on 500-row categories is mostly noise.
nbhd_volume AS (
    SELECT neighborhood, count(*) AS n
    FROM clean
    GROUP BY neighborhood
)

SELECT
    -- ---- keys, never features ----
    c.appointment_id,
    c.patient_id,

    -- ---- lead time ----
    c.lead_time_days,
    CASE
        WHEN c.lead_time_days = 0   THEN '1_same_day'
        WHEN c.lead_time_days <= 2  THEN '2_one_two_days'
        WHEN c.lead_time_days <= 7  THEN '3_three_seven_days'
        WHEN c.lead_time_days <= 30 THEN '4_eight_thirty_days'
        ELSE                             '5_thirty_one_plus'
    END AS lead_time_bucket,

    -- ---- patient history ----
    h.prior_app,
    h.prior_noshow,
    h.prior_app > 0 AS has_history,

    -- capped: everything above 5 is single-digit sample sizes
    least(h.prior_noshow, 5) AS prior_noshow_capped,

    -- rate: 2 misses out of 2 is not the same as 2 out of 10.
    -- NULL when no history, so it stays distinct from a true 0.0
    CASE WHEN h.prior_app > 0
         THEN h.prior_noshow * 1.0 / h.prior_app
    END AS prior_noshow_rate,

    -- ---- demographics ----
    c.age,
    c.gender,

    -- pooled: keeps the ~30 neighborhoods with real volume, buckets the rest
    CASE WHEN v.n >= 500 THEN c.neighborhood ELSE 'OTHER' END AS neighborhood_grp,

    -- ---- flags ----
    c.scholarship,
    c.hypertension,
    c.diabetes,
    c.alcoholism,
    c.sms_received,

    -- levels 0-4, meaning undocumented. Cast to text so downstream one-hots it
    -- instead of assuming 4 is twice 2.
    CAST(c.handicap AS VARCHAR) AS handicap_cat,

    -- ---- carried for later feature work, not for the model ----
    c.neighborhood,
    c.handicap,
    c.scheduled_at,
    c.appointment_date,

    -- ---- splits ----
    CASE WHEN hash(c.patient_id) % 10 < 8 THEN 'train' ELSE 'test' END AS split_patient,
    CASE WHEN c.appointment_date < DATE '2016-06-01' THEN 'train' ELSE 'test' END AS split_time,

    -- ---- target ----
    c.no_show

FROM clean c
JOIN history h    ON h.appointment_id = c.appointment_id
JOIN nbhd_volume v ON v.neighborhood  = c.neighborhood;
