# Did the Reminder Texts Work?

A clinic sends text reminders so fewer people miss appointments. I checked
whether it worked, using 110,521 appointment records.

## The short version

At first glance, the texts look bad:

| Got a text? | Appointments | Missed |
|---|---|---|
| No | 75,045 | 16.7% |
| Yes | 35,482 | 27.6% |

People who got a text missed 11 points more often. If you stopped here, you'd
shut the program down.

**But the clinic only texts people who book at least 3 days ahead.** Nobody
booking today for today gets one. That's 46% of all appointments that never had a
chance to get a text, and those same people almost always show up (4.6% miss
rate, vs 20.2% overall). They were padding the "no text" group and making it look
great.

Comparing only people who could have gotten a text:

| Got a text? | Appointments | Missed |
|---|---|---|
| No | 24,539 | 32.7% |
| Yes | 35,482 | 27.6% |

**Now the texts look good.** 5 points fewer missed appointments, not 11 more.
The real effect is somewhere between 4.4 and 5.9 points (95% confidence).

Notice the "Yes" row never changed. Only the comparison group moved. That's what
flipped the answer.

## Is this a fair comparison?

Booking far ahead is the biggest reason people miss appointments, so I checked
whether one group booked further ahead than the other. They didn't: 13 days vs 14
days. Close enough to compare.

**What I can't prove:** the clinic picked who got a text, not a coin flip. I
ruled out the obvious explanation (booking distance), but if they chose based on
something not in the data, part of the 5 points could be that instead. So this
shows a strong association, not proof the texts caused it.

## Other things I found

**How far ahead you book matters more than anything else.** Same day: 4.6% miss.
One day ahead: 21.4%. Ten days: 31%. After that it flattens out. Almost all the
jump happens in that first day.

**Double bookings looked bad but weren't.** 1,275 appointments got booked twice.
They miss 34% of the time, which seemed like a real problem. But they're booked
15 days ahead on average vs 4 days for everything else, and anything booked 15
days out misses about 33%. So it's the booking distance again, not the double
booking.

**Past behavior predicts future behavior.** People who've missed appointments
before keep missing them. Miss rate goes from 13.5% (never missed) up to 46%
(missed 5 before), and it isn't explained by booking distance.

**Neighborhood barely matters.** Some neighborhoods looked extreme (one showed 0%
missed) but those were tiny samples. Once I required at least 500 appointments
per neighborhood, the differences mostly disappeared.

## How to run it

Built in DuckDB. Three tables: raw (untouched copy of the CSV), staging (cleaned
up), features (ready to analyze).

```bash
duckdb noshow.duckdb
.read build_features.sql
```

Dropped 6 bad rows: five booked after the appointment already happened, one with
age -1.

[`METHODS.md`](METHODS.md) has the technical details if you want them.

## Status

The evaluation is done. Still building a model that ranks appointments by risk,
so a front desk could call the most likely no-shows.
