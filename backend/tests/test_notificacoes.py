"""Notificações para atividades delegadas (Seção 4): campo oficial
responsavel_id da Rotina e "Responsável" embutido dentro do Relatório
Comercial (plano de ação, riscos, blocos repetíveis etc.)."""
from datetime import date, timedelta

from backend.extensions import db
from backend.models import Notificacao
from backend.tests.conftest import auth_headers


def _time(factory):
    regional = factory.regional()
    dono = factory.usuario('Dono', 'dono@teste.com', 'gv', regional_id=regional.id)
    colega = factory.usuario('Colega', 'colega@teste.com', 'cd', regional_id=regional.id)
    atividade = factory.atividade('Plano de Ação Semanal', 'mensal', 'gv', obrigatoria=True)
    # Período deliberadamente no futuro (relativo a hoje de verdade, sem
    # freeze_time) — garante que a rotina nunca esteja "vencida" durante o
    # teste, não importa quando a suíte for executada.
    hoje = date.today()
    rotina = factory.rotina(dono, atividade, hoje, hoje + timedelta(days=30), status='em_andamento')
    return dono, colega, rotina


def test_delegar_responsavel_da_rotina_notifica_o_colega(app, client, factory):
    dono, colega, rotina = _time(factory)

    r = client.put(
        f'/api/rotinas/{rotina.id}',
        headers=auth_headers(dono),
        json={'responsavel_id': colega.id},
    )
    assert r.status_code == 200
    assert r.get_json()['responsavel_id'] == colega.id
    assert r.get_json()['responsavel_nome'] == 'Colega'

    notifs = Notificacao.query.filter_by(usuario_id=colega.id, rotina_id=rotina.id).all()
    assert len(notifs) == 1
    assert notifs[0].lida is False


def test_resalvar_com_mesmo_responsavel_nao_duplica_notificacao_nao_lida(app, client, factory):
    dono, colega, rotina = _time(factory)
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id})
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id, 'comentario': 'ping'})

    assert Notificacao.query.filter_by(usuario_id=colega.id, rotina_id=rotina.id).count() == 1


def test_visualizar_atividade_marca_notificacao_como_lida(app, client, factory):
    dono, colega, rotina = _time(factory)
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id})

    r = client.get(f'/api/rotinas/{rotina.id}', headers=auth_headers(colega))
    assert r.status_code == 200  # colega não é dono nem SR, mas foi delegado

    notif = Notificacao.query.filter_by(usuario_id=colega.id, rotina_id=rotina.id).first()
    assert notif.lida is True


def test_concluir_atividade_marca_notificacoes_como_lidas(app, client, factory):
    dono, colega, rotina = _time(factory)
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id})

    # completa os pré-requisitos e conclui
    rotina.formulario_preenchido = True
    from backend.models import Evidencia
    db.session.add(Evidencia(rotina_id=rotina.id, nome_arquivo='a.pdf', url='/uploads/a.pdf', tipo='application/pdf'))
    db.session.commit()

    r = client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'status': 'concluida'})
    assert r.status_code == 200

    notif = Notificacao.query.filter_by(usuario_id=colega.id, rotina_id=rotina.id).first()
    assert notif.lida is True


def test_colega_sem_delegacao_nao_acessa_rotina_de_outro(app, client, factory):
    dono, colega, rotina = _time(factory)
    r = client.get(f'/api/rotinas/{rotina.id}', headers=auth_headers(colega))
    assert r.status_code == 403


def test_responsavel_dentro_do_relatorio_comercial_tambem_notifica(app, client, factory):
    """Campo "Responsável" de um item de plano de ação dentro do Relatório
    Comercial (JSON livre) — não é o responsavel_id oficial da rotina."""
    dono, colega, rotina = _time(factory)

    formulario = {
        'plano_acao': [
            {'acao': 'Revisar indicadores', 'responsavel': 'Colega', 'responsavel_id': colega.id, 'prazo': '2026-08-01'},
        ]
    }
    r = client.put(
        f'/api/rotinas/{rotina.id}/formulario',
        headers=auth_headers(dono),
        json={'formulario': formulario},
    )
    assert r.status_code == 200

    notifs = Notificacao.query.filter_by(usuario_id=colega.id, rotina_id=rotina.id).all()
    assert len(notifs) == 1
    assert 'relatório' in notifs[0].mensagem.lower()

    # e o colega agora consegue abrir a atividade a partir da notificação
    r2 = client.get(f'/api/rotinas/{rotina.id}', headers=auth_headers(colega))
    assert r2.status_code == 200


def test_dono_preenchendo_relatorio_sem_delegar_nao_gera_notificacao_para_si_mesmo(app, client, factory):
    dono, colega, rotina = _time(factory)
    formulario = {'plano_acao': [{'acao': 'Ação própria', 'responsavel': 'Dono', 'responsavel_id': dono.id}]}
    r = client.put(f'/api/rotinas/{rotina.id}/formulario', headers=auth_headers(dono), json={'formulario': formulario})
    assert r.status_code == 200
    assert Notificacao.query.filter_by(rotina_id=rotina.id).count() == 0


def test_endpoints_de_notificacoes(app, client, factory):
    dono, colega, rotina = _time(factory)
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id})

    r_contagem = client.get('/api/notificacoes/nao-lidas/contagem', headers=auth_headers(colega))
    assert r_contagem.get_json()['total'] == 1

    r_lista = client.get('/api/notificacoes/', headers=auth_headers(colega))
    assert len(r_lista.get_json()) == 1
    nid = r_lista.get_json()[0]['id']

    r_marcar = client.post(f'/api/notificacoes/{nid}/marcar-lida', headers=auth_headers(colega))
    assert r_marcar.status_code == 200
    assert r_marcar.get_json()['lida'] is True

    r_contagem2 = client.get('/api/notificacoes/nao-lidas/contagem', headers=auth_headers(colega))
    assert r_contagem2.get_json()['total'] == 0


def test_outro_usuario_nao_pode_marcar_notificacao_alheia_como_lida(app, client, factory):
    dono, colega, rotina = _time(factory)
    client.put(f'/api/rotinas/{rotina.id}', headers=auth_headers(dono), json={'responsavel_id': colega.id})
    nid = Notificacao.query.filter_by(usuario_id=colega.id).first().id

    r = client.post(f'/api/notificacoes/{nid}/marcar-lida', headers=auth_headers(dono))
    assert r.status_code == 403
