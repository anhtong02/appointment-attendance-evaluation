# Appointment No-Show Prediction

Predicting which booked appointments will be missed, so a service business can
confirm or overbook the risky ones instead of texting everybody.

## Headline finding

The obvious reading of this data says reminder texts make no-shows **worse**, by
11 percentage points. That reading is wrong. Once you account for the fact that
nearly half the appointments were never eligible for a text in the first place,
texts are associated with **5 points fewer** no-shows.

A clinic acting on the naive number would cancel a program that works.

## The problem

20.2% of appointments in this dataset were no-shows. One in five slots wasted.
Blanket reminder texts are the standard response, and they cost money and
goodwill to send to people who were always going to show up.

## Data

Public dataset of medical appointments in Vitoria, Brazil (2016). One CSV,
110,527 rows, 14 columns.

Prediction time is **booking time**. Anything recorded after the appointment is
booked cannot be used as a feature.

## Pipeline layers

| Table | Rows | Purpose |
|---|---|---|
| `raw_appointments` | 110,527 | Exact copy of the CSV. Never modified. |
| `stg_appointments` | 110,527 | Renamed columns, fixed types, one row per appointment. |
| `feat_appointments` | 110,521 | Derived features and split assignments. 6 bad rows dropped. |

Built in DuckDB (`noshow.duckdb`). Raw is rebuildable from the CSV in one
statement, so everything downstream can be dropped and rebuilt at will.

## Staging decisions

- **Column names** to snake_case. Source misspellings `Hipertension` and
  `Handcap` corrected here, left untouched in raw.
- **`appointment_date` cast to DATE.** The source stores it as a UTC timestamp
  padded to midnight, so a plain cast reads it in local time and shifts every
  date back a day. Converted with `AT TIME ZONE 'UTC'` first.
- **`scheduled_at` kept as a timestamp.** Unlike the appointment date, this is a
  real instant with meaningful clock times. Casting it to DATE here would
  destroy the booking hour permanently; that truncation belongs downstream.
- **`patient_id` cast to BIGINT.** It arrived as a `double` holding 15-digit
  values, close enough to the float precision limit to risk two patients
  collapsing into one. Verified no collisions by comparing distinct counts
  against the column read as text. None found.
- **0/1 flags cast to BOOLEAN**, except `handicap`, which has five levels (0-4)
  and is left as an integer pending a decision on what the levels mean.
- **No rows filtered.** Row count matches raw exactly. Filtering happens
  downstream where it can be documented per feature.

## Feature layer

### lead_time_days

`appointment_date - CAST(scheduled_at AS DATE)`. Days between booking and
appointment. Range 0 to 179.

Cast both sides to DATE before subtracting. Subtracting a timestamp from a date
promotes the date to midnight and returns a negative interval for every same-day
booking, which looks like a data error and isn't.

### lead_time_bucket

`same_day` / `1_2_days` / `3_7_days` / `8_30_days` / `31_plus_days`.

Boundaries are deliberately round rather than tuned to the outcome curve, to
avoid fitting noise. Same-day gets its own bucket because of the cliff below;
the 1-2 day cut also happens to align with the SMS eligibility threshold.

### Prior-history features

For each appointment, how many of that patient's earlier appointments had
already **happened** before this one was **booked**, and how many of those were
no-shows.

Implemented as a self join on `patient_id` with
`CAST(f1.scheduled_at AS DATE) > f2.appointment_date`. LEFT JOIN so first-time
patients survive with zeros rather than disappearing.

Three things this had to get right:

1. **Two different date columns.** "Prior" means the appointment occurred before
   the current one was booked. Ordering by appointment date instead would let a
   future outcome into a past prediction: a patient who books May 10 on April 25
   cannot know how their May 1 appointment went.
2. **No self-matching.** Comparing a raw timestamp against a midnight-padded date
   makes an appointment match itself, since 14:02 > 00:00 on the same day.
3. **No mutual same-day matches.** Two appointments both booked and dated the
   same day would each count the other as prior, which is impossible. Casting
   the booking side to DATE resolves both 2 and 3, at the cost of excluding
   genuinely-earlier same-day appointments. Accepted, since appointment ordering
   within a day is unknown anyway.

**A window function cannot express this.** `sum(...) OVER (PARTITION BY
patient_id ORDER BY scheduled_at)` orders by one column, but the rule needs
`appointment_date` compared against `scheduled_at`. A patient who books three
appointments in one morning would show 0, 1, 2 priors under the window version
when the correct answer is 0 for all three. Worth noting because the window
version is shorter and looks right.

Also worth noting: the default window frame with ORDER BY includes the current
row, so a running no-show count leaks the current appointment's own outcome.
`ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING` fixes that, but the
two-column problem above remains.

### Rows excluded

Six rows, documented rather than silently dropped:

- 5 with negative lead time (booked after the appointment date). Real data entry
  errors, not a timezone artifact.
