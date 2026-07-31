"""Regressão dos bugs reportados: Checklist Diário sumindo e Relatório Diário
fechando às 21h. Causa raiz: o servidor roda em UTC e o código usava
date.today()/datetime.now(timezone.utc).date() para decidir "hoje", em vez do
fuso de Brasília — entre 21h e meia-noite (horário de Brasília) o servidor já
considerava que o dia tinha virado, 3h antes da hora real."""
from datetime import date, timedelta

from freezegun import freeze_time

from backend.utils.dates import hoje_br
from backend.models import Rotina


def test_hoje_br_ainda_e_o_dia_anterior_as_21h30_horario_de_brasilia():
    # 2026-07-30 00:30 UTC == 2026-07-29 21:30 em Brasília (UTC-3).
    with freeze_time('2026-07-30 00:30:00'):
        assert hoje_br() == date(2026, 7, 29)


def test_hoje_br_vira_o_dia_a_meia_noite_de_brasilia_nao_de_utc():
    # 2026-07-30 03:00 UTC == 2026-07-30 00:00 em Brasília: só agora é amanhã.
    with freeze_time('2026-07-30 03:00:00'):
        assert hoje_br() == date(2026, 7, 30)


def test_hoje_br_pouco_antes_da_virada_ainda_e_o_dia_anterior():
    with freeze_time('2026-07-30 02:59:59'):
        assert hoje_br() == date(2026, 7, 29)


def _rotina_diaria(factory, dia):
    regional = factory.regional()
    usuario = factory.usuario('Coordenador', 'coord@teste.com', 'cd', regional_id=regional.id)
    atividade = factory.atividade('Checklist Diário', 'diaria', 'cd', obrigatoria=True)
    return factory.rotina(usuario, atividade, dia, dia, status='nao_iniciada')


def test_checklist_diario_nao_fica_vencido_as_21h30_de_brasilia(app, factory):
    """Reprodução exata do bug: às 21h30 (horário de Brasília) do próprio dia,
    o checklist diário (sem folga configurada) NÃO pode aparecer como vencido —
    ainda faltam quase 3h para o dia acabar em Brasília."""
    with freeze_time('2026-07-29 12:00:00'):
        rotina = _rotina_diaria(factory, date(2026, 7, 29))

    with freeze_time('2026-07-30 00:30:00'):  # 21h30 de Brasília, 29/07
        assert rotina.prazo_limite == date(2026, 7, 29)
        assert rotina.to_dict()['vencida'] is False
        assert rotina.to_dict()['pendente_prazo'] is False


def test_checklist_diario_fica_vencido_somente_apos_meia_noite_de_brasilia(app, factory):
    with freeze_time('2026-07-29 12:00:00'):
        rotina = _rotina_diaria(factory, date(2026, 7, 29))

    with freeze_time('2026-07-30 03:30:00'):  # 00h30 de Brasília, 30/07 — dia virou de verdade
        assert rotina.to_dict()['vencida'] is True
        assert rotina.to_dict()['pendente_prazo'] is True


def test_relatorio_diario_nao_bloqueia_preenchimento_as_21h_de_brasilia(app, client, factory):
    """Reprodução do relato da Aline: preencher por volta das 21h não pode
    devolver "atividade vencida"."""
    from backend.tests.conftest import auth_headers

    with freeze_time('2026-07-29 12:00:00'):
        rotina = _rotina_diaria(factory, date(2026, 7, 29))
        usuario = rotina.usuario

    with freeze_time('2026-07-30 00:05:00'):  # 21h05 de Brasília
        headers = auth_headers(usuario)
        r = client.put(
            f'/api/rotinas/{rotina.id}',
            headers=headers,
            json={'status': 'em_andamento', 'comentario': 'Preenchendo às 21h'},
        )
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'em_andamento'
