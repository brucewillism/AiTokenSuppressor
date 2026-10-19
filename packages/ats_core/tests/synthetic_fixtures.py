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
