"""Geração automática de rotinas — garante que o Checklist Diário (e as demais
periodicidades) seja gerado para todos os dias do mês, de forma idempotente."""
from datetime import date, timedelta

from freezegun import freeze_time

from backend.extensions import db
from backend.models import Rotina
from backend.routes.rotinas import ensure_rotinas_atuais, ensure_rotinas_mes


def test_ensure_rotinas_mes_gera_todos_os_dias_do_mes_para_atividade_diaria(app, factory):
    regional = factory.regional()
    usuario = factory.usuario('Coordenador', 'coord@teste.com', 'cd', regional_id=regional.id)
    factory.atividade('Checklist Diário', 'diaria', 'cd', obrigatoria=True)

    with freeze_time('2026-07-15 12:00:00'):
        criadas = ensure_rotinas_mes(usuario, date(2026, 7, 15))

    assert criadas == 31  # julho tem 31 dias
    dias = {r.periodo_inicio for r in Rotina.query.filter_by(usuario_id=usuario.id, periodicidade='diaria').all()}
    assert dias == {date(2026, 7, d) for d in range(1, 32)}


def test_ensure_rotinas_mes_e_idempotente(app, factory):
    regional = factory.regional()
    usuario = factory.usuario('Coordenador', 'coord@teste.com', 'cd', regional_id=regional.id)
    factory.atividade('Checklist Diário', 'diaria', 'cd', obrigatoria=True)

    with freeze_time('2026-07-15 12:00:00'):
        primeira = ensure_rotinas_mes(usuario, date(2026, 7, 15))
        segunda = ensure_rotinas_mes(usuario, date(2026, 7, 15))

    assert primeira == 31
    assert segunda == 0  # nada duplicado
    assert Rotina.query.filter_by(usuario_id=usuario.id, periodicidade='diaria').count() == 31


def test_ensure_rotinas_atuais_gera_checklist_do_dia_corrente(app, factory):
    regional = factory.regional()
    usuario = factory.usuario('Coordenador', 'coord@teste.com', 'cd', regional_id=regional.id)
    factory.atividade('Checklist Diário', 'diaria', 'cd', obrigatoria=True)

    # Mesmo às 21h30 de Brasília (00h30 UTC do dia seguinte), o checklist
    # gerado precisa ser o do dia ainda corrente em Brasília — não o de amanhã.
    with freeze_time('2026-07-30 00:30:00'):
        ensure_rotinas_atuais(usuario)

    rotinas = Rotina.query.filter_by(usuario_id=usuario.id, periodicidade='diaria').all()
    assert len(rotinas) == 1
    assert rotinas[0].periodo_inicio == date(2026, 7, 29)


def test_checklist_gerado_para_um_dia_nao_desaparece_no_dia_seguinte(app, factory):
    """Cenário relatado: "um dia aparece, no dia seguinte não é gerado". Gera o
    mês inteiro uma vez (como ensure_rotinas_mes faz ao abrir Minhas Rotinas) e
    confirma que cada dia individual continua existindo e acessível depois."""
    regional = factory.regional()
    usuario = factory.usuario('Coordenador', 'coord@teste.com', 'cd', regional_id=regional.id)
    factory.atividade('Checklist Diário', 'diaria', 'cd', obrigatoria=True)

    with freeze_time('2026-07-01 08:00:00'):
        ensure_rotinas_mes(usuario, date(2026, 7, 1))

    for dia in range(1, 32):
        rotina = Rotina.query.filter_by(
            usuario_id=usuario.id, periodicidade='diaria', periodo_inicio=date(2026, 7, dia)
        ).first()
        assert rotina is not None, f'dia {dia}/07 não foi gerado'