- 1 with `age = -1`, likely a sentinel for unknown. Dropped rather than imputed
  since it is a single row. With more of them the right handling would be NULL
  plus an `age_missing` flag.

## Train/test splits

Both stored as columns so the split is reproducible and identical in SQL and
Python.

**`split_patient`** (primary): `hash(patient_id) % 10 < 8`. Every appointment for
a given patient lands on the same side. 79.6% train by rows. Verified that no
patient appears in both.

Hashing rather than `patient_id % 10` because raw IDs may carry structure.
Hashing rather than `random()` because the split must be identical on every
rebuild.

**`split_time`** (secondary): appointments before 2016-06-01 train, after test.
76/24 by rows.

Reporting both. The gap between them is informative: if the time-split score is
much worse, the model depends on patterns that don't hold week to week.

**Why not a random row split.** 72,601 rows (66%) belong to patients with more
than one appointment. A patient with 8 rows has only a 17% chance of landing
entirely in train, so random splitting puts most repeat patients on both sides.
The model then learns patient identity rather than patient behavior, and scores
well on people it has already seen. Reported performance would be meaningfully
better than reality.

## EDA findings

**Base rate: 20.2% no-show** (22,319 of 110,527). Predicting "everyone shows up"
is 79.8% accurate, so accuracy is not a usable metric here. Random ranking gives
precision equal to the base rate, so 20.2% is the floor any model must beat.

