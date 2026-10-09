# Spec change v5.1.0 — the Volume Axiom is withdrawn from the assessability gate

**Date:** 2026-10-09
**Kind:** deliberate withdrawal of a declared rule, not a defect fix
**Supersedes:** the Volume Axiom as a gate in `YAAF_SRAW_v5_SISTEMA_v2_Formal_Spec`
**Scorer:** `5.0.2-FORMAL` → `5.1.0-FORMAL`

---

## Why this is not an amendment

Amendment v5.0.2 fixed defects: two components carried weight and ranked nobody,
two were the same variable under different caps, and a penalty had no lower
bound. Each of those was wrong on its own terms, and the change set was selected
by arithmetic rather than chosen.

This is different. The Volume Axiom works exactly as specified. It is withdrawn
because of what it does, measured, and that is a decision rather than a
correction. Hence the minor-version bump: **the change alters who is in the
population, not the scale of the score.**

## What was measured first

On the served population, latest score per address, YAAF profiles only
(363 addresses, scorer `5.0.0-FORMAL`):

| | |
|---|---|
| `s_raw = 0` | **228 of 363** (63%) |
| of those, failed the gate (`volume_ok = 0`) | **165** |
| of those, passed the gate and the arithmetic reached the floor | **63** |
| mean `dd_penalty` among the zeros | 8.89 |

The gate was the largest single producer of zeros in the published census, and a
zero from a gate means *not assessable*, not *bad*. The public band table counts
both as EXPERIMENTAL.

**The decisive case:** among the agents the gate rejected, one carried **72,545**
cumulative trades. It was excluded because its mean absolute PnL did not exceed
eleven dollars.

That is the whole argument. `initial_balance = 11000.0` is a default fixed in
`yelden_score`'s signature, applied identically to every agent, and
`VOLUME_FLOOR_FRAC = 0.001` turns it into an absolute floor of $11 of mean
absolute PnL. **In a framework that declares itself scale-free, the entry gate
was a size threshold.** It did not exclude bad agents; it excluded small ones.

## What changes

The assessability gate is the trade floor and nothing else:

```python
assessable = n_trades >= MIN_TRADES_SRAW      # 30, Formal Spec §2.2
gate = None if assessable else "min_trades"
```

`MIN_TRADES_SRAW` is unchanged and remains the specification's own floor: it
filters insufficient activity, which is what the Volume Axiom was reaching for by
a different and worse route.

## What is retained, and why

- **`volume_axiom_ok` and `VOLUME_FLOOR_FRAC` stay in the module**, labelled in
  the docstring as not applied. Deleting the implementation of a rule that is
  still in the formal specification would make the specification unverifiable;
  a reader could no longer check what was withdrawn.
- **`initial_balance` stays in the signature, unused.** `ic_test_gmx_v2.py` is
  committed evidence and produced ρ = 0.2540; it passes that argument. Removing
  the parameter would break the canonical measurement script.

## What is renamed, and what that breaks

`volume_ok` is **removed** from the returned payload. After this change it would
equal `n_trades >= MIN_TRADES_SRAW` exactly, and a field named `volume_ok` with
no volume check in it lies by its name. It is replaced by:

- `assessable` — boolean
- `gate` — `null` or `"min_trades"`, so the reason is reported rather than
  inferred. The old boolean conflated the trade floor with the axiom, which is
  precisely why the 165 above cannot be split by cause from stored payloads.

Nothing outside the scorer read `volume_ok`; verified by grep before removal.
The other matches were in `yaaf_v5.py`, the superseded scorer, which computes its
own independent check and emits its own `volume_flag`.

Stored payloads written before this change still carry `volume_ok` and no
`assessable`. That is a visible version boundary, not a migration to perform.

## The effect is measurable, and must be measured

Re-scoring the same population before and after this change counts **how many
agents the Volume Axiom was excluding on its own** — a number that cannot be
recovered from stored payloads, because `volume_ok` did not record which gate
failed.

That count is the declared effect of this change and goes here, dated, after the
re-score. Until then this document states the decision and not its consequence.

> **Measured effect:** *(pending the deliberate re-score — see the EMA boundary
> below)*

## Interaction with the re-score

This change lands alongside two other things that require the same single
deliberate re-score event:

1. **The scorer version boundary.** `ema` in `yaaf_state` was accumulated under a
   ceiling of 88.0208. Blending it with v5.1.0 values mixes two scales in one
   exponential series for roughly fifteen to twenty rounds. The declared
   resolution is to reset `ema` to `EMA_INITIAL` and clear `round_history` at the
   boundary, recorded as a dated event, rather than rescale by 100/88.0208 —
   because the two scorers are not related by a constant factor.
2. **Coverage.** The canonical measurement covers 152 agents; the served database
   covers 34 of them. Running the re-score over the full 500-payload set makes
   the served population the measured one.

One operation, three results, one dated record. The `run_observatory.sh` cron
stays removed until it is performed deliberately.

## Band thresholds are not re-derived here

Removing the gate moves agents into the scored population at the bottom of the
range. That changes the distribution the band boundaries sit on, and D8 of
Amendment v5.0.2 already records that SF's level term duplicates the EMA. A
threshold re-derivation is owed and is deliberately **not** bundled here: it
would change band membership for reasons unrelated to this withdrawal, and the
two effects would be impossible to separate afterwards.
