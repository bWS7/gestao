import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from sqlalchemy import inspect
from sqlalchemy import text
from backend.extensions import db, jwt, migrate
from backend.routes.auth import auth_bp
from backend.routes.usuarios import usuarios_bp
from backend.routes.regionais import regionais_bp
from backend.routes.empreendimentos import empreendimentos_bp
from backend.routes.atividades import atividades_bp
from backend.routes.rotinas import rotinas_bp, reconciliar_semanas_mes_atual
from backend.routes.notificacoes import notificacoes_bp


def _get_database_url():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if db_url.startswith('postgres://'):
            return db_url.replace('postgres://', 'postgresql://', 1)
        return db_url

    pg_host = os.environ.get('PGHOST')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_user = os.environ.get('PGUSER')
    pg_password = os.environ.get('PGPASSWORD')
    pg_database = os.environ.get('PGDATABASE')

    if all([pg_host, pg_user, pg_password, pg_database]):
        return f'postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}'

    raise RuntimeError(
        'PostgreSQL configuration is required. Set DATABASE_URL or the PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE variables.'
    )


def create_app():
    app = Flask(__name__, static_folder='../frontend/static', static_url_path='/static')

    # Config
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-mude-em-producao')
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'jwt-secret-mude-em-producao')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'uploads')

    app.config['SQLALCHEMY_DATABASE_URI'] = _get_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Extensions
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app, origins='*', supports_credentials=True)

    # Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(usuarios_bp, url_prefix='/api/usuarios')
    app.register_blueprint(regionais_bp, url_prefix='/api/regionais')
    app.register_blueprint(empreendimentos_bp, url_prefix='/api/empreendimentos')
    app.register_blueprint(atividades_bp, url_prefix='/api/atividades')
    app.register_blueprint(rotinas_bp, url_prefix='/api/rotinas')
    app.register_blueprint(notificacoes_bp, url_prefix='/api/notificacoes')

    # Frontend routes
    @app.route('/')
    @app.route('/dashboard')
    @app.route('/usuarios')
    @app.route('/regionais')
    @app.route('/empreendimentos')
    @app.route('/atividades')
    @app.route('/rotinas')
    @app.route('/acompanhamento')
    @app.route('/pendencias')
    @app.route('/perfil')
    @app.route('/auditoria')
    @app.route('/aprovacoes')
    def frontend():
        # O index.html nunca deve ser cacheado pelo navegador: ele referencia os
        # bundles JS/CSS com hash no nome (esses sim cacheáveis para sempre).
        # Assim, todo novo deploy é carregado automaticamente, sem limpar cache.
        resp = send_from_directory('../frontend', 'index.html')
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    @app.route('/imagens/<path:filename>')
    def imagens(filename):
        return send_from_directory('../imagens', filename)

    @app.route('/uploads/<path:filename>')
    def uploads(filename):
        from flask import Response
        from backend.models import Evidencia

        folder = app.config['UPLOAD_FOLDER']
        path = os.path.join(folder, filename)

        # Serve inline (as_attachment=False) para abrir no navegador em vez de baixar.
        # Tipos que o navegador sabe exibir (PDF, imagens) abrem na aba; os demais
        # (ex.: Office) ainda são baixados pelo próprio navegador.
        if os.path.exists(path):
            return send_from_directory(folder, filename, as_attachment=False)

        # Arquivo não está no disco (ex: container reiniciou) — serve do banco
        evidencia = Evidencia.query.filter_by(url=f'/uploads/{filename}').first()
        if evidencia and evidencia.conteudo:
            nome_display = evidencia.nome_arquivo or filename
            return Response(
                evidencia.conteudo,
                mimetype=evidencia.tipo or 'application/octet-stream',
                headers={
                    'Content-Disposition': f'inline; filename="{nome_display}"',
                    'Content-Length': str(len(evidencia.conteudo)),
                }
            )

        app.logger.error(f"Arquivo não encontrado no disco nem no banco: {filename}")
        return jsonify({'erro': 'Arquivo não encontrado'}), 404

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    # Init DB and seed
    with app.app_context():
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        db.create_all()
        _ensure_runtime_columns()
        reconciliar_semanas_mes_atual()
        _seed_initial_data()
        _seed_empreendimentos()

    return app


def _seed_empreendimentos():
    """Carga inicial idempotente dos empreendimentos cadastrados no sistema.
    Insere apenas os que ainda não existem (por nome), preservando edições e
    inativações feitas pelo admin."""
    from backend.seed_data import EMPREENDIMENTOS_SEED
    from backend.models import Empreendimento

    existentes = {nome for (nome,) in db.session.query(Empreendimento.nome).all()}
    criados = 0
    for nome in EMPREENDIMENTOS_SEED:
        if nome not in existentes:
            db.session.add(Empreendimento(nome=nome, ativo=True))
            criados += 1
    if criados:
        db.session.commit()
        print(f"[seed] {criados} empreendimentos cadastrados.")


