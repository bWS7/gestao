from datetime import datetime, timezone, timedelta
from backend.utils.dates import get_now_br, hoje_br
from backend.extensions import db
import bcrypt
import json

# Folga (em dias) concedida após o fim do período para concluir a rotina,
# conforme a periodicidade. Periodicidades não listadas não recebem folga.
GRACE_DAYS_BY_PERIODICIDADE = {
    'semanal': 3,  # semana (seg–dom) + 3 dias → até a quarta seguinte
    'mensal': 3,   # mês inteiro + 3 dias → ex.: Julho até 03/08
}

# Dias extras que o colaborador recebe para reenviar a atividade após reprovação.
GRACE_DAYS_REENVIO = 2

MESES_PT = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]


class Regional(db.Model):
    __tablename__ = 'regionais'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=get_now_br)
    usuarios = db.relationship('Usuario', backref='regional', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'ativo': self.ativo,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class Empreendimento(db.Model):
    __tablename__ = 'empreendimentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text)
    regional_id = db.Column(db.Integer, db.ForeignKey('regionais.id'), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=get_now_br)
    regional = db.relationship('Regional', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'descricao': self.descricao,
            'regional_id': self.regional_id,
            'regional_nome': self.regional.nome if self.regional else None,
            'ativo': self.ativo,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(50), nullable=False)  # perfil PRINCIPAL: admin, sr, gv, cd, sp
    # Lista JSON com TODOS os perfis do usuário (1 a 3). O primeiro é o principal
    # (espelhado em `perfil`, mantido para a lógica de permissões existente).
    perfis = db.Column(db.Text)
    regional_id = db.Column(db.Integer, db.ForeignKey('regionais.id'), nullable=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    status = db.Column(db.String(20), default='ativo')  # ativo, inativo, bloqueado, excluido
    foto_url = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=get_now_br)
    atualizado_em = db.Column(db.DateTime, default=get_now_br, onupdate=get_now_br)
    subordinados = db.relationship('Usuario', backref=db.backref('supervisor', remote_side=[id]), lazy=True)
    rotinas = db.relationship('Rotina', foreign_keys='Rotina.usuario_id', backref='usuario', lazy=True)

    def set_senha(self, senha):
        self.senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_senha(self, senha):
        return bcrypt.checkpw(senha.encode('utf-8'), self.senha_hash.encode('utf-8'))

    @property
    def perfis_list(self):
        """Todos os perfis do usuário. Se `perfis` não estiver preenchido (dados
        antigos), cai de volta para o perfil principal único."""
        if self.perfis:
            try:
                vals = json.loads(self.perfis)
                if isinstance(vals, list) and vals:
                    return [p for p in vals if p]
            except (ValueError, TypeError):
                pass
        return [self.perfil] if self.perfil else []

    def set_perfis(self, lista):
        """Define a lista de perfis (máx. 3, sem duplicatas). O primeiro vira o
        perfil principal."""
        limpa = []
        for p in (lista or []):
            if p and p not in limpa:
                limpa.append(p)
        limpa = limpa[:3]
        self.perfis = json.dumps(limpa) if limpa else None
        if limpa:
            self.perfil = limpa[0]

    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'email': self.email,
            'perfil': self.perfil,
            'perfis': self.perfis_list,
            'regional_id': self.regional_id,
            'regional_nome': self.regional.nome if self.regional else None,
            'supervisor_id': self.supervisor_id,
            'supervisor_nome': self.supervisor.nome if self.supervisor else None,
            'status': self.status,
            'foto_url': self.foto_url,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class AtividadeCatalogo(db.Model):
    __tablename__ = 'atividades_catalogo'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text)
    periodicidade = db.Column(db.String(20), nullable=False)  # diaria, semanal, quinzenal, mensal
    perfil = db.Column(db.String(50), nullable=False)
    obrigatoria = db.Column(db.Boolean, default=True)
    tipo_evidencia = db.Column(db.String(100))
    indicador = db.Column(db.String(200))
    prazo_padrao = db.Column(db.Integer, default=7)  # dias
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=get_now_br)

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
    responsavel_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    checklist = db.Column(db.Text)
    relatorio = db.Column(db.Text)
    plano_semana = db.Column(db.Text)
    visitas_ativacoes = db.Column(db.Text)
    resultados_visita = db.Column(db.Text)
    carteira_ativa = db.Column(db.Text)
    metas_canal = db.Column(db.Text)
    formulario_comercial = db.Column(db.Text)
    formulario_preenchido = db.Column(db.Boolean, default=False)
    status_aprovacao = db.Column(db.String(30), default='pendente')  # pendente, aprovada, reprovada
    aprovador_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    data_aprovacao = db.Column(db.DateTime)
    motivo_reprovacao = db.Column(db.Text)
    prazo_reenvio = db.Column(db.Date, nullable=True)  # prazo para reenvio após reprovação
    criado_em = db.Column(db.DateTime, default=get_now_br)
    atualizado_em = db.Column(db.DateTime, default=get_now_br, onupdate=get_now_br)
    atividade = db.relationship('AtividadeCatalogo', backref='rotinas', lazy=True)
    evidencias = db.relationship('Evidencia', backref='rotina', lazy=True)
    historico = db.relationship('HistoricoRotina', backref='rotina', lazy=True)
    aprovador = db.relationship('Usuario', foreign_keys=[aprovador_id], lazy=True)
    aprovacoes = db.relationship('AprovacaoRotina', backref='rotina', lazy=True)
    responsavel = db.relationship('Usuario', foreign_keys=[responsavel_id], lazy=True)

    @property
    def prazo_limite(self):
        # Se a atividade foi reprovada e tem prazo_reenvio, o prazo efetivo
        # passa a ser o prazo_reenvio (data_reprovação + GRACE_DAYS_REENVIO).
        if self.status_aprovacao == 'reprovada' and self.prazo_reenvio:
            return self.prazo_reenvio

        # O prazo da rotina é o fim do seu período (dia/semana/quinzena/mês),
        # acrescido de uma folga de conclusão conforme a periodicidade. A
        # atividade só é considerada vencida APÓS o término do período + folga —
        # uma rotina semanal (seg a dom) pode ser concluída até a quarta seguinte.
        fim = self.periodo_fim or self.periodo_inicio
        if not fim:
            return None
        periodicidade = self.periodicidade or (self.atividade.periodicidade if self.atividade else None)
        folga = GRACE_DAYS_BY_PERIODICIDADE.get(periodicidade, 0)
        return fim + timedelta(days=folga) if folga else fim

    @property
    def periodo_label(self):
        """Rótulo legível do período de referência da rotina, p.ex.:
        'Semana 2 - Julho/2026' (semanal), 'Julho/2026' (mensal),
        '1ª Quinzena - Julho/2026' (quinzenal) ou '15/07/2026' (diária)."""
        inicio = self.periodo_inicio
        if not inicio:
            return None
        periodicidade = self.periodicidade or (self.atividade.periodicidade if self.atividade else None)

        if periodicidade == 'semanal':
            # Semana de calendário fixa (01-07/08-14/15-21/22-fim, ver
            # get_periodo em routes/rotinas.py) — sempre dentro do mesmo mês do
            # seu início, sem precisar de âncora especial pra semanas que cruzam
            # a virada do mês (isso só acontecia com semana ISO segunda-domingo).
            semana = min(4, (inicio.day - 1) // 7 + 1)
            return f"Semana {semana} - {MESES_PT[inicio.month - 1]}/{inicio.year}"
        if periodicidade == 'quinzenal':
            quinzena = 1 if inicio.day <= 15 else 2
            return f"{quinzena}ª Quinzena - {MESES_PT[inicio.month - 1]}/{inicio.year}"
        if periodicidade == 'diaria':
            return inicio.strftime('%d/%m/%Y')
        # mensal (e demais): apenas Mês/Ano
        return f"{MESES_PT[inicio.month - 1]}/{inicio.year}"

    def to_dict(self):
        prazo_limite = self.prazo_limite
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
            'periodo_label': self.periodo_label,
            'prazo_limite': prazo_limite.isoformat() if prazo_limite else None,
            'periodicidade': self.periodicidade,
            'status': self.status,
            'data_conclusao': self.data_conclusao.replace(tzinfo=timezone.utc).isoformat() if self.data_conclusao else None,
            'comentario': self.comentario,
            'justificativa': self.justificativa,
            'acao_corretiva': self.acao_corretiva,
            'novo_prazo': self.novo_prazo.isoformat() if self.novo_prazo else None,
            'responsavel_acao': self.responsavel_acao,
            'responsavel_id': self.responsavel_id,
            'responsavel_nome': self.responsavel.nome if self.responsavel else None,
            'checklist': self.checklist,
            'relatorio': self.relatorio,
            'plano_semana': self.plano_semana,
            'visitas_ativacoes': self.visitas_ativacoes,
            'resultados_visita': self.resultados_visita,
            'carteira_ativa': self.carteira_ativa,
            'metas_canal': self.metas_canal,
            'formulario_comercial': self.formulario_comercial,
            'formulario_preenchido': self.formulario_preenchido or False,
            'status_aprovacao': self.status_aprovacao,
            'aprovador_id': self.aprovador_id,
            'aprovador_nome': self.aprovador.nome if self.aprovador else None,
            'data_aprovacao': self.data_aprovacao.replace(tzinfo=timezone.utc).isoformat() if self.data_aprovacao else None,
            'motivo_reprovacao': self.motivo_reprovacao,
            'prazo_reenvio': self.prazo_reenvio.isoformat() if self.prazo_reenvio else None,
            'pendente_prazo': (
                self.atividade.obrigatoria
                and self.status in ['nao_iniciada', 'em_andamento']
                and prazo_limite
                and prazo_limite < hoje_br()
            ) if self.atividade else False,
            # Vencida = obrigatória cujo prazo já passou (qualquer status). Usada
            # para tratar a atividade como pendência mesmo já marcada "não realizada".
            'vencida': bool(
                self.atividade
                and self.atividade.obrigatoria
                and prazo_limite
                and prazo_limite < hoje_br()
            ) if self.atividade else False,
            # Período gerado antecipadamente (painel de aderência mensal) mas
            # que ainda não começou — bloqueada pra edição/conclusão até chegar.
            'ainda_nao_liberada': bool(
                self.periodo_inicio and self.periodo_inicio > hoje_br()
            ),
            'evidencias': [e.to_dict() for e in self.evidencias],
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None,
            'atualizado_em': self.atualizado_em.replace(tzinfo=timezone.utc).isoformat() if self.atualizado_em else None
        }


