# onboard.yelden.fund

**Status:** live, functional
**Deployed:** 2026-10-08
**Host:** VPS `plongen` (`94.141.97.5`)
**Static root:** `/var/www/onboard/`
**Backend:** `scores_api.py` on `127.0.0.1:9200`, systemd unit `scores-api`
**TLS:** automatic, via Caddy (ACME HTTP-01)
**Linked from:** `scores.yelden.fund` footer, "For agent operators"

---

## What it is

The public entry point for an autonomous trading agent that wants to be scored by
YAAF. The agent — or its operator — proves control of an on-chain address by
signing a message, and receives the YAAF score attached to that address, if any.

It is **not** a registration system. It does not write to the database. It does not
put an agent into a queue. It answers one question: *does this address have a
score, and what is it?*

It is also **not** the market maker product. `onboard.yelden.fund` serves YAAF only.
The MM scorer shares the database and the 0–1000 range but is not reachable here.

---

## Why it exists

The only way to read a score was `GET /scores/<address>` — public, unauthenticated,
because the leaderboard is public. That is fine for a reader and not fine for an
agent. An agent can poll the leaderboard and find its own address, but it cannot
prove to itself that the number belongs to it.

Here the agent signs a message with the key that controls its address. The server
recovers the address from the signature and returns the score attached to it. The
agent now knows, with cryptographic certainty, that the score it sees is its own.

---

## What it does, step by step

**Step 1 — address.** The client posts an address to `/api/auth/challenge`. The
server validates the format and builds a message.

**Step 2 — signature.** The server returns the message. The client signs it and
posts the signature to `/api/auth/verify`. Two ways to sign:

- **In the browser.** If `window.ethereum` is present, the page offers "Sign with
  wallet", calling `personal_sign` through MetaMask or a compatible wallet.
- **On the agent's host.** The page always shows the message and a paste field. An
  agent on a VPS signs with `cast`, `eth_account`, or whatever it already uses. No
  browser, no extension, no human.

**Step 3 — result.** The server verifies the signature. If it matches the declared
address and the address has a score, the score is returned. If the address has no
score — below the 30-trade floor, or not collected — the server says so explicitly.

---

## The message

The server builds the message; the client never reconstructs it. That is what makes
the auth scheme migratable without touching the frontend.

```
Yelden Protocol

Sign to verify ownership of your agent address for YAAF scoring.

Address: 0x7fe66740c6a2c833e5e49febe41a7e33cea07696
Nonce:   1791464736

This signature is free and does not authorize any transaction.
```

The address is lowercase, the nonce a decimal string. The signature is EIP-191
(`encode_defunct`), prefixed with `\x19Ethereum Signed Message:\n<len>` before
hashing. MetaMask, `cast wallet sign` and
`eth_account.Account.sign_message(encode_defunct(...))` all apply this prefix. A
tool that does not will produce a signature that recovers the wrong address.

---

## Two auth modes

Selected by the environment variable `AUTH_MODE`.

### `timestamp` (current)

The nonce is a Unix timestamp. The server accepts any nonce within ±`AUTH_WINDOW`
seconds (default 300) of server time.

- **No server state.** Nothing is written.
- **Replay is possible** but harmless: the worst an attacker achieves is verifying
  an address that is already public on the leaderboard.
- **The tradeoff** is that a signature is valid for a window, not once.

### `nonce` (not yet active)

32 random bytes, hex-encoded, stored in `yaaf_nonces` and marked used on
verification. Replay impossible.

- **The consuming side is implemented.** `store/sqlite.py` has `create_nonce` and
  `consume_nonce`; `auth_verify` calls `consume_nonce` when `AUTH_MODE == "nonce"`.
- **The creating side is not.** `auth_challenge` returns a timestamp and writes
  nothing, even in `nonce` mode. Flipping the variable today would make every
  verification fail with `nonce invalid or already used`.
- **The frontend is ready.** It signs whatever message the server returns.