def _seed_initial_data():
    from backend.models import Usuario
    from sqlalchemy import text
    
    # Migração manual de colunas novas
    try:
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS foto_url TEXT"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao adicionar coluna foto_url: {e}")
    
    # Novo Admin Master
    admin_email = 'bruno.alves@sousaaraujo.com.br'
    if not Usuario.query.filter_by(email=admin_email).first():
        admin = Usuario(
            nome='Bruno Alves',
            email=admin_email,
            perfil='admin',
            status='ativo'
        )
        admin.set_senha('admin123')
        db.session.add(admin)
        db.session.commit()
        print(f"Usuário admin {admin_email} garantido.")



def _sync_descricoes_catalogo():
    """Preenche descricao nula nas atividades do catálogo usando o seed_data."""
    from backend.seed_data import ATIVIDADES_CATALOGO
    from backend.models import AtividadeCatalogo
    atualizadas = 0
    for seed in ATIVIDADES_CATALOGO:
        descricao = seed.get('descricao')
        if not descricao:
            continue
        ativ = AtividadeCatalogo.query.filter_by(nome=seed['nome']).first()
        if ativ and not ativ.descricao:
            ativ.descricao = descricao
            atualizadas += 1
    if atualizadas:
        db.session.commit()
        print(f"[sync] {atualizadas} descrições de atividades atualizadas.")


def _sync_atividades_superintendentes():
    """Mantem o catalogo de SR alinhado aos seis relatorios personalizados."""
    from backend.seed_data import ATIVIDADES_CATALOGO
    from backend.models import AtividadeCatalogo

    aliases = {
        'Reunião de Performance com Liderados': ['Reunião de Performance Regional'],
        'Resultado Semanal da Regional': ['Diagnóstico Semanal da Regional'],
        'Decisões de Canal': [],
        'Análise dos Riscos da Regional': ['Top 3 Riscos e Contramedidas', 'Plano de Ação Semanal Regional'],
        'Acompanhamento e Desenvolvimento dos Liderados (1:1)': [
            'Acompanhamento e Desenvolvimento dos Liderados',
            '1:1 com Gerentes de Vendas',
            'Ciclo Quinzenal de Desenvolvimento',
        ],
        'Comitê Mensal de Resultados': ['Comitê Mensal de Resultado'],
    }
    sr_seeds = [seed for seed in ATIVIDADES_CATALOGO if seed.get('perfil') == 'sr']
    nomes_finais = {seed['nome'] for seed in sr_seeds}
    alteradas = 0

    for seed in sr_seeds:
        nomes_busca = [seed['nome'], *aliases.get(seed['nome'], [])]
        atividade = (
            AtividadeCatalogo.query
            .filter(AtividadeCatalogo.perfil == 'sr', AtividadeCatalogo.nome.in_(nomes_busca))
            .order_by(AtividadeCatalogo.ativo.desc(), AtividadeCatalogo.id.asc())
            .first()
        )

        if not atividade:
            atividade = AtividadeCatalogo()
            db.session.add(atividade)
            alteradas += 1

        for campo in ['nome', 'descricao', 'periodicidade', 'perfil', 'obrigatoria', 'tipo_evidencia', 'indicador', 'prazo_padrao', 'ordem']:
            valor = seed.get(campo)
            if getattr(atividade, campo, None) != valor:
                setattr(atividade, campo, valor)
                alteradas += 1
        if not atividade.ativo:
            atividade.ativo = True
            alteradas += 1

    extras = AtividadeCatalogo.query.filter(
        AtividadeCatalogo.perfil == 'sr',
        ~AtividadeCatalogo.nome.in_(nomes_finais)
    ).all()
    for atividade in extras:
        if atividade.ativo:
            atividade.ativo = False
            alteradas += 1

    if alteradas:
        db.session.commit()
        print("[sync] Catalogo de superintendentes alinhado aos 6 relatorios personalizados.")


