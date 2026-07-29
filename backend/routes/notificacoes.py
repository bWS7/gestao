from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.models import Notificacao, Usuario
from backend.utils.dates import get_now_br
from backend.extensions import db

notificacoes_bp = Blueprint('notificacoes', __name__)


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


@notificacoes_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    me = get_current_user()
    apenas_nao_lidas = request.args.get('nao_lidas', '').lower() in ('1', 'true')
    limite = min(request.args.get('limite', 30, type=int), 100)

    query = Notificacao.query.filter_by(usuario_id=me.id)
    if apenas_nao_lidas:
        query = query.filter_by(lida=False)
    notificacoes = query.order_by(Notificacao.criado_em.desc()).limit(limite).all()
    return jsonify([n.to_dict() for n in notificacoes])


@notificacoes_bp.route('/nao-lidas/contagem', methods=['GET'])
@jwt_required()
def contar_nao_lidas():
    me = get_current_user()
    total = Notificacao.query.filter_by(usuario_id=me.id, lida=False).count()
    return jsonify({'total': total})


@notificacoes_bp.route('/<int:nid>/marcar-lida', methods=['POST'])
@jwt_required()
def marcar_lida(nid):
    me = get_current_user()
    n = Notificacao.query.get_or_404(nid)
    if n.usuario_id != me.id:
        return jsonify({'erro': 'Acesso negado'}), 403
    if not n.lida:
        n.lida = True
        n.lida_em = get_now_br()
        db.session.commit()
    return jsonify(n.to_dict())


@notificacoes_bp.route('/marcar-todas-lidas', methods=['POST'])
@jwt_required()
def marcar_todas_lidas():
    me = get_current_user()
    pendentes = Notificacao.query.filter_by(usuario_id=me.id, lida=False).all()
    for n in pendentes:
        n.lida = True
        n.lida_em = get_now_br()
    db.session.commit()
    return jsonify({'total_marcadas': len(pendentes)})
