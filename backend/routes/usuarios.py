import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.audit import log_audit, diff_payload
from backend.models import Usuario, AuditLog
from backend.constants import PERFIS_USUARIO, PERFIS_COMBINAVEIS
from backend.extensions import db

usuarios_bp = Blueprint('usuarios', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


def require_admin(u):
    return u.perfil == 'admin'


def normalizar_perfis(data):
    """Extrai e valida a lista de perfis do payload. Aceita `perfis` (lista,
    novo formato) ou `perfil` (string, formato legado). Retorna (lista, erro)."""
    if 'perfis' in data and data.get('perfis') is not None:
        perfis = data.get('perfis')
        if not isinstance(perfis, list):
            perfis = [perfis]
    elif data.get('perfil'):
        perfis = [data.get('perfil')]
    else:
        perfis = []

    # Remove vazios e duplicatas preservando a ordem (1º = principal)
    limpa = []
    for p in perfis:
        if p and p not in limpa:
            limpa.append(p)

    if not limpa:
        return None, 'Selecione ao menos um perfil'
    if len(limpa) > 3:
        return None, 'Máximo de 3 perfis por usuário'
    for p in limpa:
        if p not in PERFIS_USUARIO:
            return None, 'Perfil inválido'

    # Administrador e Superintendente são sempre perfil único. Só é permitido
    # combinar perfis entre Gerente, Coordenador e Supervisor.
    if len(limpa) > 1 and any(p not in PERFIS_COMBINAVEIS for p in limpa):
        return None, 'Administrador e Superintendente não podem ser combinados com outros perfis'

    return limpa, None


def remove_uploaded_file(url):
    if not url or not url.startswith('/uploads/'):
        return

    relative_path = url.split('/uploads/', 1)[1]
    upload_folder = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    file_path = os.path.abspath(os.path.join(upload_folder, relative_path))

    if os.path.commonpath([upload_folder, file_path]) == upload_folder and os.path.exists(file_path):
        os.remove(file_path)


@usuarios_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    me = get_current_user()
    query = Usuario.query

    # escopo=delegacao: usado só pelo seletor de "Responsável pela Ação" (ver
    # Seção 4 — notificação de atividade delegada). Sem essa flag, gv/cd/sp só
    # enxergam a si mesmos (regra de visibilidade original); com ela, também
    # veem os colegas da própria regional — precisam disso pra ter alguém a
    # quem delegar, mas continuam sem acesso à listagem ampla de usuários.
    escopo_delegacao = request.args.get('escopo') == 'delegacao'

    if me.perfil == 'sr' or (escopo_delegacao and me.regional_id):
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
    else:
        # Sem filtro explícito de status, usuários excluídos ficam de fora da
        # listagem padrão (só aparecem com ?status=excluido, pra auditoria).
        query = query.filter(Usuario.status != 'excluido')

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

    perfis, erro = normalizar_perfis(data)
    if erro:
        return jsonify({'erro': erro}), 400

    if Usuario.query.filter_by(email=email).first():
        return jsonify({'erro': 'Email já cadastrado'}), 400

    # Validação: SUPERINTENDENTE requer supervisor obrigatoriamente
    if 'sr' in perfis and not data.get('supervisor_id'):
        return jsonify({'erro': 'Superintendente deve ter um Supervisor Responsável designado'}), 400

    u = Usuario(
        nome=data['nome'],
        email=email,
        perfil=perfis[0],
        regional_id=data.get('regional_id'),
        supervisor_id=data.get('supervisor_id'),
        status=data.get('status', 'ativo')
    )
    u.set_perfis(perfis)
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
    if ('perfis' in data or 'perfil' in data) and require_admin(me):
        perfis, erro = normalizar_perfis(data)
        if erro:
            return jsonify({'erro': erro}), 400
        u.set_perfis(perfis)
    if 'regional_id' in data and require_admin(me):
        u.regional_id = data['regional_id']
    if 'supervisor_id' in data and require_admin(me):
        u.supervisor_id = data['supervisor_id']
    if 'status' in data and require_admin(me):
        u.status = data['status']
    if 'senha' in data and require_admin(me):
        u.set_senha(data['senha'])

    # Validação: SUPERINTENDENTE requer supervisor obrigatoriamente
    if u.perfil == 'sr' and not u.supervisor_id:
        return jsonify({'erro': 'Superintendente deve ter um Supervisor Responsável designado'}), 400

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
    """Exclusão suave: o usuário deixa de poder logar e some das listas
    padrão (mesmo critério de login/geração/dashboard, que já só consideram
    status='ativo'), mas o registro em si continua no banco — preservando
    integralmente as rotinas dele (inclusive concluídas), evidências,
    histórico e aprovações, que continuam visíveis em telas de histórico
    (ex.: Acompanhamento). Diferente de 'inativo' (reversível/temporário),
    pensado como estado permanente."""
    me = get_current_user()
    if not require_admin(me):
        return jsonify({'erro': 'Acesso negado'}), 403
    if me.id == uid:
        return jsonify({'erro': 'Não é possível excluir o próprio usuário'}), 400

    u = Usuario.query.get_or_404(uid)
    if u.status == 'excluido':
        return jsonify({'erro': 'Usuário já está excluído'}), 400

    status_anterior = u.status
    u.status = 'excluido'
    remove_uploaded_file(u.foto_url)
    u.foto_url = None

    log_audit(me.id, 'usuario', u.id, 'excluir', {
        'nome': u.nome, 'email': u.email, 'perfil': u.perfil, 'status_anterior': status_anterior,
    })
    db.session.commit()
    return jsonify({'mensagem': 'Usuário excluído'})


@usuarios_bp.route('/perfil/foto', methods=['POST'])
@jwt_required()
def upload_foto():
    me = get_current_user()
    if 'foto' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
    
    arquivo = request.files['foto']
    if arquivo.filename == '':
        return jsonify({'erro': 'Nenhum arquivo selecionado'}), 400
    
    if arquivo and allowed_file(arquivo.filename):
        # Garantir pasta de perfis
        folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'perfis')
        os.makedirs(folder, exist_ok=True)
        
        ext = arquivo.filename.rsplit('.', 1)[1].lower()
        nome_final = f"user_{me.id}_{uuid.uuid4().hex[:8]}.{ext}"
        caminho = os.path.join(folder, nome_final)
        
        arquivo.save(caminho)
        
        # Atualizar usuário
        me.foto_url = f"/uploads/perfis/{nome_final}"
        db.session.commit()
        
        return jsonify({'foto_url': me.foto_url})
    
    return jsonify({'erro': 'Tipo de arquivo não permitido'}), 400


@usuarios_bp.route('/perfil/senha', methods=['POST'])
@jwt_required()
def mudar_senha():
    me = get_current_user()
    data = request.get_json()
    senha_atual = data.get('senha_atual')
    nova_senha = data.get('nova_senha')

    if not senha_atual or not nova_senha:
        return jsonify({'erro': 'Senha atual e nova senha são obrigatórias'}), 400
    
    if not me.check_senha(senha_atual):
        return jsonify({'erro': 'Senha atual incorreta'}), 401
    
    me.set_senha(nova_senha)
    db.session.commit()
    log_audit(me.id, 'usuario', me.id, 'mudar_senha', {'mensagem': 'Senha alterada pelo próprio usuário'})
    return jsonify({'mensagem': 'Senha alterada com sucesso'})