def _sync_atividades_parcerias():
    """Mantem o catalogo de SP alinhado aos cinco relatorios personalizados."""
    from backend.seed_data import ATIVIDADES_CATALOGO
    from backend.models import AtividadeCatalogo

    aliases = {
        'Rotina de Visita a Parceiros': ['Rotina de Visitas a Parceiros'],
        'Análise da Carteira de Parceiros': ['Mapa de Carteira de Parceiros'],
    }
    sp_seeds = [seed for seed in ATIVIDADES_CATALOGO if seed.get('perfil') == 'sp']
    nomes_finais = {seed['nome'] for seed in sp_seeds}
    alteradas = 0

    for seed in sp_seeds:
        nomes_busca = [seed['nome'], *aliases.get(seed['nome'], [])]
        atividade = (
            AtividadeCatalogo.query
            .filter(AtividadeCatalogo.perfil == 'sp', AtividadeCatalogo.nome.in_(nomes_busca))
            .order_by(AtividadeCatalogo.ativo.desc(), AtividadeCatalogo.id.asc())
            .first()
        )

        if not atividade:
            atividade = AtividadeCatalogo()
            db.session.add(atividade)
            alteradas += 1

        for campo in ['nome', 'descricao', 'periodicidade', 'perfil', 'obrigatoria', 'tipo_evidencia', 'indicador', 'prazo_padrao', 'ordem']:
            valor = seed.get(campo)
            if getattr(atividade, campo, None) != valor:
                setattr(atividade, campo, valor)
                alteradas += 1
        if not atividade.ativo:
            atividade.ativo = True
            alteradas += 1

    extras = AtividadeCatalogo.query.filter(
        AtividadeCatalogo.perfil == 'sp',
        ~AtividadeCatalogo.nome.in_(nomes_finais)
    ).all()
    for atividade in extras:
        if atividade.ativo:
            atividade.ativo = False
            alteradas += 1

    if alteradas:
        db.session.commit()
        print("[sync] Catalogo de parcerias alinhado aos 5 relatorios personalizados.")


def _ensure_runtime_columns():
    insp = inspect(db.engine)
    tabelas = set(insp.get_table_names())

    if 'rotinas' in tabelas:
        existentes = {col['name'] for col in insp.get_columns('rotinas')}
        colunas_texto = ['checklist', 'relatorio', 'plano_semana', 'visitas_ativacoes', 'resultados_visita', 'carteira_ativa', 'metas_canal', 'motivo_reprovacao', 'formulario_comercial']
        for coluna in colunas_texto:
            if coluna not in existentes:
                db.session.execute(text(f"ALTER TABLE rotinas ADD COLUMN {coluna} TEXT"))
        if 'status_aprovacao' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN status_aprovacao VARCHAR(30) DEFAULT 'pendente'"))
        if 'aprovador_id' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN aprovador_id INTEGER"))
        if 'data_aprovacao' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN data_aprovacao TIMESTAMP"))
        if 'formulario_preenchido' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN formulario_preenchido BOOLEAN DEFAULT FALSE"))
        if 'prazo_reenvio' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN prazo_reenvio DATE"))
        if 'responsavel_id' not in existentes:
            db.session.execute(text("ALTER TABLE rotinas ADD COLUMN responsavel_id INTEGER REFERENCES usuarios(id)"))

    if 'aprovacoes_rotinas' in tabelas:
        existentes_ap = {col['name'] for col in insp.get_columns('aprovacoes_rotinas')}
        if 'duracao_revisao_segundos' not in existentes_ap:
            db.session.execute(text("ALTER TABLE aprovacoes_rotinas ADD COLUMN duracao_revisao_segundos INTEGER"))

    if 'evidencias' in tabelas:
        existentes = {col['name'] for col in insp.get_columns('evidencias')}
        if 'conteudo' not in existentes:
            db.session.execute(text("ALTER TABLE evidencias ADD COLUMN conteudo BYTEA"))
        # MIME types de Office (pptx/docx/xlsx) passam de 50 caracteres; amplia a coluna.
        db.session.execute(text("ALTER TABLE evidencias ALTER COLUMN tipo TYPE VARCHAR(255)"))

    if 'atividades_catalogo' in tabelas:
        existentes_at = {col['name'] for col in insp.get_columns('atividades_catalogo')}
        if 'descricao' not in existentes_at:
            db.session.execute(text("ALTER TABLE atividades_catalogo ADD COLUMN descricao TEXT"))

    if 'usuarios' in tabelas:
        existentes_u = {col['name'] for col in insp.get_columns('usuarios')}
        if 'perfis' not in existentes_u:
            db.session.execute(text("ALTER TABLE usuarios ADD COLUMN perfis TEXT"))
            # Backfill: usuários existentes recebem uma lista com seu perfil atual.
            db.session.execute(text(
                "UPDATE usuarios SET perfis = '[\"' || perfil || '\"]' "
                "WHERE perfis IS NULL AND perfil IS NOT NULL"
            ))

    db.session.commit()

    # Atualiza descrições do catálogo a partir do seed_data
    _sync_descricoes_catalogo()
    _sync_atividades_superintendentes()
    _sync_atividades_parcerias()

    # Catálogo de atividades


app = create_app()



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
