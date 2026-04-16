from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from backend.audit import log_audit
from backend.models import Usuario
from backend.extensions import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    senha = data.get('senha', '')

    if not email or not senha:
        return jsonify({'erro': 'Email e senha são obrigatórios'}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not usuario.check_senha(senha):
        return jsonify({'erro': 'Credenciais inválidas'}), 401

    if usuario.status != 'ativo':
        return jsonify({'erro': 'Usuário inativo ou bloqueado'}), 403

    token = create_access_token(identity=str(usuario.id))
    return jsonify({
        'token': token,
        'usuario': usuario.to_dict()
    })


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    uid = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(uid)
    return jsonify(usuario.to_dict())


@auth_bp.route('/trocar-senha', methods=['POST'])
@jwt_required()
def trocar_senha():
    uid = int(get_jwt_identity())
    usuario = Usuario.query.get_or_404(uid)
    data = request.get_json()
    senha_atual = data.get('senha_atual', '')
    nova_senha = data.get('nova_senha', '')

    if not usuario.check_senha(senha_atual):
        return jsonify({'erro': 'Senha atual incorreta'}), 400

    if len(nova_senha) < 6:
        return jsonify({'erro': 'Nova senha deve ter pelo menos 6 caracteres'}), 400

    usuario.set_senha(nova_senha)
    log_audit(usuario.id, 'usuario', usuario.id, 'trocar_senha', {'origem': 'perfil'})
    db.session.commit()
    return jsonify({'mensagem': 'Senha alterada com sucesso'})
