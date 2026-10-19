"""Textos sintéticos. Não há dado de usuário, prompt real nem segredo."""

SENTINEL = "SYNTHETIC_SENTINEL_9f3a"

SYSTEM = (
    "You are a synthetic assistant for the blue widget drill. "
    "MUST return JSON and never invent fields."
)

VERBOSE_USER = (
    "Please note that it is important to remember that "
    "the synthetic blue widget needs a REST endpoint. "
) * 12

DUPLICATE_LINE = "synthetic duplicate line about the blue widget catalog " * 4

PYTHON_SNIPPET = (
    "def synthetic_widget_total(qty):\n"
    "    price = 3\n"
    "    tax = 1\n"
    "    return qty * price + tax\n"
)

SHORT_USER = "Quanto custa o widget sintético azul?"

REPEATED_LINE = "linha sintética repetida do pedido final do widget azul"

FINAL_QUESTION = (
    "MUST return only JSON.\n"
    f"{REPEATED_LINE}\n"
    f"{REPEATED_LINE}\n"
    "Qual é o total sintético do widget azul?"
)

NEAR_OLDER_QUESTION = "qual  é o total sintético do widget azul?"
NEAR_NEWER_QUESTION = "Qual é o total sintético do widget azul?"

LONG_FINAL_USER = (
    "Pedido final sintético do widget azul, preservar por inteiro. "
    + ("detalhe sintético " * 80)
)


def repeated_final_question() -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": FINAL_QUESTION},
        {"role": "assistant", "content": "O total sintético é 4."},
        {"role": "user", "content": FINAL_QUESTION},
    ]


def near_duplicate_final_question() -> list[dict]:
    return [
        {"role": "user", "content": NEAR_OLDER_QUESTION},
        {"role": "assistant", "content": "O total sintético é 4."},
        {"role": "user", "content": NEAR_NEWER_QUESTION},
    ]


def long_final_budget_messages() -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "contexto antigo do widget " * 40},
        {"role": "assistant", "content": "resposta antiga do widget " * 40},
        {"role": "user", "content": LONG_FINAL_USER},
    ]


def conversation(copies: int = 8) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM}]
    for index in range(copies):
        messages.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"{SENTINEL} turno {index}: {VERBOSE_USER}",
            }
        )
    return messages
