import csv
import io
import os
import uuid
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from backend.audit import log_audit
from backend.models import Rotina, AtividadeCatalogo, Usuario, HistoricoRotina, Evidencia, AuditLog
from backend.extensions import db
from datetime import date, timedelta, datetime, timezone
from dateutil.relativedelta import relativedelta

rotinas_bp = Blueprint('rotinas', __name__)


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


def can_access_rotina(me, rotina):
    if me.perfil == 'admin':
        return True
    if me.perfil == 'sr':
        return rotina.usuario and rotina.usuario.regional_id == me.regional_id
    return rotina.usuario_id == me.id


def add_rotina_history(rotina, usuario_id, acao, observacao=None, status_anterior=None, status_novo=None):
    hist = HistoricoRotina(
        rotina_id=rotina.id,
        usuario_id=usuario_id,
        acao=acao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        observacao=observacao
    )
    db.session.add(hist)


def allowed_file(filename):
    extensoes = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensoes


def get_periodo(tipo, referencia=None):
    hoje = referencia or date.today()
    if tipo == 'semanal':
        inicio = hoje - timedelta(days=hoje.weekday())
        fim = inicio + timedelta(days=6)
    elif tipo == 'quinzenal':
        if hoje.day <= 15:
            inicio = hoje.replace(day=1)
            fim = hoje.replace(day=15)
        else:
            inicio = hoje.replace(day=16)
            ultimo = (hoje.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
            fim = ultimo
    else:  # mensal
        inicio = hoje.replace(day=1)
        ultimo = (hoje.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        fim = ultimo
    return inicio, fim


@rotinas_bp.route('/gerar', methods=['POST'])
@jwt_required()
def gerar_rotinas():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    data = request.get_json() or {}
    usuario_ids = data.get('usuario_ids')  # None = todos
    referencia_str = data.get('referencia')
    referencia = date.fromisoformat(referencia_str) if referencia_str else date.today()

    query = Usuario.query.filter_by(status='ativo')
    if usuario_ids:
        query = query.filter(Usuario.id.in_(usuario_ids))
    usuarios = query.all()

    criadas = 0
    for usuario in usuarios:
        atividades = AtividadeCatalogo.query.filter_by(perfil=usuario.perfil, ativo=True).all()
        for atividade in atividades:
            inicio, fim = get_periodo(atividade.periodicidade, referencia)
            existe = Rotina.query.filter_by(
                usuario_id=usuario.id,
                atividade_id=atividade.id,
                periodo_inicio=inicio
            ).first()
            if not existe:
                r = Rotina(
                    usuario_id=usuario.id,
                    atividade_id=atividade.id,
                    periodo_inicio=inicio,
                    periodo_fim=fim,
                    periodicidade=atividade.periodicidade
                )
                db.session.add(r)
                criadas += 1

    db.session.commit()
    return jsonify({'mensagem': f'{criadas} rotinas geradas com sucesso', 'total': criadas})


@rotinas_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    me = get_current_user()

    usuario_id = request.args.get('usuario_id', type=int)
    regional_id = request.args.get('regional_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status = request.args.get('status')
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')

    referencia = date.fromisoformat(data_ref) if data_ref else date.today()
    inicio, fim = get_periodo(periodo, referencia)

    query = Rotina.query.join(Usuario).filter(
        Rotina.periodo_inicio >= inicio,
        Rotina.periodo_fim <= fim
    )

    # Visibilidade por hierarquia
    if me.perfil == 'admin':
        if usuario_id:
            query = query.filter(Rotina.usuario_id == usuario_id)
        if regional_id:
            query = query.filter(Usuario.regional_id == regional_id)
    elif me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
        if usuario_id:
            query = query.filter(Rotina.usuario_id == usuario_id)
    elif me.perfil == 'gv':
        query = query.filter(Rotina.usuario_id == me.id)
    else:
        query = query.filter(Rotina.usuario_id == me.id)

    if periodicidade:
        query = query.filter(Rotina.periodicidade == periodicidade)
    if status:
        query = query.filter(Rotina.status == status)

    rotinas = query.order_by(Rotina.periodo_inicio.desc()).all()
    return jsonify([r.to_dict() for r in rotinas])


@rotinas_bp.route('/<int:rid>', methods=['GET'])
@jwt_required()
def obter(rid):
    me = get_current_user()
    r = Rotina.query.get_or_404(rid)
    if not can_access_rotina(me, r):
        return jsonify({'erro': 'Acesso negado'}), 403
    return jsonify(r.to_dict())


@rotinas_bp.route('/<int:rid>', methods=['PUT'])
@jwt_required()
def atualizar(rid):
    me = get_current_user()
    r = Rotina.query.get_or_404(rid)

    if not can_access_rotina(me, r):
        return jsonify({'erro': 'Acesso negado'}), 403

    data = request.get_json()
    status_anterior = r.status

    if 'status' in data:
        r.status = data['status']
        if data['status'] == 'concluida' and not r.data_conclusao:
            r.data_conclusao = datetime.now(timezone.utc)
        elif data['status'] != 'concluida':
            r.data_conclusao = None

    if 'comentario' in data:
        r.comentario = data['comentario']
    if 'justificativa' in data:
        r.justificativa = data['justificativa']
    if 'acao_corretiva' in data:
        r.acao_corretiva = data['acao_corretiva']
    if 'novo_prazo' in data:
        r.novo_prazo = date.fromisoformat(data['novo_prazo']) if data['novo_prazo'] else None
    if 'responsavel_acao' in data:
        r.responsavel_acao = data['responsavel_acao']
    if 'checklist' in data:
        r.checklist = data['checklist']
    if 'relatorio' in data:
        r.relatorio = data['relatorio']
    if 'plano_semana' in data:
        r.plano_semana = data['plano_semana']
    if 'visitas_ativacoes' in data:
        r.visitas_ativacoes = data['visitas_ativacoes']
    if 'resultados_visita' in data:
        r.resultados_visita = data['resultados_visita']
    if 'carteira_ativa' in data:
        r.carteira_ativa = data['carteira_ativa']
    if 'metas_canal' in data:
        r.metas_canal = data['metas_canal']

    if r.status == 'nao_realizada' and (not r.justificativa or not r.acao_corretiva):
        return jsonify({'erro': 'Justificativa e plano de ação são obrigatórios para atividades não realizadas'}), 400

    if status_anterior != r.status:
        add_rotina_history(
            r,
            me.id,
            'mudanca_status',
            observacao=data.get('comentario'),
            status_anterior=status_anterior,
            status_novo=r.status
        )

    if any(chave in data for chave in ['comentario', 'justificativa', 'acao_corretiva', 'novo_prazo', 'responsavel_acao', 'checklist', 'relatorio', 'plano_semana', 'visitas_ativacoes', 'resultados_visita', 'carteira_ativa', 'metas_canal']):
        add_rotina_history(
            r,
            me.id,
            'atualizacao_rotina',
            observacao=data.get('comentario') or data.get('justificativa') or 'Campos complementares atualizados',
            status_anterior=status_anterior,
            status_novo=r.status
        )

    log_audit(me.id, 'rotina', r.id, 'atualizar', {
        'status': r.status,
        'comentario': r.comentario,
        'justificativa': r.justificativa,
        'acao_corretiva': r.acao_corretiva,
        'novo_prazo': r.novo_prazo,
        'responsavel_acao': r.responsavel_acao,
        'checklist': r.checklist,
        'relatorio': r.relatorio,
        'plano_semana': r.plano_semana,
        'visitas_ativacoes': r.visitas_ativacoes,
        'resultados_visita': r.resultados_visita,
        'carteira_ativa': r.carteira_ativa,
        'metas_canal': r.metas_canal
    })

    db.session.commit()
    return jsonify(r.to_dict())


@rotinas_bp.route('/<int:rid>/evidencias', methods=['POST'])
@jwt_required()
def upload_evidencia(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)
    if not can_access_rotina(me, rotina):
        return jsonify({'erro': 'Acesso negado'}), 403

    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename:
        return jsonify({'erro': 'Arquivo é obrigatório'}), 400
    if not allowed_file(arquivo.filename):
        return jsonify({'erro': 'Tipo de arquivo não permitido'}), 400

    nome_seguro = secure_filename(arquivo.filename)
    nome_final = f"{rotina.id}_{uuid.uuid4().hex}_{nome_seguro}"
    caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_final)
    arquivo.save(caminho)

    evidencia = Evidencia(
        rotina_id=rotina.id,
        nome_arquivo=arquivo.filename,
        url=f"/uploads/{nome_final}",
        tipo=arquivo.mimetype or 'arquivo'
    )
    db.session.add(evidencia)
    db.session.flush()
    add_rotina_history(rotina, me.id, 'anexo_evidencia', observacao=arquivo.filename, status_anterior=rotina.status, status_novo=rotina.status)
    log_audit(me.id, 'evidencia', evidencia.id, 'criar', {'rotina_id': rotina.id, 'arquivo': arquivo.filename})
    db.session.commit()
    return jsonify(evidencia.to_dict()), 201


@rotinas_bp.route('/evidencias/<int:eid>', methods=['DELETE'])
@jwt_required()
def deletar_evidencia(eid):
    me = get_current_user()
    evidencia = Evidencia.query.get_or_404(eid)
    rotina = Rotina.query.get_or_404(evidencia.rotina_id)
    if not can_access_rotina(me, rotina):
        return jsonify({'erro': 'Acesso negado'}), 403

    if evidencia.url and evidencia.url.startswith('/uploads/'):
        caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], evidencia.url.split('/uploads/', 1)[1])
        if os.path.exists(caminho):
            os.remove(caminho)

    nome = evidencia.nome_arquivo
    db.session.delete(evidencia)
    add_rotina_history(rotina, me.id, 'remocao_evidencia', observacao=nome, status_anterior=rotina.status, status_novo=rotina.status)
    log_audit(me.id, 'evidencia', eid, 'excluir', {'rotina_id': rotina.id, 'arquivo': nome})
    db.session.commit()
    return jsonify({'mensagem': 'Evidência removida'})


