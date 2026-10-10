#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_plan_20261009.py — o PLAN.md recebe o dia 2026-10-09.

Quatro insercoes:

  1. Fase 1 fechada, com o residuo nomeado em vez de arredondado. A secao
     anterior desta fase teve de retratar um fechamento declarado "em
     substancia"; o que distingue este e um numero, nao uma frase.
  2. Fase 2 com dois impedimentos novos que o dia criou: o limiar de 400, que
     era o literal do scorer e nao governa nada, e uma data minima, porque a
     EMA zerada ainda nao convergiu.
  3. Uma quarta categoria em "The failures, sorted": falhas de COLETA. Os
     quatro achados estruturais do dia, nenhum procurado, e juntos maiores que
     os defeitos de score da categoria 1.
  4. Uma secao sobre o erro recorrente, com as regras que ele deixou. Serve
     para a proxima sessao nao repetir, que e a unica utilidade de registrar.

Nada e removido. Rode com --diff antes, que e o unico jeito de ver o que
muda num documento que e o registro do projeto.

Uso:
    python3 patch_plan_20261009.py --diff   [caminho/PLAN.md]
    python3 patch_plan_20261009.py          [caminho/PLAN.md]
"""
import argparse
import difflib
import io
import os
import sys

PADRAO = "/root/yaaf/docs/PLAN.md"

# ---------------------------------------------------------------- 1. Fase 1
F1_ANC = """The lag is a field now, not a thing to remember: `scorer_version_lag` in
`/stats`, rendered in the page's caption. It empties itself when the re-score
runs."""

F1 = """The lag is a field now, not a thing to remember: `scorer_version_lag` in
`/stats`, rendered in the page's caption. It empties itself when the re-score
runs.

---

### Closed 2026-10-09

The re-score ran. 783 addresses served, 777 of them under `5.6.0-FORMAL`, with
`RESCORE_20261009.md` carrying the reversibility hashes, the before-and-after
table, and the stated reason for zeroing each of the three state fields.

The phase's own indicator did not reach zero, and the closure says why rather
than rounding it off. `scorer_version_lag` still lists `5.0.0-FORMAL` behind 6
records. Those six are addresses the current specification **declines to score**,
not addresses that were missed: their payload's profile regressed to `unknown`
and the emit filters on profile. Two further records were withheld entirely,
having no payload at all. The mechanism, the decision, and why the two get
different treatment are in `D12_STALE_RECORDS.md`.

What separates this closure from the one this section had to retract is a number.
When the phase was called "closed in substance", **363 of 363** served records
were pre-amendment and no figure on the page reflected the specification. Now
**777 of 783** are current, the 6 exceptions are published as exceptions carrying
`basis=stale` and a reason, and the 2 unverifiable ones are out of every count
while staying readable one address at a time. This phase existed because *a
scorer that has been corrected and not re-run publishes the old specification
under the new version number*. That is resolved.

**The consequence the phase did not anticipate.** Resetting `ema` to
`EMA_INITIAL` leaves one observation per address, and one observation has a
ceiling of `0.85 x 300 + 0.15 x 1000 = 405` against a contract threshold of 500.
Eligibility fell from 4 to 0 **by arithmetic and not by performance**: no agent
could have cleared the threshold in that round whatever it did. The observed
maximum confirms the identity, `255 + 1.5 x 70.6 = 360.9`.

Measured in `docs/evidence/sim_steady_state.py` over the 607 served YAAF
records, holding CF and SF at the values in each record: **34 clear 500 once the
EMA converges**, projected ceiling **715.16**, 4 to 8 collection events for the
leaders. The threshold is reachable under this specification, which was the
better of the two branches — had nothing reached it, what would have been in
question was the threshold against the scale rather than the agents.

Three figures in that measurement were first stated wrongly here, and the
corrections belong to the record:

- Counting `S_RAW >= 50` gives **86**, not 34. That form assumes `CF = SF = 1`;
  the condition is `S_RAW x 10 x CF x SF >= 500`. The assumption overcounted by
  52 agents, and 86 was quoted as a projection before being checked.
- The mean `SISTEMA` **rises** (115.35 to 141.96) while **395 of 607 EMAs fall**.
  The sign of a product's mean was inferred from the sign of one factor's mean,
  which does not follow: the agents whose EMA rises carry higher `CF x SF`.
- `CF x SF` is **not** concentrated low. One sampled agent showed 0.166 and an
  argument was built on it; across the population 253 agents are above 0.4 and 73
  above 0.8.

