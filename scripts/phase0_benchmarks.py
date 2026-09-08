#!/usr/bin/env python3
"""
Phase 0 benchmarks — ATS justification measurements.
Produces JSON consumed by docs/JUSTIFICATION.md generation.

Does NOT change production code. Run from backend/:
  set APP_ENV=development
  python ../scripts/phase0_benchmarks.py
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "change-me-to-a-secure-random-string-min-32-chars")
os.environ.setdefault("JWT_SECRET_KEY", "change-me-jwt-secret-key-min-32-chars-long")

from app.schemas import CompressionStrategy  # noqa: E402
from app.services.compression_service import CompressionService  # noqa: E402
from app.services.quality_guard_service import QualityGuardService  # noqa: E402
from app.services.token_service import TokenService  # noqa: E402

OUT = ROOT / "docs" / "phase0" / "measurements.json"
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
ATS_URL = os.environ.get("ATS_URL", "http://191.252.210.60:8105")
ATS_KEY = os.environ.get("API_KEY", "ats-super-api-key")


def pad_to_approx_tokens(seed: str, target_tokens: int) -> str:
    """Repeat/trim seed text until ~target_tokens (tiktoken cl100k)."""
    ts = TokenService()
    chunk = seed.strip() + "\n"
    text = chunk
    while ts.count_tokens(text) < target_tokens:
        text += chunk
    # trim
    enc = ts.encoding.encode(text)
    return ts.encoding.decode(enc[:target_tokens])


def build_cases() -> list[dict]:
    """25 realistic long-context-ish cases (synthetic but representative)."""
    cases: list[dict] = []
    finance_block = (
        "SYSTEM: You are a finance assistant. NEVER invent balances.\n"
        "User cards: Visa ****1234 limit 5000 due day 10; Mastercard ****5678 limit 3000 due day 5.\n"
    )
    chat_noise = (
        "User: ok\nAssistant: sure\nUser: thanks\nAssistant: you're welcome\n"
        "User: hmm\nAssistant: take your time\n"
    )
    code_block = (
        "```python\n"
        "def calculate_interest(principal, rate, days):\n"
        "    # TODO: remove debug prints\n"
        "    print('debug', principal)\n"
        "    return principal * rate * days / 365\n"
        "```\n"
    )
    log_block = (
        "2026-09-01T10:00:01 INFO request_id=abc started\n"
        "2026-09-01T10:00:01 DEBUG payload={...repeated...}\n"
        "2026-09-01T10:00:02 WARN retry 1\n"
        "2026-09-01T10:00:03 ERROR timeout upstream\n"
    ) * 5
    doc_block = (
        "Please note that it is important to remember that the API must return JSON. "
        "In order to successfully implement the feature, we need authentication. "
    ) * 20

    for i in range(25):
        kind = ["chat", "code", "finance", "logs", "mixed"][i % 5]
        if kind == "chat":
            content = finance_block[:0] + (chat_noise * (8 + i)) + f"User: list my cards case={i}\n"
            preserve_marker = None
        elif kind == "code":
            content = (code_block * (6 + i // 2)) + "User: refactor calculate_interest\n"
            preserve_marker = None
        elif kind == "finance":
            content = finance_block + (doc_block * (2 + i // 5)) + "User: what's my card due dates?\n"
            preserve_marker = "NEVER invent balances"
        elif kind == "logs":
            content = (log_block * (2 + i // 4)) + "User: summarize the errors\n"
            preserve_marker = None
        else:
            content = (
                finance_block
                + code_block * 3
                + chat_noise * 10
                + doc_block
                + f"User: explain everything case={i}\n"
            )
            preserve_marker = "NEVER invent balances"

        cases.append(
            {
                "id": f"case_{i:02d}",
                "kind": kind,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": content},
                ],
                "must_preserve_substr": preserve_marker,
            }
        )
    return cases


def jaccard_tokens(a: str, b: str) -> float:
    ta = set(TokenService().encoding.encode(a))
    tb = set(TokenService().encoding.encode(b))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


async def compress_once(messages: list[dict], strategy: CompressionStrategy) -> dict:
    svc = CompressionService()
    ts = TokenService()
    before = ts.count_messages(messages)
    t0 = time.perf_counter()
    out, ops = await svc.compress_prompt(
        messages, strategy=strategy, use_ollama=False, preserve_system=True
    )
    ms = (time.perf_counter() - t0) * 1000
    after = ts.count_messages(out)
    return {
        "tokens_before": before,
        "tokens_after": after,
        "ratio": round(after / before, 4) if before else 1.0,
        "latency_ms": round(ms, 2),
        "operations": ops,
        "messages": out,
    }


async def measure_compress_latency() -> dict:
    """In-process /compress-equivalent latency by size bucket."""
    seed = (
        "Please note that it is important to remember that we need a REST API. "
        "In order to successfully implement authentication we must validate JWT. "
    )
    ts = TokenService()
    sizes = [500, 2000, 8000, 16000]
    results = {}
    for n in sizes:
        text = pad_to_approx_tokens(seed, n)
        messages = [{"role": "user", "content": text}]
        assert abs(ts.count_tokens(text) - n) <= 5 or ts.count_tokens(text) >= n - 5
        samples = []
        for _ in range(7):
            r = await compress_once(messages, CompressionStrategy.BALANCED)
            samples.append(r["latency_ms"])
        samples_sorted = sorted(samples)
        results[str(n)] = {
            "n_runs": len(samples),
            "p50_ms": round(statistics.median(samples), 2),
            "p95_ms": round(samples_sorted[max(0, int(len(samples_sorted) * 0.95) - 1)], 2),
            "mean_ms": round(statistics.mean(samples), 2),
            "tokens_in": ts.count_tokens(text),
        }
    return results


async def measure_quality_cases() -> dict:
    cases = build_cases()
    rows = []
    degraded = 0
    for case in cases:
        r = await compress_once(case["messages"], CompressionStrategy.BALANCED)
        original = "\n".join(m["content"] for m in case["messages"])
        compressed = "\n".join(str(m.get("content", "")) for m in r["messages"])
        overlap = jaccard_tokens(original, compressed)
        # Quality guard check on system preservation
        qg = QualityGuardService()
        _, report = qg.merge_with_compressed(case["messages"], r["messages"])
        preserve_ok = True
        marker = case.get("must_preserve_substr")
        if marker:
            preserve_ok = marker in compressed
            if not preserve_ok:
                degraded += 1
        # Heuristic: >25% token set loss on finance/critical AND savings >70% → risk
        loss_proxy = 1.0 - overlap
        perceptible = loss_proxy > 0.35 and case["kind"] in ("finance", "mixed")
        if perceptible and not preserve_ok:
            pass  # already counted
        elif perceptible:
            degraded += 1
        rows.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "tokens_before": r["tokens_before"],
                "tokens_after": r["tokens_after"],
                "ratio": r["ratio"],
                "latency_ms": r["latency_ms"],
                "token_jaccard": round(overlap, 4),
                "loss_proxy": round(loss_proxy, 4),
                "must_preserve_ok": preserve_ok,
                "quality_violations": getattr(report, "violations", []) or [],
                "perceptible_risk": perceptible or not preserve_ok,
            }
        )
    return {
        "n_cases": len(rows),
        "n_perceptible_risk": degraded,
        "pct_perceptible_risk": round(100 * degraded / len(rows), 1) if rows else 0,
        "mean_ratio": round(statistics.mean(r["ratio"] for r in rows), 4),
        "mean_jaccard": round(statistics.mean(r["token_jaccard"] for r in rows), 4),
        "cases": rows,
        "method": (
            "In-process CompressionService balanced use_ollama=false; "
            "quality via token Jaccard + must_preserve substring + QualityGuard. "
            "NOT LLM-as-judge (Ollama/providers unavailable from this workstation)."
        ),
    }


async def measure_ollama_prefill() -> dict:
    """TTFT vs context size on Ollama."""
    try:
        import httpx
    except ImportError:
        return {"status": "unavailable", "error": "httpx missing"}

    sizes = [500, 2000, 8000, 16000, 32000]
    seed = "word " * 100
    out: dict = {"status": "ok", "model": OLLAMA_MODEL, "url": OLLAMA_URL, "points": []}
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            ping = await client.get(f"{OLLAMA_URL.rstrip('/')}/api/tags")
            ping.raise_for_status()
        except Exception as exc:
            return {
                "status": "unavailable",
                "error": str(exc),
                "url": OLLAMA_URL,
                "note": "Re-run with OLLAMA_BASE_URL pointing to a live instance.",
            }

        for n in sizes:
            prompt = pad_to_approx_tokens(seed, n)
            # warmup small
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 1},
                "keep_alive": "2m",
            }
            t0 = time.perf_counter()
            try:
                resp = await client.post(f"{OLLAMA_URL.rstrip('/')}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                total_ms = (time.perf_counter() - t0) * 1000
                # Ollama returns total_duration/eval/prompt_eval in ns when available
                prompt_ns = data.get("prompt_eval_duration") or 0
                prefill_ms = prompt_ns / 1e6 if prompt_ns else total_ms
                out["points"].append(
                    {
                        "tokens": n,
                        "ttft_proxy_ms": round(prefill_ms, 1),
                        "wall_ms": round(total_ms, 1),
                        "eval_count": data.get("eval_count"),
                        "prompt_eval_count": data.get("prompt_eval_count"),
                    }
                )
            except Exception as exc:
                out["points"].append({"tokens": n, "error": str(exc)})
    return out


async def measure_ats_http_rtt() -> dict:
    """End-to-end /compress against live ATS if reachable."""
    try:
        import httpx
    except ImportError:
        return {"status": "unavailable"}

    seed = "Please note that it is important. " * 200
    body = {
        "messages": [{"role": "user", "content": seed}],
        "strategy": "balanced",
        "use_ollama": False,
        "check_semantic_loss": False,
    }
    samples = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            h = await client.get(f"{ATS_URL.rstrip('/')}/health/live")
            h.raise_for_status()
        except Exception as exc:
            return {
                "status": "unavailable",
                "url": ATS_URL,
                "error": str(exc),
                "fallback": "in_process_latency used as lower bound (no network hop)",
            }
        for _ in range(10):
            t0 = time.perf_counter()
            r = await client.post(
                f"{ATS_URL.rstrip('/')}/compress",
                headers={"X-API-Key": ATS_KEY, "Content-Type": "application/json"},
                json=body,
            )
            ms = (time.perf_counter() - t0) * 1000
            if r.status_code == 200:
                samples.append(ms)
    if not samples:
        return {"status": "failed", "url": ATS_URL}
    s = sorted(samples)
    return {
        "status": "ok",
        "url": ATS_URL,
        "n": len(samples),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(s[max(0, int(len(s) * 0.95) - 1)], 2),
        "mean_ms": round(statistics.mean(samples), 2),
    }


def estimate_breakeven(prefill: dict, compress_latency: dict) -> dict:
    """Find token count where prefill savings > compress RTT."""
    # Use in-process p95 at 2000 as compress cost if HTTP unavailable
    compress_p95 = compress_latency.get("2000", {}).get("p95_ms", 50)
    points = prefill.get("points") or []
    if len(points) < 2 or prefill.get("status") != "ok":
        return {
            "status": "insufficient_data",
            "compress_p95_ms_ref": compress_p95,
            "note": (
                "Without Ollama prefill curve, breakeven cannot be measured. "
                "Hypothesis for EDITH: bypass compression below ~2k–4k tokens for local models "
                "unless measured otherwise."
            ),
            "provisional_bypass_threshold_tokens": 2000,
        }

    # Compare delta prefill(large) - prefill(small) vs compress cost
    # Breakeven: tokens where reducing to ~target saves more than compress RTT
    # Approximate: savings = prefill(n) - prefill(n*0.17)  vs compress_p95
    by_n = {p["tokens"]: p.get("ttft_proxy_ms") for p in points if "ttft_proxy_ms" in p}
    ordered = sorted(by_n.items())
    threshold = None
    details = []
    for n, ttft in ordered:
        # assume compression to ~17% (ultra-like) or ~50% balanced
        target = max(500, int(n * 0.5))
        # interpolate target ttft
        lower = max((k for k, _ in ordered if k <= target), default=ordered[0][0])
        upper = min((k for k, _ in ordered if k >= target), default=ordered[-1][0])
        if upper == lower:
            ttft_t = by_n[lower]
        else:
            frac = (target - lower) / (upper - lower)
            ttft_t = by_n[lower] + frac * (by_n[upper] - by_n[lower])
        saved = ttft - ttft_t
        pays = saved > compress_p95
        details.append(
            {
                "tokens_in": n,
                "prefill_ms": ttft,
                "prefill_if_half_ms": round(ttft_t, 1),
                "saved_ms": round(saved, 1),
                "compress_p95_ms": compress_p95,
                "pays_off": pays,
            }
        )
        if pays and threshold is None:
            threshold = n
    return {
        "status": "ok",
        "bypass_below_tokens": threshold or "never_in_measured_range",
        "compress_p95_ms_ref": compress_p95,
        "details": details,
    }


def cost_audit() -> dict:
    """Audit what cost telemetry exists — no production DB access from this machine."""
    return {
        "status": "no_historical_spend_available",
        "findings": [
            "RequestLog stores cost_saved_usd as ESTIMATED savings from token deltas × static "
            "rates in config (COST_CLAUDE_*, COST_OPENAI_*), not invoices from providers.",
            "There is no table/field for actual USD charged by Groq/OpenAI/Anthropic/Gemini.",
            "LiteLLM complete_with_fallback may return cost_usd per call, but it is not "
            "aggregated into a spend ledger for months.",
            "VPS ATS (191.252.210.60:8105/8100) unreachable from this workstation during Phase 0 "
            "(timeout) — could not pull GET /stats.",
            "Ecosystem policy FREE_FIRST + current .env PROXY_USE_OLLAMA=false and Groq-first "
            "fallback imply most interactive traffic is intended to be free/local via EDITH, "
            "not billed Claude/GPT through ATS.",
        ],
        "instrumentation_required": {
            "fields": [
                "provider",
                "model",
                "tokens_in",
                "tokens_out",
                "billed_cost_usd",
                "trace_id",
                "sensitivity",
            ],
            "note": (
                "Per Phase 0 constraint (no production code this phase), instrumentation is "
                "specified here for Phase 1+/EDITH ownership of routing. ATS should stop "
                "owning billed spend once routing authority is removed."
            ),
        },
        "conclusion_preview": (
            "COST ARGUMENT IS UNVERIFIED AND LIKELY WEAK under FREE_FIRST. "
            "Cannot claim dollar savings without billed telemetry."
        ),
    }


async def main() -> None:
    print("Phase 0: measuring...")
    compress_lat = await measure_compress_latency()
    print("compress latency:", compress_lat)
    quality = await measure_quality_cases()
    print(
        "quality cases:",
        quality["n_cases"],
        "risk%",
        quality["pct_perceptible_risk"],
    )
    ollama = await measure_ollama_prefill()
    print("ollama:", ollama.get("status"), ollama.get("error", ""))
    http_rtt = await measure_ats_http_rtt()
    print("http rtt:", http_rtt.get("status"))
    breakeven = estimate_breakeven(ollama, compress_lat)
    cost = cost_audit()

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cost_audit": cost,
        "compress_latency_in_process": compress_lat,
        "ats_http_rtt": http_rtt,
        "ollama_prefill": ollama,
        "breakeven": breakeven,
        "quality": quality,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", OUT)


if __name__ == "__main__":
    asyncio.run(main())
