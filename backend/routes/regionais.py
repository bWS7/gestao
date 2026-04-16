from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.audit import log_audit, diff_payload
from backend.models import Regional, Usuario
from backend.extensions import db

regionais_bp = Blueprint('regionais', __name__)


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


@regionais_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    ativo = request.args.get('ativo')
    query = Regional.query
    if ativo is not None:
        query = query.filter_by(ativo=(ativo.lower() == 'true'))
    regionais = query.order_by(Regional.nome).all()
    return jsonify([r.to_dict() for r in regionais])


@regionais_bp.route('/<int:rid>', methods=['GET'])
@jwt_required()
def obter(rid):
    r = Regional.query.get_or_404(rid)
    return jsonify(r.to_dict())


@regionais_bp.route('/', methods=['POST'])
@jwt_required()
def criar():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403
    data = request.get_json()
    r = Regional(nome=data['nome'], descricao=data.get('descricao'))
    db.session.add(r)
    db.session.commit()
    log_audit(me.id, 'regional', r.id, 'criar', r.to_dict())
    db.session.commit()
    return jsonify(r.to_dict()), 201


@regionais_bp.route('/<int:rid>', methods=['PUT'])
@jwt_required()
def atualizar(rid):
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403
    r = Regional.query.get_or_404(rid)
    before = r.to_dict()
    data = request.get_json()
    if 'nome' in data:
        r.nome = data['nome']
    if 'descricao' in data:
        r.descricao = data['descricao']
    if 'ativo' in data:
        r.ativo = data['ativo']
    after = r.to_dict()
    mudancas = diff_payload(before, after)
    if mudancas:
        log_audit(me.id, 'regional', r.id, 'atualizar', mudancas)
    db.session.commit()
    return jsonify(r.to_dict())


@regionais_bp.route('/<int:rid>', methods=['DELETE'])
@jwt_required()
def deletar(rid):
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403
    r = Regional.query.get_or_404(rid)
    r.ativo = False
    log_audit(me.id, 'regional', r.id, 'excluir', {'ativo': False, 'nome': r.nome})
    db.session.commit()
    return jsonify({'mensagem': 'Regional inativada'})
