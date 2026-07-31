"""Relatório Comparativo das Rotinas dos Liderados (Seção 3)."""
from datetime import date

from freezegun import freeze_time

from backend.tests.conftest import auth_headers

# "Hoje" fixo dentro da semana de gv2 (07/07, ainda dentro do período e da
# folga) — deixa a segunda rotina de gv2 claramente "pendente", não "atrasada".
REFERENCIA = '2026-07-05 12:00:00'


def _preparar_time(factory):
    regional = factory.regional('Regional Sul')
    sr = factory.usuario('Super', 'sr@teste.com', 'sr', regional_id=regional.id)
    gv1 = factory.usuario('GV Um', 'gv1@teste.com', 'gv', regional_id=regional.id)
    gv2 = factory.usuario('GV Dois', 'gv2@teste.com', 'gv', regional_id=regional.id)
    atividade = factory.atividade('Relatório Semanal', 'semanal', 'gv', obrigatoria=True)

    inicio, fim = date(2026, 7, 1), date(2026, 7, 7)
    # gv1: 2 de 2 concluídas -> 100%
    factory.rotina(gv1, atividade, inicio, fim, status='concluida')
    factory.rotina(gv1, atividade, inicio, fim, status='concluida')
    # gv2: 1 concluída, 1 ainda pendente (dentro do prazo) -> 50%
    factory.rotina(gv2, atividade, inicio, fim, status='concluida')
    factory.rotina(gv2, atividade, inicio, fim, status='nao_iniciada')
    return sr, gv1, gv2, regional


def test_sr_ve_liderados_da_propria_regional_sem_precisar_informar_regional_id(app, client, factory):
    with freeze_time(REFERENCIA):
        sr, gv1, gv2, _ = _preparar_time(factory)
        r = client.get(
            '/api/rotinas/relatorio-liderados?data_inicio=2026-07-01&data_fim=2026-07-31',
            headers=auth_headers(sr),
        )
        assert r.status_code == 200
        dados = r.get_json()
        nomes = {l['nome']: l for l in dados['liderados']}
        assert nomes['GV Um']['percentual_execucao'] == 100.0
        assert nomes['GV Um']['concluidas'] == 2
        assert nomes['GV Dois']['concluidas'] == 1
        assert nomes['GV Dois']['pendentes'] == 1
        assert nomes['GV Dois']['atrasadas'] == 0
        assert nomes['GV Dois']['percentual_execucao'] == 50.0
        assert dados['totais']['total'] == 4


def test_admin_sem_regional_id_recebe_erro_claro(app, client, factory):
    """Regressão: a tela quebrava para admin porque ele não tem regional
    própria (diferente do SR, resolvido automaticamente pelo backend)."""
    factory.regional()
    admin = factory.usuario('Admin', 'admin@teste.com', 'admin', regional_id=None)
    r = client.get('/api/rotinas/relatorio-liderados', headers=auth_headers(admin))
    assert r.status_code == 400
    assert 'regional' in r.get_json()['erro'].lower()


def test_admin_com_regional_id_funciona(app, client, factory):
    with freeze_time(REFERENCIA):
        sr, gv1, gv2, regional = _preparar_time(factory)
        admin = factory.usuario('Admin', 'admin@teste.com', 'admin', regional_id=None)
        r = client.get(
            f'/api/rotinas/relatorio-liderados?regional_id={regional.id}&data_inicio=2026-07-01&data_fim=2026-07-31',
            headers=auth_headers(admin),
        )
        assert r.status_code == 200
        assert len(r.get_json()['liderados']) == 2


def test_gv_nao_pode_acessar_relatorio_comparativo(app, client, factory):
    sr, gv1, gv2, _ = _preparar_time(factory)
    r = client.get('/api/rotinas/relatorio-liderados', headers=auth_headers(gv1))
    assert r.status_code == 403


def test_export_csv_e_pdf(app, client, factory):
    with freeze_time(REFERENCIA):
        sr, gv1, gv2, _ = _preparar_time(factory)
        r_csv = client.get(
            '/api/rotinas/relatorio-liderados/export?formato=csv&data_inicio=2026-07-01&data_fim=2026-07-31',
            headers=auth_headers(sr),
        )
        assert r_csv.status_code == 200
        assert r_csv.content_type.startswith('text/csv')

        r_pdf = client.get(
            '/api/rotinas/relatorio-liderados/export?formato=pdf&data_inicio=2026-07-01&data_fim=2026-07-31',
            headers=auth_headers(sr),
        )
        assert r_pdf.status_code == 200
        assert r_pdf.content_type == 'application/pdf'
        assert len(r_pdf.data) > 0
