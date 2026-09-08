#!/usr/bin/env python3
"""
Round 2 — quality eval by answer accuracy (not Jaccard).
Uses Groq (or OPENAI-compatible) when Ollama is down.

For each case: full | compressed | compressed+must_preserve
Metric: does model answer contain expected_answer substring?
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "change-me-to-a-secure-random-string-min-32-chars")
os.environ.setdefault("JWT_SECRET_KEY", "change-me-jwt-secret-key-min-32-chars-long")

# Load .env keys without printing them
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

from app.schemas import CompressionStrategy  # noqa: E402
from app.services.compression_service import CompressionService  # noqa: E402
from app.services.token_service import TokenService  # noqa: E402

OUT = ROOT / "docs" / "phase0" / "quality_accuracy.json"
MODEL = os.environ.get("QUALITY_EVAL_MODEL", "llama-3.1-8b-instant")
PROVIDER = "groq"


NOISE = (
    "Please note that it is important to remember that the system must return JSON. "
    "In order to successfully implement the feature we need careful validation. "
    "User: ok\nAssistant: sure\nUser: thanks\nAssistant: you're welcome\n"
) * 12


def build_cases() -> list[dict]:
    """25+ cases: long noise + one verifiable fact + question."""
    facts = [
        ("card_due", "The Visa card ending in 4412 closes on day 17 and is due on day 25.", "What day is the Visa 4412 due?", "25"),
        ("balance", "Account checking-8821 has a current balance of R$ 3847.50 as of 2026-08-15.", "What is the balance of checking-8821?", "3847.50"),
        ("invoice", "Invoice INV-90210 for vendor Acme Ltd totals R$ 1299.00 and was issued on 2026-07-03.", "What is the total of invoice INV-90210?", "1299.00"),
        ("limit", "Mastercard ending 7781 has a credit limit of R$ 6500.", "What is the credit limit of Mastercard 7781?", "6500"),
        ("name", "The primary account holder on policy POL-551 is Marina Duarte Souza.", "Who is the primary holder of POL-551?", "Marina Duarte Souza"),
        ("date", "The last password rotation for user usr_bruce happened on 2026-06-18.", "When was usr_bruce password last rotated?", "2026-06-18"),
        ("sum", "Line items: 120.00, 80.50, and 49.50. The verified sum of these three is 250.00.", "What is the verified sum of the three line items?", "250.00"),
        ("city", "Shipment SHP-44 is currently in warehouse city Recife-PE awaiting pickup.", "Which city is shipment SHP-44 in?", "Recife"),
        ("code", "The 2FA recovery code for workspace ws_alpha is K7M9-QP2L-44ZX.", "What is the 2FA recovery code for ws_alpha?", "K7M9-QP2L-44ZX"),
        ("rate", "Savings account sav-220 pays an annual interest rate of 11.25 percent.", "What is the annual interest rate of sav-220?", "11.25"),
        ("count", "Portfolio holds exactly 7 active credit cards as of the last sync.", "How many active credit cards are in the portfolio?", "7"),
        ("phone", "Support escalation phone for Contoso is +55-81-3344-7788.", "What is Contoso escalation phone?", "3344-7788"),
        ("tax", "IRRF withheld on payment PAY-331 was R$ 42.17.", "How much IRRF was withheld on PAY-331?", "42.17"),
        ("sku", "Product SKU-BR-9088 is named 'Filtro HEPA Pro' in the catalog.", "What is the name of SKU-BR-9088?", "Filtro HEPA Pro"),
        ("deadline", "Project Orion hard deadline is 2026-11-30 18:00 America/Recife.", "What is the hard deadline date for Project Orion?", "2026-11-30"),
        ("ticket", "Jira ticket ATS-441 status is In Review and assignee is Carla Nunes.", "Who is assigned to ATS-441?", "Carla Nunes"),
        ("ibge", "Store ST-12 IBGE code is 2611606.", "What is the IBGE code for store ST-12?", "2611606"),
        ("pix", "PIX key for merchant M-90 is CNPJ 12.345.678/0001-90.", "What CNPJ is the PIX key for M-90?", "12.345.678/0001-90"),
        ("temp", "Server rack R3 peak temperature logged was 67.4C.", "What peak temperature was logged for rack R3?", "67.4"),
        ("ver", "API contract version deployed in prod is 1.1.0-rc2.", "Which API contract version is in prod?", "1.1.0-rc2"),
        ("seats", "Workspace seats purchased: 42. Seats used: 37.", "How many seats were purchased?", "42"),
        ("lat", "Gateway latency SLA p95 target is 180 milliseconds.", "What is the p95 latency SLA target in ms?", "180"),
        ("hash", "Release artifact checksum prefix is a3f91c.", "What is the release checksum prefix?", "a3f91c"),
        ("room", "Meeting with finance is in room B-214 at 15:30.", "Which room is the finance meeting in?", "B-214"),
        ("qty", "Purchase order PO-77 quantity for item X is 128 units.", "What quantity is on PO-77 for item X?", "128"),
        ("iban", "Beneficiary IBAN ends with 9910 (full masked).", "What are the last four digits of the beneficiary IBAN?", "9910"),
        ("score", "Risk score for customer C-55 is exactly 0.73 on the last model run.", "What is the risk score for C-55?", "0.73"),
        ("branch", "Git branch for hotfix is hotfix/token-leak-202609.", "What is the hotfix branch name?", "hotfix/token-leak-202609"),
    ]
    cases = []
    for i, (cid, fact, question, expected) in enumerate(facts):
        critical = f"[CRITICAL_FACT id={cid}]\n{fact}\n[/CRITICAL_FACT]"
        context = (
            f"{NOISE}\n"
            f"=== SECTION LOGS ===\n{('WARN retry\n' * 40)}\n"
            f"{critical}\n"
            f"=== SECTION CHAT ===\n{('User: hmm\nAssistant: ok\n' * 20)}\n"
        )
        cases.append(
            {
                "id": cid,
                "question": question,
                "expected": expected,
                "critical_block": critical,
                "messages_full": [
                    {"role": "system", "content": "Answer with only the exact value requested. No explanation."},
                    {"role": "user", "content": context + "\nQUESTION: " + question},
                ],
            }
        )
    return cases


def answer_correct(reply: str, expected: str) -> bool:
    if not reply:
        return False
    norm = reply.strip().lower()
    exp = expected.strip().lower()
    # allow currency formatting noise
    if exp in norm:
        return True
    # digits-only compare for numeric expectations
    dig_exp = re.sub(r"[^\d.]", "", exp)
    dig_got = re.sub(r"[^\d.]", "", norm)
    if dig_exp and dig_exp in dig_got:
        return True
    return False


async def compress_all(messages: list[dict]) -> list[dict]:
    svc = CompressionService()
    out, _ = await svc.compress_prompt(
        messages, strategy=CompressionStrategy.BALANCED, use_ollama=False, preserve_system=True
    )
    return out


async def compress_with_must_preserve(messages: list[dict], critical: str) -> list[dict]:
    """Simulate must_preserve: keep critical block untouched; compress the rest."""
    preserved = []
    compressible = []
    for m in messages:
        content = str(m.get("content", ""))
        if critical in content:
            # split: compress noise, keep critical + question
            before, _, after = content.partition(critical)
            # compress only the noise parts as separate msgs
            noise_msgs = []
            if before.strip():
                noise_msgs.append({"role": m["role"], "content": before})
            if after.strip():
                # keep question after critical
                qpart = after
            else:
                qpart = ""
            if noise_msgs:
                compressed_noise, _ = await CompressionService().compress_prompt(
                    noise_msgs,
                    strategy=CompressionStrategy.BALANCED,
                    use_ollama=False,
                    preserve_system=True,
                )
                compressible.extend(compressed_noise)
            preserved.append(
                {
                    "role": m["role"],
                    "content": critical + qpart,
                }
            )
        else:
            compressible.append(m)
    if compressible and not any(critical in str(m.get("content", "")) for m in preserved):
        compressible, _ = await CompressionService().compress_prompt(
            compressible,
            strategy=CompressionStrategy.BALANCED,
            use_ollama=False,
            preserve_system=True,
        )
    # order: system first if any, then compressed noise, then preserved critical
    systems = [m for m in messages if m.get("role") == "system"]
    sys_out = [m for m in compressible if m.get("role") == "system"] or systems[:1]
    others = [m for m in compressible if m.get("role") != "system"]
    return sys_out + others + preserved


async def call_model(messages: list[dict]) -> str:
    import httpx

    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "temperature": 0,
        "max_tokens": 64,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]


def critical_still_present(messages: list[dict], critical: str) -> bool:
    blob = "\n".join(str(m.get("content", "")) for m in messages)
    return critical in blob or all(
        part in blob for part in critical.replace("[CRITICAL_FACT", "").split("\n")[1:2] if part
    )


async def run_case(case: dict) -> dict:
    ts = TokenService()
    full = case["messages_full"]
    compressed = await compress_all(full)
    preserved = await compress_with_must_preserve(full, case["critical_block"])

    critical_in_compressed = case["critical_block"] in "\n".join(
        str(m.get("content", "")) for m in compressed
    ) or case["expected"] in "\n".join(str(m.get("content", "")) for m in compressed)

    results = {}
    for name, msgs in (
        ("full", full),
        ("compressed", compressed),
        ("must_preserve", preserved),
    ):
        t0 = time.perf_counter()
        try:
            reply = await call_model(msgs)
            err = None
        except Exception as exc:
            reply = ""
            err = str(exc)
        ok = answer_correct(reply, case["expected"])
        results[name] = {
            "ok": ok,
            "reply": (reply or "")[:200],
            "error": err,
            "tokens": ts.count_messages(msgs),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        await asyncio.sleep(0.15)  # gentle rate limit

    loss_critical = results["full"]["ok"] and not results["compressed"]["ok"]
    must_preserve_rescued = loss_critical and results["must_preserve"]["ok"]

    return {
        "id": case["id"],
        "expected": case["expected"],
        "tokens_full": results["full"]["tokens"],
        "tokens_compressed": results["compressed"]["tokens"],
        "tokens_must_preserve": results["must_preserve"]["tokens"],
        "critical_fact_present_after_naive_compress": critical_in_compressed,
        "full_ok": results["full"]["ok"],
        "compressed_ok": results["compressed"]["ok"],
        "must_preserve_ok": results["must_preserve"]["ok"],
        "info_loss_event": loss_critical,
        "must_preserve_rescued": must_preserve_rescued,
        "replies": results,
    }


async def main() -> None:
    cases = build_cases()
    print(f"Running {len(cases)} cases on {PROVIDER}/{MODEL}...")
    rows = []
    for i, case in enumerate(cases):
        print(f"  [{i+1}/{len(cases)}] {case['id']}...", flush=True)
        row = await run_case(case)
        rows.append(row)
        print(
            f"    full={row['full_ok']} comp={row['compressed_ok']} "
            f"preserve={row['must_preserve_ok']} loss={row['info_loss_event']}"
        )

    n = len(rows)
    full_acc = sum(1 for r in rows if r["full_ok"]) / n
    comp_acc = sum(1 for r in rows if r["compressed_ok"]) / n
    mp_acc = sum(1 for r in rows if r["must_preserve_ok"]) / n
    # among cases where full was correct, how often compressed fails
    full_ok_rows = [r for r in rows if r["full_ok"]]
    loss_rate = (
        sum(1 for r in full_ok_rows if r["info_loss_event"]) / len(full_ok_rows)
        if full_ok_rows
        else None
    )
    # critical fact dropped by naive compress
    drop_rate = sum(1 for r in rows if not r["critical_fact_present_after_naive_compress"]) / n
    mp_rescue = sum(1 for r in rows if r["must_preserve_rescued"])
    mp_fail_when_needed = sum(
        1 for r in rows if r["info_loss_event"] and not r["must_preserve_ok"]
    )

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": PROVIDER,
        "model": MODEL,
        "n_cases": n,
        "accuracy_full": round(full_acc, 4),
        "accuracy_compressed": round(comp_acc, 4),
        "accuracy_must_preserve": round(mp_acc, 4),
        "critical_info_loss_rate_given_full_correct": round(loss_rate, 4) if loss_rate is not None else None,
        "critical_fact_drop_rate_naive_compress": round(drop_rate, 4),
        "must_preserve_rescues": mp_rescue,
        "must_preserve_failures_when_loss": mp_fail_when_needed,
        "cases": rows,
        "method_note": (
            "Answer accuracy = expected substring in model reply. "
            "must_preserve simulated by not compressing the critical block "
            "(API must_preserve not yet in CompressionService)."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote", OUT)
    print(
        f"SUMMARY full={full_acc:.0%} compressed={comp_acc:.0%} "
        f"must_preserve={mp_acc:.0%} loss_rate={loss_rate} drop_rate={drop_rate:.0%}"
    )


if __name__ == "__main__":
    asyncio.run(main())
