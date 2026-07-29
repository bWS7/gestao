from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BR_TZ = ZoneInfo("America/Sao_Paulo")


def get_now_br():
    """Retorna o datetime atual em UTC para persistência no banco."""
    return datetime.now(timezone.utc)


def hoje_br():
    """Data de HOJE no fuso de Brasília (America/Sao_Paulo) — usada em toda a
    lógica de negócio que depende do "dia atual" (geração de rotinas, prazos,
    fechamento de período, checagem de vencida/liberada).

    O servidor (Railway) roda em UTC, 3h à frente de Brasília. Usar
    `date.today()`/`datetime.now(timezone.utc).date()` nessas contas faz o
    sistema considerar que o dia virou 3h mais cedo do que a realidade local
    — entre 21h e meia-noite (horário de Brasília) todo santo dia, "hoje" no
    servidor já é amanhã. Isso é o que fechava o Relatório Diário por volta
    das 21h (prazo sem folga da atividade diária já contado como vencido) e
    fazia o Checklist Diário sumir/virar "Não Realizada" antes da hora certa
    quando o cron batia nessa janela. Toda comparação de "hoje" para regras de
    negócio deve usar esta função, não `date.today()`."""
    return datetime.now(BR_TZ).date()