**Precondition, satisfied 2026-10-08.** The auth endpoints now send
`Cache-Control: no-store, no-cache, must-revalidate`. In `nonce` mode a cached
challenge would hand the same nonce to two callers and the second verification
would fail intermittently, with no visible cause. The header went in before
`AUTH_MODE=nonce` was ever enabled, which is the order that keeps that bug from
ever existing.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/challenge` | Build a message for an address |
| `POST` | `/api/auth/verify` | Verify a signature, return the score |

Both take a JSON body and both return `Cache-Control: no-store`. `GET /scores`
remains cacheable at `max-age=300`.

**`POST /auth/challenge`** → `{ "address": "0x..." }`

```json
{
  "ok": true,
  "address": "0x7fe6...",
  "nonce": "1791464736",
  "message": "Yelden Protocol\n\nSign to verify...",
  "mode": "timestamp"
}
```

**`POST /auth/verify`** → `{ "address", "nonce", "signature" }`, returning one of
three shapes: signature valid and address scored (the full score object, with
`detail` carrying the raw payload minus `dsr`); signature valid and address not
scored (`"scored": false` with an explanation); or signature invalid
(`"error": "signature recovers 0x..., not 0x..."`).

---

## The frontend

A single static `index.html`. No build step, no framework, no dependency.

Above the form sit the consent notice and a three-value card, in that order: the
notice frames the registry, the numbers exist inside that frame.

| Value | Source |
|---|---|
| YAAF agents | `by_engine.YAAF` from `/api/stats`, live |
| Min. closed trades | 30, static |
| Last round | `latest_ts`, live, trimmed to `MM-DD HH:MM` |

**The card deliberately shows no band counts.** An earlier draft included VERIFIED
and PROMISING. They were cut for two reasons: band assignment is level-based and
`AMENDMENT_v5.0.2.md` marks it preliminary, and `VERIFIED 6` out of 334 answers a
question the visitor did not ask with a discouraging number that is also provisional.
The visitor came to check one address. The trade floor is the fact that tells them
whether they are likely to be found, and it is the one value that renders even if the
API is unreachable.

Then three states, each a `div` shown or hidden by class:

1. **Form** — address input and "Get message".
2. **Sign** — the message in a read-only textarea, "Sign with wallet" when
   `window.ethereum` exists, a paste field for external signatures, "Verify".
3. **Result** — the score, or the "no score yet" notice.

The result view deliberately does not render `detail`. It shows SISTEMA, S_RAW,
engine, profile and timestamp. The raw payload is available from the API, but the
page does not surface `s_smoothness: 0.0`, `s_mc: 50.0` or the other values
`AMENDMENT_v5.0.2.md` documents as defective.

---

## Consent

The registry has no opt-out. Addresses enter it because the collector scanned GMX V2
and found 30 or more closed trades. The operator is not asked, and cannot ask to be
removed.

**That is a choice, not a limitation.** Removing a score is entirely possible — it
is a row in a database, not an on-chain fact. The decision is not to remove it, and
the reason is the thesis of the protocol: a registry that lets an agent erase its
own record is a registry that lets a bad agent start over under a new address.
Opt-out, in a system whose purpose is accountability, is that same loophole with a
form attached.

An earlier version of this notice argued instead that removal would be pointless
because on-chain trades are re-identifiable from their timestamps. That argument
conflates the data with the label. The data is irremovable; the label is ours and
is trivially removable. The honest position is that we could remove it and choose
not to — not that removal would achieve nothing.

The page states this in plain language before the form. It does not claim consent,
because there is none.

---

## What was verified

Tested on 2026-10-08, on the VPS, against the running service.

| Test | Result |
|---|---|
| `GET /health` after patch | `ok: true`, unchanged |
| `POST /auth/challenge` | returns message, `mode: "timestamp"` |
| `POST /auth/verify` empty signature | `missing fields` |
| `POST /auth/verify` random signature | `signature recovers 0x..., not 0x...` |
| `POST /auth/verify` valid signature, unscored address | `ok: true, scored: false` |
| `POST /auth/verify` valid signature, scored address | `ok: true, scored: true` |
| Same, through `https://onboard.yelden.fund/api/*` | identical result |
| `dsr` absent from `GET /scores/<address>` | confirmed, cache-busted |
| Consent notice present before the form | confirmed, live fetch |
| Link in `scores.yelden.fund` footer | confirmed, "For agent operators" |
| `Cache-Control: no-store` on auth endpoints | confirmed |
| `Cache-Control: max-age` still on `GET /scores` | confirmed |
| `GET /stats` returns a non-empty body | confirmed |
| Stats card present, three values, no band names | confirmed, live fetch |

The scored-address test ran against a real agent's payload copied to a test address,
inserted for the duration and deleted after. The database was confirmed clean.

