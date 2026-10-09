# D12 — Records served as current after their basis is gone

Status: **finding, with a rule proposed and not adopted.** The defect is
measured; the rule is a specification decision and is left open deliberately.

Date: 2026-10-09. Found while verifying the coverage of the re-score, not while
looking for it.

## What was observed

The re-score of 2026-10-09 produced 599 records under `5.6.0-FORMAL`. Eight of
the 607 served YAAF records were still produced by `5.0.0-FORMAL`, and the
coverage verdict in `rescore_v560.py` reported the run as incomplete.

The eight are not the residue of a half-finished run — both emits exited 0. They
are addresses the emits decline to score, whose last score therefore stays in
place and continues to be served as the current figure for that agent.

They split into two causes with nothing in common but the consequence.

## Cause A — the payload no longer exists (2 addresses)

| address | ts | profile | `s_raw` | `sistema` |
|---|---|---|---|---|
| `0x6f64c88C94` | 2026-10-06 22:27:19 | gmx | 31.87 | 114.36 |
| `0x915D9b0c37` | 2026-10-06 22:27:19 | gmx | 35.90 | 186.16 |

Neither appears in either emit log, and the GMX emit iterates `[1/500]` to
`[500/500]` over every file in the directory. Neither has a file in
`yaaf_payloads_gmx/` or in `yaaf_payloads/`. They were scored on 2026-10-06 from
a GMX payload set that no longer exists.

These two cannot be re-scored and cannot be verified. The database is serving a
number whose input is gone.

## Cause B — the profile regressed to `unknown` (6 addresses)

Six `directional` addresses appear in the emit log as `unknown skip`. Their
payload files exist; the payload's `profile` field now reads `"unknown"`, and the
emit filters on profile, so they are skipped.

The row history of one of them, `0x0c1fd09952`:

| id | ts | `s_raw` | `sistema` | profile | version |
|---|---|---|---|---|---|
| 7404 | 2026-10-09 00:04:21 | 0.0 | 0.0 | directional | 5.0.0-FORMAL |
| 6958 | 2026-10-08 18:04:03 | 0.0 | 0.0 | directional | 5.0.0-FORMAL |
| 6525 | 2026-10-08 12:04:24 | 0.0 | 0.0 | directional | 5.0.0-FORMAL |
| 6109 | 2026-10-08 06:04:31 | 0.0 | 0.0 | directional | 5.0.0-FORMAL |
| 5707 | 2026-10-08 03:07:00 | 0.0 | 0.0 | directional | 5.0.0-FORMAL |

Classified `directional`, scored every six hours without new collection, and at
some point reclassified `unknown`, after which scoring stops and the last
`5.0.0-FORMAL` row stands as current indefinitely.

### The classifier is not stable for the same address

A collector run of 2026-10-09 classified two of these same eight as
`directional`:

```
[25/57] 0x7da8d13576...  profile=directional  equity=$2,737  sharpe=4.173
[46/57] 0xcf1a30d57b...  profile=directional  equity=$2,114  sharpe=3.435
```

while the payloads on disk at re-score time read `unknown`. The same address
receives different labels on different runs.

The probable cause is in the same output: `HTTP Error 429: Too Many Requests` on
9 of 57 addresses in that run. Incomplete collection yields a partial trade
history, and a partial history yields a different classification. The chain is

    rate limit -> partial history -> profile `unknown` -> emit skips ->
    last score under a superseded specification served as current

Four links, each defensible alone, and the result is a stale number on a public
page. It is the same family as the `is_eligible = 400` defect that opened this
work, reached by a different route: a figure that no longer reflects what
governs, published without saying so.

## `unknown` does not mean "no data"

```
0xa880d6cc...  profile=unknown  equity=$237,386  sharpe=7.039  wr=67.74%  dd=10.15%
0xaa6ba025...  profile=unknown  equity=$2,124    sharpe=3.069  wr=72.73%  dd=4.77%
```

261 of 722 payloads carry `profile: unknown`. They are not empty. They are
addresses with usable metrics that the classifier cannot label, and because the
emit filters on the label, a third of the collected population never enters
scoring at all. This was previously recorded as wasted API budget; it is larger
than that.

## The structural finding behind both causes

`run_observatory.sh` rebuilds `wallets_full.txt` from the discovery lists, and
that file holds **143** addresses. `yaaf_payloads/` holds **722** files.

Neither the six-hourly round nor `refresh_all.sh` collects anything outside
`wallets_full.txt`. So **579 payloads belong to addresses that left the wallet
list and are never re-collected** — while being re-scored four times a day until
2026-10-09. The served population is largely built on payloads nobody maintains.

Causes A and B are both symptoms of this. An unmaintained payload can vanish, or
can carry a classification from a collection that will never be repeated.

## Proposed rule, not adopted

> A record whose basis is absent is not current. The API should not serve it as
> the agent's current figure, and should say which records it is withholding and
> why.

"Basis absent" has to be defined, and there are two defensible lines:

**Narrow** — the payload file is gone. Covers cause A (2 records). Cheap,
unarguable, and leaves the six `unknown` records being served.

**Wide** — the payload is gone, *or* the latest payload is one the current
specification declines to score. Covers both causes (8 records). Honest about
what it does not know, and it makes the withheld count a visible number that
grows when the collector degrades, which is a property worth having.

The wide rule has a cost worth stating plainly: it reduces the served population
from 607 to 599 today, and it would hide an agent whose only defect is that a
rate limit spoiled its last collection. That is a real loss of information, and
whether it is better than publishing a superseded figure is a judgement about
what the registry is for, not something the data decides.

Either rule belongs in the API, not the emits. The emits are doing the right
thing by declining to score what they cannot score; the error is in serving the
previous answer as though nothing had changed.

## Owed either way, independent of the rule

1. The 429 rate limiting is structural, not a traffic spike: 26 of 139, 30 of
   141, 25 of 143, 29 of 143 across the logged rounds, consistently near 20%.
   Until it is addressed the classifier will keep flipping.
2. `emit_yaaf.py` is the dead predecessor — 120 lines against 168, no `--force`,
   no P1 gate, last touched 2026-10-06, in no cron and no timer. It still writes
   to the same `yaaf_state`. A superseded emit without the gate is a loaded gun
   in a drawer; it should be deleted.
3. The 579 unmaintained payloads need a decision of their own: re-enter the
   wallet list, or be marked as a frozen historical set the way the 500 sealed
   GMX payloads already are. Right now they are neither, which is the worst of
   the three states.