@rotinas_bp.route('/<int:rid>/historico', methods=['GET'])
@jwt_required()
def historico_rotina(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)
    if not can_access_rotina(me, rotina):
        return jsonify({'erro': 'Acesso negado'}), 403

    historico = HistoricoRotina.query.filter_by(rotina_id=rid).order_by(HistoricoRotina.criado_em.desc()).all()
    return jsonify([h.to_dict() for h in historico])


@rotinas_bp.route('/audit-log', methods=['GET'])
@jwt_required()
def listar_auditoria():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    limite = min(request.args.get('limit', 100, type=int), 500)
    registros = AuditLog.query.order_by(AuditLog.criado_em.desc()).limit(limite).all()
    return jsonify([r.to_dict() for r in registros])


@rotinas_bp.route('/minha-aderencia', methods=['GET'])
@jwt_required()
def minha_aderencia():
    me = get_current_user()
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else date.today()
    inicio, fim = get_periodo(periodo, referencia)

    rotinas = Rotina.query.filter(
        Rotina.usuario_id == me.id,
        Rotina.periodo_inicio >= inicio,
        Rotina.periodo_fim <= fim
    ).all()

    total = len(rotinas)
    concluidas = sum(1 for r in rotinas if r.status == 'concluida')
    percentual = round((concluidas / total * 100), 1) if total else 0
    return jsonify({
        'periodo': periodo,
        'periodo_inicio': inicio.isoformat(),
        'periodo_fim': fim.isoformat(),
        'total': total,
        'concluidas': concluidas,
        'percentual_execucao': percentual
    })


