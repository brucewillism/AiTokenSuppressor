#!/usr/bin/env python3
"""Oracle quality eval without external LLM APIs or .env secrets."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "x" * 40)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 40)

from app.schemas import CompressionStrategy
from app.services.compression_service import CompressionService
from app.services.token_service import TokenService

OUT = ROOT / "docs" / "phase0" / "quality_oracle.json"

NOISE = (
    "Please note that it is important to remember that the system must return JSON. "
    "In order to successfully implement the feature we need careful validation. "
    "User: ok\nAssistant: sure\nUser: thanks\nAssistant: you're welcome\n"
) * 12


def build_cases() -> list[dict]:
    facts = [
        ("card_due", "The Visa card ending in 4412 closes on day 17 and is due on day 25.", "25"),
        ("balance", "Account checking-8821 has a current balance of R$ 3847.50 as of 2026-08-15.", "3847.50"),
        ("invoice", "Invoice INV-90210 for vendor Acme Ltd totals R$ 1299.00 and was issued on 2026-07-03.", "1299.00"),
        ("limit", "Mastercard ending 7781 has a credit limit of R$ 6500.", "6500"),
        ("name", "The primary account holder on policy POL-551 is Marina Duarte Souza.", "Marina Duarte Souza"),
        ("date", "The last password rotation for user usr_bruce happened on 2026-06-18.", "2026-06-18"),
        ("sum", "Line items: 120.00, 80.50, and 49.50. The verified sum of these three is 250.00.", "250.00"),
        ("city", "Shipment SHP-44 is currently in warehouse city Recife-PE awaiting pickup.", "Recife"),
        ("code", "The 2FA recovery code for workspace ws_alpha is K7M9-QP2L-44ZX.", "K7M9-QP2L-44ZX"),
        ("rate", "Savings account sav-220 pays an annual interest rate of 11.25 percent.", "11.25"),
        ("count", "Portfolio holds exactly 7 active credit cards as of the last sync.", "7"),
        ("phone", "Support escalation phone for Contoso is +55-81-3344-7788.", "3344-7788"),
        ("tax", "IRRF withheld on payment PAY-331 was R$ 42.17.", "42.17"),
        ("sku", "Product SKU-BR-9088 is named 'Filtro HEPA Pro' in the catalog.", "Filtro HEPA Pro"),
        ("deadline", "Project Orion hard deadline is 2026-11-30 18:00 America/Recife.", "2026-11-30"),
        ("ticket", "Jira ticket ATS-441 status is In Review and assignee is Carla Nunes.", "Carla Nunes"),
        ("ibge", "Store ST-12 IBGE code is 2611606.", "2611606"),
        ("pix", "PIX key for merchant M-90 is CNPJ 12.345.678/0001-90.", "12.345.678/0001-90"),
        ("temp", "Server rack R3 peak temperature logged was 67.4C.", "67.4"),
        ("ver", "API contract version deployed in prod is 1.1.0-rc2.", "1.1.0-rc2"),
        ("seats", "Workspace seats purchased: 42. Seats used: 37.", "42"),
        ("lat", "Gateway latency SLA p95 target is 180 milliseconds.", "180"),
        ("hash", "Release artifact checksum prefix is a3f91c.", "a3f91c"),
        ("room", "Meeting with finance is in room B-214 at 15:30.", "B-214"),
        ("qty", "Purchase order PO-77 quantity for item X is 128 units.", "128"),
        ("iban", "Beneficiary IBAN ends with 9910 (full masked).", "9910"),
        ("score", "Risk score for customer C-55 is exactly 0.73 on the last model run.", "0.73"),
        ("branch", "Git branch for hotfix is hotfix/token-leak-202609.", "hotfix/token-leak-202609"),
    ]
    cases = []
    for cid, fact, expected in facts:
        critical = f"[CRITICAL_FACT id={cid}]\n{fact}\n[/CRITICAL_FACT]"
        context = f"{NOISE}\n=== LOGS ===\n" + ("WARN retry\n" * 40) + f"\n{critical}\n"
        cases.append(
            {
                "id": cid,
                "expected": expected,
                "critical_block": critical,
                "messages_full": [
                    {"role": "system", "content": "Answer with only the exact value."},
                    {"role": "user", "content": context + "\nQUESTION: extract the fact value."},
                ],
            }
        )
    return cases


def ctx_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


async def compress_all(messages: list[dict]) -> list[dict]:
    out, _ = await CompressionService().compress_prompt(
        messages, strategy=CompressionStrategy.BALANCED, use_ollama=False, preserve_system=True
    )
    return out


async def compress_with_must_preserve(messages: list[dict], critical: str) -> list[dict]:
    preserved = []
    compressible = []
    for m in messages:
        content = str(m.get("content", ""))
        if critical in content:
            before, _, after = content.partition(critical)
            noise_msgs = []
            if before.strip():
                noise_msgs.append({"role": m["role"], "content": before})
            if noise_msgs:
                compressed_noise, _ = await CompressionService().compress_prompt(
                    noise_msgs,
                    strategy=CompressionStrategy.BALANCED,
                    use_ollama=False,
                    preserve_system=True,
                )
                compressible.extend(compressed_noise)
            preserved.append({"role": m["role"], "content": critical + after})
        else:
            compressible.append(m)
    systems = [m for m in messages if m.get("role") == "system"]
    sys_out = [m for m in compressible if m.get("role") == "system"] or systems[:1]
    others = [m for m in compressible if m.get("role") != "system"]
    return sys_out + others + preserved


async def main() -> None:
    cases = build_cases()
    ts = TokenService()
    rows = []
    for case in cases:
        full = case["messages_full"]
        compressed = await compress_all(full)
        preserved = await compress_with_must_preserve(full, case["critical_block"])
        exp = case["expected"]
        full_ok = exp in ctx_text(full)
        comp_ok = exp in ctx_text(compressed)
        mp_ok = exp in ctx_text(preserved)
        loss = full_ok and not comp_ok
        rows.append(
            {
                "id": case["id"],
                "expected": exp,
                "tokens_full": ts.count_messages(full),
                "tokens_compressed": ts.count_messages(compressed),
                "tokens_must_preserve": ts.count_messages(preserved),
                "oracle_full_ok": full_ok,
                "oracle_compressed_ok": comp_ok,
                "oracle_must_preserve_ok": mp_ok,
                "info_loss_event": loss,
                "must_preserve_rescued": loss and mp_ok,
            }
        )

    n = len(rows)
    full_ok_n = sum(1 for r in rows if r["oracle_full_ok"])
    loss_n = sum(1 for r in rows if r["info_loss_event"])
    drop_rate = loss_n / full_ok_n if full_ok_n else None
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judge": "oracle_substring_in_context",
        "n_cases": n,
        "accuracy_full": round(full_ok_n / n, 4),
        "accuracy_compressed": round(sum(1 for r in rows if r["oracle_compressed_ok"]) / n, 4),
        "accuracy_must_preserve": round(sum(1 for r in rows if r["oracle_must_preserve_ok"]) / n, 4),
        "critical_info_loss_rate_given_full_correct": round(drop_rate, 4)
        if drop_rate is not None
        else None,
        "must_preserve_failures_when_loss": sum(
            1 for r in rows if r["info_loss_event"] and not r["oracle_must_preserve_ok"]
        ),
        "mean_compression_ratio": round(
            sum(r["tokens_compressed"] / max(r["tokens_full"], 1) for r in rows) / n, 4
        ),
        "cases": rows,
        "neural_judge_note": (
            "Groq returned HTTP 401 for all neural-judge calls "
            "(quality_accuracy.json). OpenAI probe blocked by environment policy. "
            "Oracle judge: expected answer must remain in context after compression."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "cases"}, indent=2))
    print("Wrote", OUT)


if __name__ == "__main__":
    asyncio.run(main())