Published alongside, so the zero cannot be read as a verdict on the agents:
`eligible_at_ema_steady_state` in `/stats`, computed independently of the
simulation and agreeing with it at 34, and the sentence the page now carries."""

# ---------------------------------------------------------------- 2. Fase 2
F2_ANC = """3. **The threshold.** SISTEMA 400 — the VERIFIED boundary, the first band with a
   stake floor that means anything — assigned by the Phase 1 scorer, declared
   before the run."""

F2 = """3. **The threshold, and it can no longer be 400 by inheritance.** This item
   said SISTEMA 400 — the VERIFIED boundary, the first band with a stake
   floor that means anything. On 2026-10-09 that number was found to be the
   scorer's own `is_eligible` literal, which governs nothing: the contract's
   `SCORE_THRESHOLD_ACTIVE` is **500**, and the gap between the two was
   publishing 9 eligible agents where the contract accepts 4. The scorer field
   has since been removed. So this phase must **re-declare** its threshold
   before the run — 500, to match what governs registration, or 400 with a
   written reason for measuring the gate at a boundary the contract does not
   use. Inheriting 400 in silence would measure the gate against a number this
   project has just taken out of circulation.

3a. **A minimum date, which is new.** The re-score reset the EMA, so every
   address now carries a single observation and the leaders are 4 to 8
   collection events from convergence. Assigning bands today would assign them
   from scores in transit, and the measurement would then describe the EMA's
   transient rather than the gate. This phase has a floor in time now, and it is
   a function of collection cadence rather than of anyone's schedule. The figure
   to watch is `eligible_at_ema_steady_state` converging on `eligible` in
   `/stats`."""

# ------------------------------------------------- 3. a quarta categoria
F4_ANC = """**3. Failures of durability.** This is the newest and the worst. Below."""

F4 = """**3. Failures of durability.** This is the newest and the worst. Below.

**4. Failures of collection.** Found on 2026-10-09 while verifying the re-score.
None of them was looked for, and together they are larger than the score defects
of category 1.

- `wallets_full.txt` holds **143** addresses; `yaaf_payloads/` holds **722**
  files. Neither the six-hourly round nor `refresh_all.sh` collects anything
  outside the wallet list, so **579 payloads belong to addresses that are never
  re-collected** — while being re-scored four times a day until P1 landed. The
  served population is largely built on payloads nobody maintains.
- The six-hourly writer is `run_observatory.sh`, which appears in no crontab, no
  systemd timer and no PM2 app; it was found by the two strings it writes to
  `logs/cron.log`. It collected only addresses with no payload yet — 26 of 139,
  30 of 141, 25 of 143, 29 of 143 across the logged rounds — and then scored
  everything: about 462 rows per round, four rounds a day. Roughly **1,850 scores
  a day standing on roughly 110 collection events**, which is what filled
  `round_history` with a single repeated value in 379 of 391 windows.
- The profile classifier is **not stable for the same address between runs**. Two
  addresses were labelled `directional` in one collector run while their payload
  on disk read `unknown`. The probable cause is in the same output: `HTTP Error
  429` on 9 of 57 addresses, so an incomplete collection yields a partial history
  and a different label. The chain ends in a superseded score published as
  current, which is D12.
- `profile: unknown` is **not** "no data". 261 of 722 payloads carry it,
  including addresses with Sharpe 7.04 and 10% drawdown. A third of the collected
  population never enters scoring, because the emit filters on a label that
  fails. This was previously recorded as wasted API budget; it is larger than
  that.

This category has no phase of its own and needs one. It sits upstream of
everything Phase 2 will measure: a gate measured on a population assembled this
way inherits the assembly's defects, and no statistic computed downstream can
recover from it."""

# ------------------------------------------------- 4. o erro recorrente
ERRO_ANC = """## Sequence"""