def _export_csv(nome_arquivo, cabecalho, linhas):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(cabecalho)
    writer.writerows(linhas)
    mem = io.BytesIO(buffer.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=nome_arquivo)


@rotinas_bp.route('/export', methods=['GET'])
@jwt_required()
def exportar_rotinas():
    me = get_current_user()

    usuario_id = request.args.get('usuario_id', type=int)
    regional_id = request.args.get('regional_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status = request.args.get('status')
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else date.today()
    inicio, fim = get_periodo(periodo, referencia)

    query = Rotina.query.join(Usuario).filter(
        Rotina.periodo_inicio >= inicio,
        Rotina.periodo_fim <= fim
    )

    if me.perfil == 'admin':
        if regional_id:
            query = query.filter(Usuario.regional_id == regional_id)
        if usuario_id:
            query = query.filter(Rotina.usuario_id == usuario_id)
    elif me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
        if usuario_id:
            query = query.filter(Rotina.usuario_id == usuario_id)
    else:
        query = query.filter(Rotina.usuario_id == me.id)

    if periodicidade:
        query = query.filter(Rotina.periodicidade == periodicidade)
    if status:
        query = query.filter(Rotina.status == status)

    rotinas = query.order_by(Rotina.periodo_inicio.desc()).all()
    linhas = [[
        r.usuario_nome,
        r.atividade_nome,
        r.periodicidade,
        r.status,
        r.periodo_inicio.isoformat() if r.periodo_inicio else '',
        r.periodo_fim.isoformat() if r.periodo_fim else '',
        r.data_conclusao.isoformat() if r.data_conclusao else '',
        r.comentario or '',
        r.justificativa or '',
        r.acao_corretiva or '',
        len(r.evidencias)
    ] for r in rotinas]
    return _export_csv(
        f'rotinas_{periodo}.csv',
        ['Usuario', 'Atividade', 'Periodicidade', 'Status', 'Periodo Inicio', 'Periodo Fim', 'Conclusao', 'Comentario', 'Justificativa', 'Plano Acao', 'Qtde Evidencias'],
        linhas
    )


@rotinas_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    me = get_current_user()

    if me.perfil not in ['admin', 'sr']:
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id = request.args.get('regional_id', type=int)
    usuario_id = request.args.get('usuario_id', type=int)
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')

    referencia = date.fromisoformat(data_ref) if data_ref else date.today()
    inicio, fim = get_periodo(periodo, referencia)

    query = Rotina.query.join(Usuario).filter(
        Rotina.periodo_inicio >= inicio,
        Rotina.periodo_fim <= fim,
        Usuario.status == 'ativo'
    )

    if me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
    elif regional_id:
        query = query.filter(Usuario.regional_id == regional_id)

    if usuario_id and me.perfil in ['admin', 'sr']:
        query = query.filter(Rotina.usuario_id == usuario_id)

    rotinas = query.all()
    total = len(rotinas)
    concluidas = sum(1 for r in rotinas if r.status == 'concluida')
    nao_realizadas = sum(1 for r in rotinas if r.status == 'nao_realizada')
    em_andamento = sum(1 for r in rotinas if r.status == 'em_andamento')
    nao_iniciadas = sum(1 for r in rotinas if r.status == 'nao_iniciada')

    percentual = round((concluidas / total * 100), 1) if total > 0 else 0

    # Por perfil
    por_perfil = {}
    for r in rotinas:
        p = r.atividade.perfil if r.atividade else 'N/A'
        if p not in por_perfil:
            por_perfil[p] = {'total': 0, 'concluidas': 0}
        por_perfil[p]['total'] += 1
        if r.status == 'concluida':
            por_perfil[p]['concluidas'] += 1

    for p in por_perfil:
        t = por_perfil[p]['total']
        c = por_perfil[p]['concluidas']
        por_perfil[p]['percentual'] = round(c / t * 100, 1) if t > 0 else 0

    usuarios_query = Usuario.query.filter_by(status='ativo')
    if me.perfil == 'sr':
        usuarios_query = usuarios_query.filter_by(regional_id=me.regional_id)
    elif regional_id:
        usuarios_query = usuarios_query.filter_by(regional_id=regional_id)
    if usuario_id:
        usuarios_query = usuarios_query.filter_by(id=usuario_id)

    # Por usuário (ranking)
    por_usuario = {
        u.id: {
            'nome': u.nome,
            'regional': u.regional.nome if u.regional else 'N/A',
            'total': 0,
            'concluidas': 0
        }
        for u in usuarios_query.order_by(Usuario.nome).all()
    }

    for r in rotinas:
        uid = r.usuario_id
        if uid not in por_usuario:
            por_usuario[uid] = {
                'nome': r.usuario.nome if r.usuario else 'N/A',
                'regional': r.usuario.regional.nome if r.usuario and r.usuario.regional else 'N/A',
                'total': 0,
                'concluidas': 0
            }
        por_usuario[uid]['total'] += 1
        if r.status == 'concluida':
            por_usuario[uid]['concluidas'] += 1

    ranking = []
    for uid, info in por_usuario.items():
        t = info['total']
        c = info['concluidas']
        ranking.append({
            'usuario_id': uid,
            'nome': info['nome'],
            'regional': info['regional'],
            'total': t,
            'concluidas': c,
            'percentual': round(c / t * 100, 1) if t > 0 else 0
        })
    ranking.sort(key=lambda x: x['percentual'], reverse=True)

    return jsonify({
        'periodo': periodo,
        'periodo_inicio': inicio.isoformat(),
        'periodo_fim': fim.isoformat(),
        'total': total,
        'concluidas': concluidas,
        'nao_realizadas': nao_realizadas,
        'em_andamento': em_andamento,
        'nao_iniciadas': nao_iniciadas,
        'percentual_execucao': percentual,
        'por_perfil': por_perfil,
        'ranking': ranking
    })


@rotinas_bp.route('/dashboard/export', methods=['GET'])
@jwt_required()
def exportar_dashboard():
    me = get_current_user()
    if me.perfil not in ['admin', 'sr']:
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id = request.args.get('regional_id', type=int)
    usuario_id = request.args.get('usuario_id', type=int)
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else date.today()
    inicio, fim = get_periodo(periodo, referencia)

    query = Rotina.query.join(Usuario).filter(
        Rotina.periodo_inicio >= inicio,
        Rotina.periodo_fim <= fim,
        Usuario.status == 'ativo'
    )
    if me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
    elif regional_id:
        query = query.filter(Usuario.regional_id == regional_id)
    if usuario_id:
        query = query.filter(Rotina.usuario_id == usuario_id)

    rotinas = query.all()
    linhas = [[
        r.usuario_nome,
        r.usuario.regional.nome if r.usuario and r.usuario.regional else '',
        r.atividade_nome,
        r.periodicidade,
        r.status,
        r.data_conclusao.isoformat() if r.data_conclusao else ''
    ] for r in rotinas]
    return _export_csv(
        f'dashboard_{periodo}.csv',
        ['Usuario', 'Regional', 'Atividade', 'Periodicidade', 'Status', 'Conclusao'],
        linhas
    )


@rotinas_bp.route('/pendencias', methods=['GET'])
@jwt_required()
def pendencias():
    me = get_current_user()

    query = Rotina.query.join(Usuario).join(AtividadeCatalogo).filter(
        Rotina.status.in_(['nao_iniciada', 'em_andamento']),
        AtividadeCatalogo.obrigatoria == True,
        Rotina.periodo_fim < date.today()
    )

    if me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
    elif me.perfil not in ['admin']:
        query = query.filter(Rotina.usuario_id == me.id)

    rotinas = query.order_by(Rotina.periodo_fim).all()
    return jsonify([r.to_dict() for r in rotinas])