The metric that matters is **precision at top-k**: sort by predicted risk, take
as many as the front desk can actually phone, and measure what fraction of those
were real no-shows. This maps to the real constraint ("I can make 50 calls
today, which 50?") and cannot be gamed by flagging more people.

**Grain confirmed.** `appointment_id` is unique across all rows. One row per
appointment.

**Two different date ranges.**

- Appointments: 2016-04-29 to 2016-06-08 (six weeks)
- Bookings: 2015-11-10 to 2016-06-08 (seven months)

Every appointment that *occurred* in a six-week window, plus however far back the
booking reached. So patient history is capped at what falls inside that window,
and anything booked during the window for a later date is missing, truncating the
top of the lead time distribution.

**No nulls anywhere.** Ages top out at 115 with a smooth tail through 101 and
102, so the upper end looks real rather than capped.

### Patient visits are heavily right skewed

55,911 patients, 110,527 appointments.

| Appointments | Patients |
|---|---|
| 1 | 37,920 |
| 2 | 13,895 |
| 3 | 5,500 |
| 4 | 2,367 |
| 5+ | ~2,200 |
| max | 88 |

Median 1, mean 2, so the mean describes nobody.

68% of *patients* are one-timers but they account for only 34% of *rows*, since
frequent visitors contribute many appointments each. Rows are what the model
trains on, so 34% is the operative number: two thirds of rows have usable
patient history.

**Visit frequency itself barely predicts anything:**

| Appointments per patient | Rows | No-show rate |
|---|---|---|
| 1 | 37,920 | 18.8% |
| 2-4 | 53,763 | 21.0% |
| 5+ | 18,838 | 20.7% |

Two points of spread, not monotonic. So "this patient comes often" carries almost
no signal. This does not undermine the prior-history features, which measure
behavior rather than frequency: a 5+ patient who missed 6 of 8 is nothing like
one who missed none, and this table cannot tell them apart.

### Lead time drives everything

| Lead time | No-show rate |
|---|---|
| 0 days (same day) | 4.6% |
| 1 day | 21.4% |
| 2 days | 23.8% |
| 5 days | 26.6% |
| 10 days | 31.6% |
| 15 days | 33.4% |
| 30+ days | low 30s, flat |

The relationship is a **step, not a slope**. One day of separation takes the
no-show rate from 4.6% to 21.4%, a 4.6x jump. After that it drifts up gently and
plateaus around 30%.

Same-day bookings dominate: 38,563 appointments, 35% of all rows. Together with
days 1 and 2 that is 50,500 rows, 46% of the dataset.

Practical consequence: raw `lead_time_days` is a poor input for a linear model,
which fits a single coefficient meaning "each extra day adds X." Day 0 to 1 is
worth 17 points and day 30 to 31 is worth almost nothing. Buckets fit the actual
shape.

Tail values past ~110 days sit on groups of 1 to 5 appointments and swing between
0% and 100%. Noise, not signal.

### The SMS reversal

Naive comparison across the whole dataset:

| SMS received | Appointments | No-show rate |
|---|---|---|
| No | 75,045 | 16.70% |
| Yes | 35,482 | 27.57% |

Reads as: reminder texts increase no-shows by 11 points.

**The clinic never sends a text below 3 days of lead time.** Not a tendency, a
mechanical rule: zero texts on any appointment booked 0, 1, or 2 days out. That
is 50,500 appointments, 46% of the data, structurally ineligible. And those same
appointments have by far the lowest no-show rates in the dataset.

So the "no SMS" group was padded with tens of thousands of near-certain
attendances that could never have received a text. Restricting to appointments
where a text was actually possible:

| SMS received | Appointments | No-show rate |
|---|---|---|
| No | 24,539 | 32.69% |
| Yes | 35,482 | 27.57% |

**The sign flips.** The SMS figure does not move at all, because every recipient
was already in the eligible group. All the movement is in the comparison group,
16.7% to 32.7%.

Textbook Simpson's paradox: the direction of the effect reverses once you
condition on eligibility.

**Is the gap real?** Two-proportion z-test on the eligible subset: z = 13.5,
p ≈ 1.6e-41. 95% CI on the difference: **4.4 to 5.9 percentage points**. The CI
is the number worth reporting; at n = 60,021 the p-value is so extreme it stops
carrying information.

**Are the groups comparable?** A significance test cannot detect a biased
comparison, so the confounder was checked directly. Median lead time within the
eligible subset: 13 days for the no-SMS group, 14 days for the SMS group. Close
enough that the comparison is roughly fair.

**Limits.** Observational, not an experiment. The clinic chose who got a text.
Lead time was the obvious confounder and it has been ruled out, but if that
choice depended on something unrecorded (appointment type, whether a phone
number was on file, patient category), part of the gap could still be selection
rather than effect. The honest claim is association with a plausible mechanism,
not proven causation.

### Duplicate bookings: a non-finding

1,275 groups share the same `patient_id`, `scheduled_at`, and
`appointment_date`. 2,609 rows, 2.4% of the data. Either genuine double bookings
or duplicated source records; cannot be distinguished from this data alone.

They no-show at **34%** against a 20.2% base rate, which looks alarming.

| | Rows | Median lead time | No-show rate |
|---|---|---|---|
| Duplicate | 2,609 | 15 days | 34.0% |
| Not duplicate | 107,912 | 4 days | 19.9% |

Median lead time 15 days versus 4. And any appointment booked ~15 days out
no-shows at roughly 33%. So the 34% is lead time, not duplication. No effect to
model, and no reason to drop the rows.

Kept the same reasoning pattern as the SMS check: when a subgroup looks unusual,
test whether it is just a proxy for lead time before concluding anything.

### Neighborhood carries little signal

81 neighborhoods. Unfiltered, rates range from 0% to 29%, but the extremes are
tiny samples: PARQUE INDUSTRIAL at exactly 0.0%, ILHA DO BOI at 8.6%.

Restricted to neighborhoods with at least 500 appointments, the range compresses
to roughly 16% to 29%. Worst five:

| Neighborhood | No-show rate |
|---|---|
| SANTOS DUMONT | 28.9% |
| SANTA CLARA | 26.5% |
| ITARARÉ | 26.3% |
| JESUS DE NAZARETH | 24.4% |
| ILHA DO PRÍNCIPE | 23.5% |

The size filter changes the ranking entirely. Without it the apparent finding
would have been "ILHA DO BOI has excellent attendance," based on a handful of
rows.

About 13 points of spread among substantial neighborhoods, against lead time's
28. Real but secondary.

**Neighborhood is effectively a patient attribute, not an appointment
attribute.** Zero patients have more than one neighborhood, despite bookings
spanning seven months. With 55,911 people and nobody changing address, the
likelier explanation is that the source overwrites the field on the patient
record. If so, older appointments carry the patient's *current* address rather
than the one on file at the time, which is a mild leak. Cannot be confirmed from
this data.

**Encoding is unresolved.** Target encoding (mean no-show rate per neighborhood)
leaks unless computed on training rows only, and even then overfits on rare
categories without smoothing. One-hot or grouping rare neighborhoods together
sidesteps the problem.

## Next

- [ ] Fold the prior-history features into `feat_appointments`, with a
      `has_history` flag so "never missed" and "never been here" stay distinct
- [ ] Decide neighborhood encoding
- [ ] Decide what `handicap` levels 1-4 mean, or one-hot rather than assume order
- [ ] Baseline logistic regression on the patient split; report precision and
      lift at top 10% and 20% against the 20.2% floor
- [ ] Repeat on the time split and compare
- [ ] Gradient boosting as a second model, reporting the gap against the baseline

## Known limitations

- **EDA preceded the split.** Bucket boundaries and encoding choices were
  informed by looking at outcomes across all rows, including future test rows.
  The cuts used are round and driven by obvious structure (the day-0 cliff, the
  3-day SMS rule) rather than tuned to the curve, so the effect should be small,
  but it is not zero.
- **Six-week appointment window.** Patient history is limited to what falls
  inside it. "First appointment" means first *observed*, not first ever.
- **No weather, appointment type, or provider data.** A meaningful share of
  variance is unexplained and unexplainable from these columns.
- **No real users.** This is a portfolio project. The pipeline is real and the
  findings are real, but nobody is acting on the output.