ERRO = """## The recurring error, recorded

Kept because the only use of recording a mistake is that the next session does
not repeat it. From 2026-10-09.

**Seven of one kind: a name was trusted instead of the arithmetic.**

- `load_payload(r[6])` was read as implying a path. The column holds JSON.
- A cron at `0 3 * * *` against records stamped `00:04` was read as a three-hour
  timezone bug. The machine runs in UTC; there was no offset, and the P1
  declaration it would have retracted was correct.
- `EMA_ALPHA = 0.85` was read as the smoothing weight. It is the decay; the
  weight is 0.15. The rounds column then came out as `1` for all 34 agents, and a
  uniform result across a population is a symptom, not a finding.
- A tmux session whose 3d16h uptime coincided with the start of a cadence was
  read as its cause. The session was an idle shell.
- A search filtered on `yaaf|observatory` hid `run_observatory.sh`, because the
  filter was chosen from the hypothesis instead of from the evidence.
- `gate` and `assessable` were seen in a `5.6.0` payload and assumed present in
  the `5.0.0` population. They were added later. The document that called that
  measurement unrecoverable was right and was doubted without evidence.
- `"is_eligible" not in src` was used to test for a removed field. The word
  survives in a comment, so the note asserted a read failure that had not
  happened — a null with the wrong cause, replacing a null with a different wrong
  cause. The correct predicate was already written, the same day, in
  `test_v560_weights_eligible.py`.

In every one the check was a single query, and in two the right answer was
already written in a neighbouring file.

**Two of a worse kind.** A per-agent file was named as something that must not be
committed, and then committed by the very `git add -A` offered in the same
message — the warning was worthless because the command contradicted it. And a
commit message described work that its patch had aborted without writing, so a
public history carried a claim about fields that were still empty. Both were
corrected by following commits rather than by `--amend`: a wrong message in the
history is a smaller problem than a history rewritten to look clean.

**Three of a third kind: a test that failed for its own reasons and nearly
condemned working code.** A replica built with the wrong anchor string. A
`for a in $A` loop written to bash's splitting rules inside zsh, which does not
split. A listing checked at `limit=500` over a population of 783, where the
record being sought sorts last. Each printed a verdict about the implementation
that was false.

**What caught five of the first seven was not judgement.** It was the habit of
asking for the verification output instead of assuming the step worked: the wrong
`facts.py` note surfaced only because a `facts.py | head -2` was in the block.
The atomic-group discipline refused to write on three separate occasions when an
anchor did not match, and each refusal was correct — including one that would
have left a public endpoint raising `NameError`, which is the defect that
discipline was adopted after causing once.

The rules, in the order they were earned:

1. A name is a hypothesis about arithmetic. Check the arithmetic.
2. Choose a search scope from the evidence, not from the hypothesis.
3. A uniform result across a population is a symptom until proven otherwise.
4. A test must establish its own premise before it reports a verdict.
5. Never offer `git add -A` in the same message as a warning about a file.
6. Verify that a patch applied before writing the commit message that describes
   it.
7. Instrument a gate to record what it excludes **before** removing it.

---

## Sequence"""

GRUPOS = [
    ("Fase 1 fechada, com o residuo nomeado", [(F1_ANC, F1)]),
    ("Fase 2: o limiar re-declarado e a data minima", [(F2_ANC, F2)]),
    ("falhas de coleta, a quarta categoria", [(F4_ANC, F4)]),
    ("o erro recorrente e as regras", [(ERRO_ANC, ERRO)]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("alvo", nargs="?", default=PADRAO)
    ap.add_argument("--diff", action="store_true",
                    help="mostra o diff e NAO escreve")
    a = ap.parse_args()

    if not os.path.isfile(a.alvo):
        print("ABORTADO: nao achei %s" % a.alvo)
        return 2
    src = io.open(a.alvo, encoding="utf-8").read()
    if "### Closed 2026-10-09" in src:
        print("ABORTADO: ja aplicado.")
        return 1

    tentativa, falhas = src, []
    for nome, edicoes in GRUPOS:
        parcial, erro = tentativa, None
        for velho, novo in edicoes:
            n = parcial.count(velho)
            if n != 1:
                erro = "ancora aparece %d vezes, esperava 1" % n
                break
            parcial = parcial.replace(velho, novo, 1)
        if erro:
            falhas.append("%s (%s)" % (nome, erro))
        else:
            tentativa = parcial
            print("   %s %s" % ("." if a.diff else "+", nome))

    if falhas:
        for f in falhas:
            print("   ! FALHOU: %s" % f)
        print()
        print("   NADA FOI ESCRITO. As quatro andam juntas: a Fase 1 fechada sem")
        print("   os impedimentos da Fase 2 convidaria a rodar a Fase 2 contra um")
        print("   limiar que acabou de sair de circulacao.")
        return 1

    if a.diff:
        print()
        for l in difflib.unified_diff(src.splitlines(True),
                                      tentativa.splitlines(True),
                                      "PLAN.md (atual)", "PLAN.md (com o dia)"):
            sys.stdout.write(l)
        print()
        print("   --diff: nada foi escrito. Rode sem --diff para aplicar.")
        return 0

    io.open(a.alvo, "w", encoding="utf-8").write(tentativa)
    print("   escrito %s  %+d bytes" % (a.alvo, len(tentativa) - len(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
