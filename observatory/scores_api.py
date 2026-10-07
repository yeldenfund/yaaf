#!/usr/bin/env python3
"""
Yelden Scores API — scores.yelden.fund

Serve os scores YAAF e MM do observatory a partir do SQLite.
Separado da API do Agent Observatory (observatory.yelden.fund), que mede o
ecossistema ERC-8004 + x402 e e' outro produto.

    GET /health
    GET /stats
    GET /scores?limit=100&offset=0&profile=directional&stage=VERIFIED&eligible=1
    GET /scores/<address>
    GET /leaderboard?profile=directional&limit=20
    GET /agents
"""
import json
import math
import os
import sqlite3
import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.getenv("SCORES_API_PORT", "9200"))
# Liga so em localhost: o Caddy roda no mesmo VPS e faz o proxy de
# scores.yelden.fund. Expor a 9200 na internet seria desnecessario e
# deixaria a API sem TLS.
BIND = os.getenv("SCORES_API_BIND", "127.0.0.1")
MAX_LIMIT = 500
DEFAULT_LIMIT = 100
CACHE_SECONDS = 300

# Um endereco pode ser pontuado por um dos dois motores, nunca pelos dois.
# Nomes conferidos contra os dados: directional e gmx no YAAF,
# hedger e market_maker no MM, unknown sem score.
YAAF_PROFILES = ("directional", "gmx", "scalper")
MM_PROFILES = ("market_maker", "hedger")

# Ultimo score POR ENDERECO. Nao usar "WHERE ts = (SELECT MAX(ts))": basta um
# endereco com timestamp desalinhado -- reexecucao parcial, rescoring avulso --
# para a consulta devolver uma unica linha em vez da rodada inteira.
LATEST = """
SELECT address, ts, s_raw, sistema, stage, profile, payload FROM (
  SELECT address, ts, s_raw, sistema, stage, profile, payload,
         ROW_NUMBER() OVER (PARTITION BY address ORDER BY ts DESC, id DESC) AS rn
  FROM yaaf_scores
) WHERE rn = 1
"""


def connect():
    """Usa o store do observatory quando disponivel; senao, SQLITE_PATH."""
    try:
        from store import sqlite as db          # noqa: PLC0415
        return db.conn()
    except Exception:
        path = os.getenv("SQLITE_PATH", "observatory.db")
        c = sqlite3.connect(path, timeout=10)
        c.row_factory = None
        return c


