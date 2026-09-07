#!/usr/bin/env python3
"""Gera PDF da solicitacao de infraestrutura (minimo, recomendado, ideal)."""

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "SOLICITACAO_INFRA_GERENCIA.pdf"
FONT_REG = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


class InfraPDF(FPDF):
    def __init__(self) -> None:
        super().__init__()
        self.add_font("Arial", "", str(FONT_REG))
        self.add_font("Arial", "B", str(FONT_BOLD))
        self.set_auto_page_break(auto=True, margin=16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Arial", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"AI Token Suppressor - Pagina {self.page_no()}", align="C")

    def h1(self, text: str) -> None:
        self.ln(3)
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 15)
        self.set_text_color(20, 60, 120)
        self.multi_cell(0, 8, text)
        self.ln(2)

    def h2(self, text: str) -> None:
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, text)
        self.ln(1)

    def h3(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "", 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "", 9)
        self.multi_cell(0, 5, f"  - {text}")

    def table_row(self, cols: list[str], widths: list[int], bold: bool = False) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "B" if bold else "", 7)
        for col, w in zip(cols, widths):
            txt = col[:36] + ".." if len(col) > 38 else col
            self.cell(w, 6.5, txt, border=1)
        self.ln()

    def profile_box(self, title: str, color: tuple[int, int, int]) -> None:
        self.set_x(self.l_margin)
        self.set_fill_color(*color)
        self.set_font("Arial", "B", 10)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, f"  {title}", fill=True)
        self.ln(8)
        self.set_text_color(30, 30, 30)


