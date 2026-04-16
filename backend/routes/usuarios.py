from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.audit import log_audit, diff_payload
from backend.models import Usuario
from backend.constants import PERFIS_USUARIO
from backend.extensions import db

usuarios_bp = Blueprint('usuarios', __name__)


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


def require_admin(u):
    return u.perfil == 'admin'


@usuarios_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    me = get_current_user()
    query = Usuario.query

    if me.perfil == 'sr':
        query = query.filter_by(regional_id=me.regional_id)
    elif me.perfil not in ['admin']:
        query = query.filter_by(id=me.id)

    perfil = request.args.get('perfil')
    regional_id = request.args.get('regional_id')
    status = request.args.get('status')

    if perfil:
        query = query.filter_by(perfil=perfil)
    if regional_id:
        query = query.filter_by(regional_id=int(regional_id))
    if status:
        query = query.filter_by(status=status)

    usuarios = query.order_by(Usuario.nome).all()
    return jsonify([u.to_dict() for u in usuarios])


@usuarios_bp.route('/<int:uid>', methods=['GET'])
@jwt_required()
def obter(uid):
    me = get_current_user()
    u = Usuario.query.get_or_404(uid)
    if me.perfil not in ['admin', 'sr'] and me.id != uid:
        return jsonify({'erro': 'Acesso negado'}), 403
    return jsonify(u.to_dict())


@usuarios_bp.route('/', methods=['POST'])
@jwt_required()
def criar():
    me = get_current_user()
    if not require_admin(me):
        return jsonify({'erro': 'Acesso negado'}), 403

    data = request.get_json()
    email = data.get('email', '').strip().lower()
    perfil = data.get('perfil')

    if perfil not in PERFIS_USUARIO:
        return jsonify({'erro': 'Perfil inválido'}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({'erro': 'Email já cadastrado'}), 400

    u = Usuario(
        nome=data['nome'],
        email=email,
        perfil=perfil,
        regional_id=data.get('regional_id'),
        supervisor_id=data.get('supervisor_id'),
        status=data.get('status', 'ativo')
    )
    u.set_senha(data.get('senha', '123456'))
    db.session.add(u)
    db.session.commit()
    log_audit(me.id, 'usuario', u.id, 'criar', u.to_dict())
    db.session.commit()
    return jsonify(u.to_dict()), 201


@usuarios_bp.route('/<int:uid>', methods=['PUT'])
@jwt_required()
def atualizar(uid):
    me = get_current_user()
    if not require_admin(me) and me.id != uid:
        return jsonify({'erro': 'Acesso negado'}), 403

    u = Usuario.query.get_or_404(uid)
    before = u.to_dict()
    data = request.get_json()

    if 'nome' in data:
        u.nome = data['nome']
    if 'email' in data and require_admin(me):
        u.email = data['email'].strip().lower()
    if 'perfil' in data and require_admin(me):
        if data['perfil'] not in PERFIS_USUARIO:
            return jsonify({'erro': 'Perfil inválido'}), 400
        u.perfil = data['perfil']
    if 'regional_id' in data and require_admin(me):
        u.regional_id = data['regional_id']
    if 'supervisor_id' in data and require_admin(me):
        u.supervisor_id = data['supervisor_id']
    if 'status' in data and require_admin(me):
        u.status = data['status']
    if 'senha' in data and require_admin(me):
        u.set_senha(data['senha'])

    after = u.to_dict()
    mudancas = diff_payload(before, after)
    if 'senha' in data and require_admin(me):
        mudancas['senha'] = {'antes': '***', 'depois': '***'}
    if mudancas:
        log_audit(me.id, 'usuario', u.id, 'atualizar', mudancas)
    db.session.commit()
    return jsonify(u.to_dict())


@usuarios_bp.route('/<int:uid>', methods=['DELETE'])
@jwt_required()
def deletar(uid):
    me = get_current_user()
    if not require_admin(me):
        return jsonify({'erro': 'Acesso negado'}), 403
    u = Usuario.query.get_or_404(uid)
    u.status = 'inativo'
    log_audit(me.id, 'usuario', u.id, 'excluir', {'status': 'inativo', 'email': u.email})
    db.session.commit()
    return jsonify({'mensagem': 'Usuário inativado'})