class Evidencia(db.Model):
    __tablename__ = 'evidencias'
    id = db.Column(db.Integer, primary_key=True)
    rotina_id = db.Column(db.Integer, db.ForeignKey('rotinas.id'), nullable=False)
    nome_arquivo = db.Column(db.String(255))
    url = db.Column(db.Text)
    tipo = db.Column(db.String(255))
    conteudo = db.Column(db.LargeBinary, nullable=True)
    criado_em = db.Column(db.DateTime, default=get_now_br)

    def to_dict(self):
        return {
            'id': self.id,
            'rotina_id': self.rotina_id,
            'nome_arquivo': self.nome_arquivo,
            'url': self.url,
            'tipo': self.tipo,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    entidade = db.Column(db.String(100), nullable=False)
    entidade_id = db.Column(db.String(50))
    acao = db.Column(db.String(50), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    detalhes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=get_now_br)
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
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
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
    criado_em = db.Column(db.DateTime, default=get_now_br)
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
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class AprovacaoRotina(db.Model):
    __tablename__ = 'aprovacoes_rotinas'
    id = db.Column(db.Integer, primary_key=True)
    rotina_id = db.Column(db.Integer, db.ForeignKey('rotinas.id'), nullable=False)
    aprovador_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    acao = db.Column(db.String(20), nullable=False)  # aprovada, reprovada
    motivo = db.Column(db.Text)
    duracao_revisao_segundos = db.Column(db.Integer, nullable=True)
    criado_em = db.Column(db.DateTime, default=get_now_br)
    aprovador = db.relationship('Usuario', lazy=True)
    rotina_rel = db.relationship('Rotina', foreign_keys=[rotina_id], lazy=True, overlaps='aprovacoes')

    def to_dict(self):
        return {
            'id': self.id,
            'rotina_id': self.rotina_id,
            'rotina_nome': self.rotina_rel.atividade.nome if self.rotina_rel and self.rotina_rel.atividade else None,
            'aprovador_id': self.aprovador_id,
            'aprovador_nome': self.aprovador.nome if self.aprovador else None,
            'acao': self.acao,
            'motivo': self.motivo,
            'duracao_revisao_segundos': self.duracao_revisao_segundos,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None
        }


class FechamentoPeriodo(db.Model):
    """Snapshot do percentual de execução de um usuário num período (semana/mês)
    já encerrado — gravado só depois que a folga de conclusão (e a janela de
    reenvio pós-reprovação) já expiraram, pra não travar um número que uma
    aprovação tardia ainda poderia mudar. Dá uma série histórica estável, sem
    precisar reconsultar Rotina toda vez (base pra tendência de aderência)."""
    __tablename__ = 'fechamentos_periodo'
    __table_args__ = (
        db.UniqueConstraint('usuario_id', 'periodicidade', 'periodo_inicio', name='uq_fechamento_usuario_periodo'),
    )
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    periodicidade = db.Column(db.String(20), nullable=False)
    periodo_inicio = db.Column(db.Date, nullable=False)
    periodo_fim = db.Column(db.Date, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    concluidas = db.Column(db.Integer, nullable=False)
    percentual_execucao = db.Column(db.Float, nullable=False)
    fechado_em = db.Column(db.DateTime, default=get_now_br)
    usuario = db.relationship('Usuario', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'periodicidade': self.periodicidade,
            'periodo_inicio': self.periodo_inicio.isoformat() if self.periodo_inicio else None,
            'periodo_fim': self.periodo_fim.isoformat() if self.periodo_fim else None,
            'total': self.total,
            'concluidas': self.concluidas,
            'percentual_execucao': self.percentual_execucao,
            'fechado_em': self.fechado_em.replace(tzinfo=timezone.utc).isoformat() if self.fechado_em else None,
        }


class Notificacao(db.Model):
    """Notificação in-app para o usuário designado como responsável por uma
    atividade delegada por outra pessoa (ex.: Plano de Ação de uma Rotina cujo
    responsavel_id difere do dono/criador). Fica não lida até o destinatário
    abrir a atividade referenciada ou ela ser concluída."""
    __tablename__ = 'notificacoes'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)  # destinatário
    criado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    tipo = db.Column(db.String(50), nullable=False, default='atividade_delegada')
    titulo = db.Column(db.String(200), nullable=False)
    mensagem = db.Column(db.Text)
    rotina_id = db.Column(db.Integer, db.ForeignKey('rotinas.id'), nullable=True)
    lida = db.Column(db.Boolean, default=False)
    lida_em = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, default=get_now_br)
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], lazy=True)
    criado_por = db.relationship('Usuario', foreign_keys=[criado_por_id], lazy=True)
    rotina = db.relationship('Rotina', foreign_keys=[rotina_id], lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'titulo': self.titulo,
            'mensagem': self.mensagem,
            'rotina_id': self.rotina_id,
            'atividade_nome': self.rotina.atividade.nome if self.rotina and self.rotina.atividade else None,
            'criado_por_id': self.criado_por_id,
            'criado_por_nome': self.criado_por.nome if self.criado_por else None,
            'lida': self.lida,
            'lida_em': self.lida_em.replace(tzinfo=timezone.utc).isoformat() if self.lida_em else None,
            'criado_em': self.criado_em.replace(tzinfo=timezone.utc).isoformat() if self.criado_em else None,
        }