def build() -> None:
    pdf = InfraPDF()
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    u = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.h1("Solicitacao de Infraestrutura")
    pdf.h2("AI Token Suppressor - 200+ usuarios, modo ULTRA")
    pdf.body(
        "Middleware de compressao de prompts antes do envio a LLMs (Claude, GPT, Groq).\n"
        "Cenario: 200+ colaboradores, estrategia ultra + Ollama em todas as requisicoes.\n"
        "Junho/2026"
    )

    pdf.h2("Resumo: tres perfis")
    w4 = [int(u * 0.22), int(u * 0.26), int(u * 0.26), int(u * 0.26)]
    pdf.table_row(["Perfil", "RAM", "Disco SSD", "vCPU"], w4, bold=True)
    pdf.table_row(["MINIMO", "16 GB", "80 GB", "4"], w4)
    pdf.table_row(["RECOMENDADO", "32 GB", "120 GB", "8"], w4)
    pdf.table_row(["IDEAL (rodar liso)", "48-64 GB", "250 GB", "16"], w4)
    pdf.body(
        "NAO usar VPS 4 GB para este cenario. Perfil RECOMENDADO e a sugestao "
        "para aprovacao em producao. Perfil IDEAL elimina filas longas e lentidao em pico."
    )

    pdf.h2("Tabela comparativa completa")
    wc = [int(u * 0.20), int(u * 0.27), int(u * 0.27), int(u * 0.26)]
    pdf.table_row(["Criterio", "Minimo", "Recomendado", "Ideal"], wc, bold=True)
    compare = [
        ("RAM total", "16 GB", "32 GB", "48-64 GB"),
        ("Disco SSD", "80 GB", "120 GB", "250 GB"),
        ("vCPU", "4", "8", "16"),
        ("GPU", "Nao", "Opcional", "Recomendada"),
        ("Servidores", "1", "1 ou 2", "2-3"),
        ("Instancias Ollama", "1x 3B", "1x 3B", "2x 3B ou GPU"),
        ("Replicas API", "1", "2", "3"),
        ("Workers Celery", "0-1", "2", "4"),
        ("Redis cache", "512 MB", "2 GB", "4 GB"),
        ("Monitoramento", "Nao", "Sim", "Sim+alertas"),
        ("Ultra ~1700 tokens", "30-90 s", "15-45 s", "3-25 s"),
        ("200 users ultra", "Arriscado", "Sim", "Folgado"),
        ("Fila em pico", "Longa", "Moderada", "Curta/rara"),
        ("Disponibilidade", "~95%", "~99%", "99,5%+"),
        ("Custo cloud ref.", "R$300-600", "R$800-1500", "R$2k-4k/mes"),
    ]
    for row in compare:
        pdf.table_row(list(row), wc)

    # --- MINIMO ---
    pdf.add_page()
    pdf.profile_box("PERFIL MINIMO - Viavel com limitacoes", (180, 80, 30))
    pdf.body(
        "Para: piloto ou ate ~50 usuarios ativos no pico; 200 usuarios com fila "
        "e espera de 1-3 min por compressao."
    )
    pdf.h3("Hardware minimo")
    pdf.bullet("RAM: 16 GB (1 servidor)")
    pdf.bullet("vCPU: 4 cores")
    pdf.bullet("Disco: 80 GB SSD")
    pdf.bullet("Rede: 100 Mbps")
    pdf.h3("Software obrigatorio")
    pdf.bullet("Docker 24+, Compose v2, PostgreSQL 15+ pgvector")
    pdf.bullet("Redis 7, Ollama llama3.2:3b (1 instancia), Nginx+SSL")
    pdf.bullet("Containers: redis + api + frontend (sem Grafana)")
    pdf.h3("Comportamento esperado")
    pdf.bullet("Compressao ultra 1700 tokens: 30-90 segundos")
    pdf.bullet("Pico: fila longa; swap possivel")
    pdf.bullet("Disponibilidade ~95%")

    # --- RECOMENDADO ---
    pdf.ln(3)
    pdf.profile_box("PERFIL RECOMENDADO - Producao 200+ usuarios", (30, 120, 60))
    pdf.body(
        "Para: producao oficial. SUGESTAO PARA APROVACAO DO GERENTE."
    )
    pdf.h3("Hardware recomendado")
    pdf.bullet("RAM: 32 GB")
    pdf.bullet("vCPU: 8 cores")
    pdf.bullet("Disco: 120 GB SSD/NVMe")
    pdf.bullet("Rede: 500 Mbps - 1 Gbps")
    pdf.h3("Arquitetura (preferir 2 servidores)")
    pdf.bullet("Servidor App 16 GB: API x2, Redis, Postgres, Nginx, Celery")
    pdf.bullet("Servidor Inferencia 16 GB: so Ollama (3B + nomic-embed)")
    pdf.h3("Software adicional")
    pdf.bullet("Celery 2 workers, Prometheus + Grafana, backup diario")
    pdf.h3("Comportamento esperado")
    pdf.bullet("Compressao ultra 1700 tokens: 15-45 segundos")
    pdf.bullet("Cache Redis 2 GB: repetidos em menos de 1 s")
    pdf.bullet("Disponibilidade alvo 99%")

    # --- IDEAL ---
    pdf.add_page()
    pdf.profile_box("PERFIL IDEAL - Rodar liso (sem gargalo)", (30, 80, 160))
    pdf.body(
        "Para: 200+ usuarios sem fila perceptivel, compressao rapida, "
        "crescimento ate 500 usuarios, SLA alto."
    )
    pdf.h3("Hardware ideal")
    pdf.bullet("RAM: 48-64 GB total")
    pdf.bullet("vCPU: 16 cores")
    pdf.bullet("Disco: 250 GB NVMe")
    pdf.bullet("GPU opcional: 16 GB VRAM (ultra em 3-8 s)")
    pdf.bullet("Rede: 1 Gbps")
    pdf.h3("Arquitetura ideal")
    pdf.bullet("API: 3 replicas com load balancer")
    pdf.bullet("Ollama: 2 instancias 3B OU 1 GPU com modelo 7B")
    pdf.bullet("Redis 4 GB, Postgres 8 GB RAM, Celery 4 workers")
    pdf.bullet("Monitoramento + alertas (Slack/email)")
    pdf.bullet("Backup horario Postgres, ambiente homolog 8 GB")
    pdf.h3("Comportamento - rodar liso")
    pdf.bullet("Ultra 1700 tokens: 3-15 s (GPU) ou 10-25 s (2x Ollama CPU)")
    pdf.bullet("Pico 30 req: p95 menor que 30 s")
    pdf.bullet("Cache hit: menos de 500 ms")
    pdf.bullet("Swap: 0% em operacao normal")
    pdf.bullet("Disponibilidade alvo 99,5%+")

    pdf.h2("Stack tecnica (todos os perfis)")
    w3 = [int(u * 0.35), int(u * 0.65)]
    pdf.table_row(["Componente", "Funcao"], w3, bold=True)
    stack = [
        ("Docker 24+ / Compose v2", "Orquestracao"),
        ("PostgreSQL 15+ pgvector", "Dados e busca vetorial"),
        ("Redis 7", "Cache + fila Celery"),
        ("Ollama", "Compressao ultra local"),
        ("Nginx + SSL", "HTTPS"),
        ("Chaves LLM (Groq, OpenAI...)", "Apos compressao"),
    ]
    for r in stack:
        pdf.table_row(list(r), w3)

    pdf.h2("Armazenamento (ano 1)")
    pdf.table_row(["Item", "Min | Rec | Ideal"], [int(u * 0.45), int(u * 0.55)], bold=True)
    for r in [
        ("SO + Docker", "15 | 20 | 25 GB"),
        ("Modelos Ollama", "3 | 5 | 8 GB"),
        ("PostgreSQL", "5 | 15 | 40 GB"),
        ("Redis, logs, backup", "15 | 40 | 80 GB"),
        ("TOTAL disco", "80 | 120 | 250 GB"),
    ]:
        pdf.table_row(list(r), [int(u * 0.45), int(u * 0.55)])

    pdf.h2("Texto para solicitacao formal")
    pdf.body(
        "Solicito provisionamento do AI Token Suppressor para mais de 200 usuarios "
        "em modo ultra (maxima economia de tokens com Ollama).\n\n"
        "Opcoes apresentadas:\n"
        "1) MINIMO - 16 GB RAM, 80 GB SSD, 4 vCPU - viavel com filas.\n"
        "2) RECOMENDADO - 32 GB RAM, 120 GB SSD, 8 vCPU - producao estavel. "
        "SUGIRO ESTA OPCAO.\n"
        "3) IDEAL (rodar liso) - 48-64 GB RAM, 250 GB SSD, 16 vCPU, GPU opcional - "
        "sem gargalo e pronto para crescimento.\n\n"
        "O ambiente atual de 4 GB nao atende este cenario."
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"PDF gerado: {OUT}")


if __name__ == "__main__":
    build()