def clean(obj):
    """NaN e Inf nao sao JSON validos. Vira null em vez de derrubar a resposta."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def load_payload(raw):
    if not raw:
        return {}
    try:
        p = json.loads(raw)
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def engine_of(profile):
    if profile in YAAF_PROFILES:
        return "YAAF"
    if profile in MM_PROFILES:
        return "MM"
    return None


def row_to_item(r, detail=False):
    address, ts, s_raw, sistema, stage, profile, payload = r
    p = load_payload(payload)
    eng = engine_of(profile)
    item = {
        "address": address,
        "engine": eng,
        "profile": profile,
        "stage": stage,
        "sistema": sistema,
        "s_raw": s_raw,
        "ts": ts,
    }
    if eng == "YAAF":
        # Campos que so fazem sentido no motor YAAF.
        for k in ("monthly_fee_usdc", "s_min_usdc", "is_eligible",
                  "sharpe", "max_dd", "trades", "dsr"):
            if k in p:
                item[k] = p[k]
    if detail:
        item["detail"] = p
    return clean(item)


class Handler(BaseHTTPRequestHandler):
    server_version = "YeldenScores/1.0"

    # ---- helpers -----------------------------------------------------------
    def _send(self, data, status=200):
        body = json.dumps(clean(data), default=str, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", f"public, max-age={CACHE_SECONDS}")
        self.end_headers()
        self.wfile.write(body)

    def _int(self, qs, key, default, lo, hi):
        try:
            return max(lo, min(int(qs.get(key, [str(default)])[0]), hi))
        except (ValueError, TypeError):
            return default

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    # ---- routing -----------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        c = None
        try:
            c = connect()
            if path == "/" or path == "/health":
                return self.health(c)
            if path == "/stats":
                return self.stats(c)
            if path == "/scores":
                return self.scores(c, qs)
            if path == "/leaderboard":
                return self.leaderboard(c, qs)
            if path == "/agents":
                return self.agents(c)
            if path.startswith("/scores/"):
                return self.detail(c, path[len("/scores/"):])
            self._send({"error": "not found", "path": path}, 404)
        except Exception as e:
            self._send({"error": "internal", "detail": str(e)}, 500)
        finally:
            if c is not None:
                try:
                    c.close()
                except Exception:
                    pass

    # ---- endpoints ---------------------------------------------------------
    def health(self, c):
        rows, latest = c.execute(
            "SELECT COUNT(*), MAX(ts) FROM yaaf_scores").fetchone()
        n_addr = c.execute(
            "SELECT COUNT(DISTINCT address) FROM yaaf_scores").fetchone()[0]
        self._send({"ok": True, "rows": rows, "addresses": n_addr,
                    "latest_ts": latest})

    def stats(self, c):
        rows = c.execute(LATEST).fetchall()
        by_engine, by_profile = Counter(), Counter()
        by_stage = {"YAAF": Counter(), "MM": Counter(), "unscored": Counter()}
        eligible = 0
        for r in rows:
            eng = engine_of(r[5])
            by_engine[eng or "unscored"] += 1
            by_profile[r[5] or "unknown"] += 1
            by_stage[eng or "unscored"][r[4] or "unknown"] += 1
            if eng == "YAAF" and load_payload(r[6]).get("is_eligible"):
                eligible += 1
        rounds = c.execute(
            "SELECT COUNT(DISTINCT ts) FROM yaaf_scores").fetchone()[0]
        self._send({
            "scored_addresses": len(rows),
            "scope": "addresses with at least one score record. Addresses below the 30-trade minimum are not stored here; see the whitepaper for total coverage.",
            "by_engine": dict(by_engine),
            "by_profile": dict(by_profile),
            "by_stage": {k: dict(v) for k, v in by_stage.items() if v},
            "eligible": eligible,
            "scoring_rounds": rounds,
            "latest_ts": c.execute("SELECT MAX(ts) FROM yaaf_scores").fetchone()[0],
            "note": "YAAF and MM scores share the 0-1000 range but are not "
                    "comparable: YAAF is scale-free, MM includes a size term.",
        })

    def _filtered(self, c, qs):
        rows = c.execute(LATEST).fetchall()
        profile = (qs.get("profile", [None])[0] or "").strip().lower()
        stage = (qs.get("stage", [None])[0] or "").strip().upper()
        engine = (qs.get("engine", [None])[0] or "").strip().upper()
        elig = qs.get("eligible", [None])[0]
        out = []
        for r in rows:
            if profile and (r[5] or "").lower() != profile:
                continue
            if stage and (r[4] or "").upper() != stage:
                continue
            if engine and (engine_of(r[5]) or "") != engine:
                continue
            if elig in ("1", "true"):
                # isEligible() e' do contrato e so se aplica ao motor YAAF.
                # Um score MM nunca e' elegivel, tenha o payload o campo ou nao.
                if engine_of(r[5]) != "YAAF" or not load_payload(r[6]).get("is_eligible"):
                    continue
            out.append(r)
        out.sort(key=lambda r: (r[3] if r[3] is not None else -1), reverse=True)
        return out

    def scores(self, c, qs):
        limit = self._int(qs, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = self._int(qs, "offset", 0, 0, 10 ** 7)
        rows = self._filtered(c, qs)
        page = rows[offset:offset + limit]
        self._send({
            "total": len(rows),
            "count": len(page),
            "limit": limit,
            "offset": offset,
            "scores": [row_to_item(r) for r in page],
        })

    def leaderboard(self, c, qs):
        limit = self._int(qs, "limit", 20, 1, 100)
        rows = self._filtered(c, qs)[:limit]
        items = []
        for i, r in enumerate(rows, 1):
            it = row_to_item(r)
            it["rank"] = i
            items.append(it)
        self._send({
            "engine": (qs.get("engine", [None])[0] or None),
            "profile": (qs.get("profile", [None])[0] or None),
            "count": len(items),
            "leaderboard": items,
        })

    def agents(self, c):
        rows = c.execute(LATEST).fetchall()
        rows.sort(key=lambda r: r[0])
        self._send({
            "count": len(rows),
            "agents": [{"address": r[0], "engine": engine_of(r[5]),
                        "profile": r[5], "stage": r[4], "sistema": clean(r[3])}
                       for r in rows],
        })

    def detail(self, c, addr):
        addr = addr.strip()
        if not addr.startswith("0x") or len(addr) < 6:
            return self._send({"error": "address must start with 0x"}, 400)
        # Igualdade exata, sem distincao de caixa. Prefixo com LIKE faria
        # GET /scores/0x devolver um endereco arbitrario.
        r = c.execute(LATEST.replace(") WHERE rn = 1",
                                     ") WHERE rn = 1 AND lower(address) = ?"),
                      (addr.lower(),)).fetchone()
        if not r:
            return self._send({"error": "not found", "address": addr}, 404)
        hist = c.execute(
            "SELECT ts, s_raw, sistema, stage FROM yaaf_scores "
            "WHERE lower(address) = ? ORDER BY ts DESC LIMIT 20",
            (addr.lower(),)).fetchall()
        item = row_to_item(r, detail=True)
        item["history"] = [{"ts": h[0], "s_raw": clean(h[1]),
                            "sistema": clean(h[2]), "stage": h[3]} for h in hist]
        self._send(item)


if __name__ == "__main__":
    print(f"Yelden Scores API em http://{BIND}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