**Every count in this document is a snapshot.** The collector is still expanding the
universe — 308 YAAF-scored addresses on the morning of 2026-10-08, 316 that night,
334 the following morning. Any figure here is true as of its date and will not match
the live API for long. The card on the page reads the API precisely so that it does
not carry the same problem.

**Three near-misses are recorded here on purpose**, because all three are the same
failure mode this project has been correcting for two days: concluding before
computing.

The first: the `dsr` removal was initially reported as *not applied*, against a
response the fetch layer had cached for fifteen minutes. Re-checked with a
cache-buster, it was absent. That incident is why `no-store` is treated as a
precondition for `nonce` mode rather than a polish item.

The second: the first draft of the `no-store` patch anchored on `self.end_headers()`
and would have inserted the new method between that line and `self.wfile.write(body)`,
leaving `_send` without a body write. Every `GET` on the API would have returned
headers and nothing else. Caught by reading the anchor against the original source
before running it.

The third: that patch was applied anyway, from a parallel session, before the warning
reached the operator. For roughly four minutes every `GET` on the public API returned
headers with a `Content-Length` and an empty body, while `systemctl is-active` kept
reporting the service healthy — because it was. The repair restored the write,
removed a duplicated one from `_send_nostore`, and now checks response **size**, not
service status. An assertion that the anchor exists is not an assertion that the
replacement is correct, and a process check is not a correctness check.

---

## What it does not do

- **It does not register an agent.** No write to `yaaf_scores`, no queue, no pending
  status. An address not scored today will not be scored tomorrow because someone
  verified it here.
- **It does not prove an address is an agent.** A signature proves control of a key,
  not that the key belongs to an autonomous agent rather than a human. That
  distinction lives in the registry, not here.
- **It does not offer opt-out.** See Consent.
- **It does not separate MM scores.** The `engine` field is returned so a caller can
  filter, but the page does not distinguish. A market maker address in the table
  would return its MM score under the same heading — and MM scores are not
  comparable to YAAF scores.

---

## Where it lives

| | |
|---|---|
| Static file | `/var/www/onboard/index.html` |
| Caddy block | `/etc/caddy/Caddyfile`, after `scores.yelden.fund` |
| API | `scores_api.py`: `do_POST`, `auth_challenge`, `auth_verify`, `_send_nostore` |
| Nonce store | `store/sqlite.py`, table `yaaf_nonces` (unused in timestamp mode) |
| systemd | `scores-api.service`, `AUTH_MODE` unset (defaults to `timestamp`) |

```caddy
onboard.yelden.fund {
    encode gzip
    @api path /api/*
    handle @api {
        uri strip_prefix /api
        reverse_proxy 127.0.0.1:9200
    }
    handle {
        root * /var/www/onboard
        file_server
    }
}
```

---

## Known gaps

**`nonce` mode is half-built.** The precondition is in place; the `create_nonce`
call in `auth_challenge` is not. `auth_challenge` does not currently receive a
database connection, so the patch has to open one.

**The response is not signed by the server.** The score travels over TLS but carries
no server signature. A client that does not trust the transport cannot verify the
score came from the Yelden backend. Acceptable for a read-only preview; not
acceptable for a score that gates a fee or an allocation.

**The score itself is preliminary.** `SISTEMA`, the stage and the fee are level-based
quantities, and `AMENDMENT_v5.0.2.md` documents nine defects in how the level is
computed. Rank order survives all of them; level does not. This page returns a level.

---

## What it is not

It is not the `join.html` mockup, which collects an MT5 login, an investor password
and a server name and posts them to a different host running a MetaApi integration
that exists in no file of this repository. `join.yelden.fund` still resolves there.
`onboard.yelden.fund` resolves to `94.141.97.5` and serves this.

The mockup informed the palette and the copy. It informed nothing else.

---

## Verification, from a clean shell

```bash
curl -s https://onboard.yelden.fund/ | head -5

curl -s https://onboard.yelden.fund/api/health | python3 -m json.tool

curl -sI -X POST https://onboard.yelden.fund/api/auth/challenge \
  -H 'Content-Type: application/json' \
  -d '{"address":"0x0000000000000000000000000000000000000000"}' \
  | grep -i cache-control
```

The last must show `no-store`. For the full signed flow, `/tmp/test_sign.py`
generates a wallet, requests a challenge, signs it and verifies.
