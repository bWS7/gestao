from datetime import datetime, timezone
from backend.extensions import db
import bcrypt


class Regional(db.Model):
    __tablename__ = 'regionais'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuarios = db.relationship('Usuario', backref='regional', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(50), nullable=False)  # admin, sr, gv, cd, sp
    regional_id = db.Column(db.Integer, db.ForeignKey('regionais.id'), nullable=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    status = db.Column(db.String(20), default='ativo')  # ativo, inativo, bloqueado
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    subordinados = db.relationship('Usuario', backref=db.backref('supervisor', remote_side=[id]), lazy=True)
    rotinas = db.relationship('Rotina', backref='usuario', lazy=True)

    def set_senha(self, senha):
        self.senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_senha(self, senha):
        return bcrypt.checkpw(senha.encode('utf-8'), self.senha_hash.encode('utf-8'))

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'email': self.email,
            'perfil': self.perfil,
            'regional_id': self.regional_id,
            'regional_nome': self.regional.nome if self.regional else None,
            'supervisor_id': self.supervisor_id,
            'supervisor_nome': self.supervisor.nome if self.supervisor else None,
            'status': self.status,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class AtividadeCatalogo(db.Model):
    __tablename__ = 'atividades_catalogo'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    periodicidade = db.Column(db.String(20), nullable=False)  # semanal, quinzenal, mensal
    perfil = db.Column(db.String(50), nullable=False)
    obrigatoria = db.Column(db.Boolean, default=True)
    tipo_evidencia = db.Column(db.String(100))
    indicador = db.Column(db.String(200))
    prazo_padrao = db.Column(db.Integer, default=7)  # dias
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'periodicidade': self.periodicidade,
            'perfil': self.perfil,
            'obrigatoria': self.obrigatoria,
            'tipo_evidencia': self.tipo_evidencia,
            'indicador': self.indicador,
            'prazo_padrao': self.prazo_padrao,
            'ordem': self.ordem,
            'ativo': self.ativo
        }


class Rotina(db.Model):
    __tablename__ = 'rotinas'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    atividade_id = db.Column(db.Integer, db.ForeignKey('atividades_catalogo.id'), nullable=False)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    periodicidade = db.Column(db.String(20))
    status = db.Column(db.String(30), default='nao_iniciada')  # nao_iniciada, em_andamento, concluida, nao_realizada
    data_conclusao = db.Column(db.DateTime)
    comentario = db.Column(db.Text)
    justificativa = db.Column(db.Text)
    acao_corretiva = db.Column(db.Text)
    novo_prazo = db.Column(db.Date)
    responsavel_acao = db.Column(db.String(150))
    checklist = db.Column(db.Text)
    relatorio = db.Column(db.Text)
    plano_semana = db.Column(db.Text)
    visitas_ativacoes = db.Column(db.Text)
    resultados_visita = db.Column(db.Text)
    carteira_ativa = db.Column(db.Text)
    metas_canal = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    atividade = db.relationship('AtividadeCatalogo', backref='rotinas', lazy=True)
    evidencias = db.relationship('Evidencia', backref='rotina', lazy=True)
    historico = db.relationship('HistoricoRotina', backref='rotina', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario.nome if self.usuario else None,
            'atividade_id': self.atividade_id,
            'atividade_nome': self.atividade.nome if self.atividade else None,
            'atividade_descricao': self.atividade.descricao if self.atividade else None,
            'atividade_obrigatoria': self.atividade.obrigatoria if self.atividade else False,
            'tipo_evidencia': self.atividade.tipo_evidencia if self.atividade else None,
            'indicador': self.atividade.indicador if self.atividade else None,
            'perfil': self.atividade.perfil if self.atividade else None,
            'periodo_inicio': self.periodo_inicio.isoformat() if self.periodo_inicio else None,
            'periodo_fim': self.periodo_fim.isoformat() if self.periodo_fim else None,
            'periodicidade': self.periodicidade,
            'status': self.status,
            'data_conclusao': self.data_conclusao.isoformat() if self.data_conclusao else None,
            'comentario': self.comentario,
            'justificativa': self.justificativa,
            'acao_corretiva': self.acao_corretiva,
            'novo_prazo': self.novo_prazo.isoformat() if self.novo_prazo else None,
            'responsavel_acao': self.responsavel_acao,
            'checklist': self.checklist,
            'relatorio': self.relatorio,
            'plano_semana': self.plano_semana,
            'visitas_ativacoes': self.visitas_ativacoes,
            'resultados_visita': self.resultados_visita,
            'carteira_ativa': self.carteira_ativa,
            'metas_canal': self.metas_canal,
            'evidencias': [e.to_dict() for e in self.evidencias],
            'criado_em': self.criado_em.isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.isoformat() if self.atualizado_em else None
        }


class Evidencia(db.Model):
    __tablename__ = 'evidencias'
    id = db.Column(db.Integer, primary_key=True)
    rotina_id = db.Column(db.Integer, db.ForeignKey('rotinas.id'), nullable=False)
    nome_arquivo = db.Column(db.String(255))
    url = db.Column(db.Text)
    tipo = db.Column(db.String(50))
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'rotina_id': self.rotina_id,
            'nome_arquivo': self.nome_arquivo,
            'url': self.url,
            'tipo': self.tipo,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    entidade = db.Column(db.String(100), nullable=False)
    entidade_id = db.Column(db.String(50))
    acao = db.Column(db.String(50), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    detalhes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'entidade': self.entidade,
            'entidade_id': self.entidade_id,
            'acao': self.acao,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario.nome if self.usuario else None,
            'detalhes': self.detalhes,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }


class HistoricoRotina(db.Model):
    __tablename__ = 'historico_rotinas'
    id = db.Column(db.Integer, primary_key=True)
    rotina_id = db.Column(db.Integer, db.ForeignKey('rotinas.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    acao = db.Column(db.String(100))
    status_anterior = db.Column(db.String(30))
    status_novo = db.Column(db.String(30))
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    usuario = db.relationship('Usuario', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'rotina_id': self.rotina_id,
            'usuario_id': self.usuario_id,
            'usuario_nome': self.usuario.nome if self.usuario else None,
            'acao': self.acao,
            'status_anterior': self.status_anterior,
            'status_novo': self.status_novo,
            'observacao': self.observacao,
            'criado_em': self.criado_em.isoformat() if self.criado_em else None
        }
