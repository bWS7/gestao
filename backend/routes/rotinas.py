import csv
import io
import json
import os
import uuid
from flask import Blueprint, request, jsonify, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from backend.audit import log_audit
from backend.utils.dates import get_now_br, hoje_br
from backend.models import Rotina, AtividadeCatalogo, Usuario, HistoricoRotina, Evidencia, AuditLog, FechamentoPeriodo, Notificacao, GRACE_DAYS_BY_PERIODICIDADE, GRACE_DAYS_REENVIO
from backend.constants import atividade_requer_aprovacao
from backend.extensions import db
from datetime import date, timedelta, datetime, timezone
from dateutil.relativedelta import relativedelta

rotinas_bp = Blueprint('rotinas', __name__)

PERIODICIDADES = ('diaria', 'semanal', 'quinzenal', 'mensal')


def get_current_user():
    uid = int(get_jwt_identity())
    return Usuario.query.get_or_404(uid)


def can_access_rotina(me, rotina):
    if me.perfil == 'admin':
        return True
    if rotina.responsavel_id == me.id:
        # Responsável por uma ação delegada nesta rotina (ex.: Plano de Ação)
        # pode visualizar a atividade mesmo sem ser o dono, pra acompanhar via
        # a notificação recebida — mas não editá-la (ver can_edit_rotina).
        return True
    if me.perfil == 'sr':
        return rotina.usuario and rotina.usuario.regional_id == me.regional_id
    if rotina.usuario_id == me.id:
        return True
    # Foi delegado num item do Relatório Comercial (plano de ação, riscos,
    # etc.) sem ser o responsavel_id "oficial" da rotina — ainda assim
    # recebeu notificação, então precisa poder abrir a atividade a partir
    # dela (ver salvar_formulario / área de Notificações).
    return Notificacao.query.filter_by(rotina_id=rotina.id, usuario_id=me.id).first() is not None


def can_edit_rotina(me, rotina):
    """Permissao de ESCRITA (preencher relatorio, alterar status, anexos).
    Apenas o admin e o proprio dono da rotina podem editar. O Superintendente
    pode visualizar/aprovar, mas NUNCA preencher o relatorio de terceiros."""
    return me.perfil == 'admin' or rotina.usuario_id == me.id


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


def _criar_notificacao_delegacao(rotina, destinatario_id, ator, contexto):
    """Cria a notificação de atividade delegada (Seção 4) pra um destinatário,
    se ainda não houver uma não lida desta mesma rotina pra ele — evita
    duplicar notificação a cada novo salvamento enquanto o responsável não
    muda de fato. `contexto` identifica de onde veio a delegação na mensagem
    ("...responsável por {contexto} na atividade...")."""
    if not destinatario_id or destinatario_id == rotina.usuario_id:
        return
    ja_existe = Notificacao.query.filter_by(
        rotina_id=rotina.id, usuario_id=destinatario_id, lida=False
    ).first()
    if ja_existe:
        return
    nome_atividade = rotina.atividade.nome if rotina.atividade else 'uma atividade'
    nome_ator = ator.nome if ator else (rotina.usuario.nome if rotina.usuario else 'Alguém')
    db.session.add(Notificacao(
        usuario_id=destinatario_id,
        criado_por_id=ator.id if ator else rotina.usuario_id,
        tipo='atividade_delegada',
        titulo=f'Você foi designado responsável: {nome_atividade}',
        mensagem=f'{nome_ator} definiu você como responsável por {contexto} na atividade "{nome_atividade}" ({rotina.usuario.nome if rotina.usuario else "—"}).',
        rotina_id=rotina.id,
    ))


def notificar_delegacao(rotina, ator):
    """Notificação de delegação do campo oficial da rotina (responsavel_id —
    "Responsável pela Ação" no RotinaModal)."""
    _criar_notificacao_delegacao(rotina, rotina.responsavel_id, ator, 'esta ação')


def _extrair_responsavel_ids(no):
    """Varre recursivamente o JSON do Relatório Comercial (formato varia por
    tipo de relatório: listas de plano de ação, riscos, blocos repetíveis,
    campos únicos) coletando todo usuario_id atribuído a um campo
    "Responsável" — reconhecido pela chave literal 'responsavel_id' em
    qualquer nível. Usado para notificar quem foi delegado dentro do
    relatório (Seção 4), não só no campo oficial da rotina."""
    ids = set()
    if isinstance(no, dict):
        valor = no.get('responsavel_id')
        if valor:
            try:
                ids.add(int(valor))
            except (TypeError, ValueError):
                pass
        for v in no.values():
            ids |= _extrair_responsavel_ids(v)
    elif isinstance(no, list):
        for item in no:
            ids |= _extrair_responsavel_ids(item)
    return ids


def notificar_delegacoes_formulario(rotina, formulario, ator):
    """Notifica cada usuário distinto encontrado como responsável em algum
    campo/linha do Relatório Comercial recém-salvo (ver _extrair_responsavel_ids)."""
    for destinatario_id in _extrair_responsavel_ids(formulario):
        if destinatario_id == ator.id:
            continue
        _criar_notificacao_delegacao(rotina, destinatario_id, ator, 'um item do relatório')


def marcar_notificacoes_lidas_por_rotina(rotina, usuario_id=None):
    """Marca como lidas as notificações desta rotina — de um destinatário
    específico (ao visualizar a atividade) ou de todos (quando a atividade é
    concluída), conforme pedido: a notificação some quando a atividade é
    visualizada OU concluída."""
    query = Notificacao.query.filter_by(rotina_id=rotina.id, lida=False)
    if usuario_id:
        query = query.filter_by(usuario_id=usuario_id)
    pendentes = query.all()
    for n in pendentes:
        n.lida = True
        n.lida_em = get_now_br()
    return len(pendentes)


def allowed_file(filename):
    # Aceita qualquer tipo de documento, slide, planilha, imagem, etc.
    # Bloqueia apenas executaveis/scripts por seguranca — os arquivos sao
    # sempre servidos como download (Content-Disposition: attachment).
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    bloqueadas = {
        'exe', 'msi', 'bat', 'cmd', 'com', 'scr', 'pif', 'sh', 'bash',
        'ps1', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh', 'jar', 'dll', 'app', 'apk',
    }
    return ext not in bloqueadas


def get_periodo(tipo, referencia=None):
    hoje = referencia or hoje_br()
    if tipo == 'diaria':
        inicio = hoje
        fim = hoje
    elif tipo == 'semanal':
        # Semana de calendário fixa (não ISO segunda-domingo): 01-07, 08-14,
        # 15-21, 22-fim do mês — mesmo espírito do quinzenal abaixo (âncora no
        # dia do mês, não no dia da semana). A semana 4 é sempre a mais longa
        # (7 a 10 dias, conforme o mês).
        ultimo_dia_mes = (hoje.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
        if hoje.day <= 7:
            inicio, fim = hoje.replace(day=1), hoje.replace(day=7)
        elif hoje.day <= 14:
            inicio, fim = hoje.replace(day=8), hoje.replace(day=14)
        elif hoje.day <= 21:
            inicio, fim = hoje.replace(day=15), hoje.replace(day=21)
        else:
            inicio, fim = hoje.replace(day=22), ultimo_dia_mes
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


def _semanas_do_mes(referencia):
    """As 4 semanas de calendário fixas do mês que contém `referencia` (mesmos
    limites de get_periodo('semanal', ...)), como lista de (numero, inicio, fim).
    Reaproveitado pela reconciliação de dados (Fase A) e pelo endpoint de
    aderência mensal (Fase B)."""
    primeiro_dia_mes = referencia.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)
    limites = []
    for numero, dia_inicio in enumerate((1, 8, 15, 22), start=1):
        inicio = primeiro_dia_mes.replace(day=dia_inicio)
        fim = primeiro_dia_mes.replace(day=dia_inicio + 6) if numero < 4 else ultimo_dia_mes
        limites.append((numero, inicio, fim))
    return limites


def reconciliar_semanas_mes_atual():
    """Corrige, de forma idempotente, o periodo_inicio/periodo_fim de rotinas
    semanais do MÊS CORRENTE que foram geradas sob o esquema antigo (semana ISO
    segunda-domingo) antes da redefinição para semanas de calendário fixas (ver
    get_periodo). Só mexe no mês corrente — meses anteriores, já históricos,
    ficam como estão.

    Nunca cria nem apaga rotina: só corrige a data de UMA rotina já existente
    (UPDATE no mesmo registro), preservando status/comentário/evidências/
    relatório/histórico — que continuam ligados pelo mesmo id. Se por acaso já
    existir outra rotina (mesmo usuário+atividade) exatamente na semana nova de
    destino — colisão extremamente rara, só possível se duas rotinas antigas de
    semanas ISO diferentes caírem na mesma semana nova —, essa rotina é pulada
    em vez de mesclada ou sobrescrita, para nunca apagar dado silenciosamente.

    Chamada uma vez no startup da aplicação (mesmo padrão de
    _ensure_runtime_columns em app.py), antes de qualquer rotina ser gerada sob
    o esquema novo — evita a corrida em que uma rotina antiga (data errada) e
    uma nova (criada por engano pra mesma semana) coexistiriam duplicadas."""
    hoje = hoje_br()
    primeiro_dia_mes = hoje.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)
    semanas = _semanas_do_mes(hoje)
    limites_validos = {(inicio, fim) for _, inicio, fim in semanas}

    candidatas = Rotina.query.filter(
        Rotina.periodicidade == 'semanal',
        Rotina.periodo_inicio >= primeiro_dia_mes,
        Rotina.periodo_inicio <= ultimo_dia_mes,
    ).all()

    corrigidas = 0
    for r in candidatas:
        if (r.periodo_inicio, r.periodo_fim) in limites_validos:
            continue  # já está no esquema novo (geração recente ou reconciliação anterior)

        novo_inicio = novo_fim = None
        for _, inicio, fim in semanas:
            if inicio <= r.periodo_inicio <= fim:
                novo_inicio, novo_fim = inicio, fim
                break
        if novo_inicio is None:
            continue  # não deveria acontecer (toda data do mês cai em alguma semana) — pula por segurança

        conflito = Rotina.query.filter(
            Rotina.id != r.id,
            Rotina.usuario_id == r.usuario_id,
            Rotina.atividade_id == r.atividade_id,
            Rotina.periodo_inicio == novo_inicio,
        ).first()
        if conflito:
            continue  # não perde dado: deixa como está pra revisão manual em vez de mesclar/sobrescrever

        r.periodo_inicio = novo_inicio
        r.periodo_fim = novo_fim
        corrigidas += 1

    if corrigidas:
        db.session.commit()
    return corrigidas


def filtro_periodo_atual(model, referencia):
    from sqlalchemy import or_, and_

    filtros = []
    for periodicidade in PERIODICIDADES:
        inicio, fim = get_periodo(periodicidade, referencia)
        filtros.append(and_(
            model.periodicidade == periodicidade,
            model.periodo_inicio >= inicio,
            model.periodo_fim <= fim
        ))
    return or_(*filtros)


def filtro_carry_over(model, referencia):
    """Filtro (OR) das atividades obrigatórias de períodos anteriores ainda dentro
    da folga de prazo (ex.: semanal = +3 dias) e em aberto — para continuarem
    visíveis na aba do período corrente em vez de sumirem na virada do período.
    Também mantém visível a atividade reprovada cujo prazo_reenvio ainda não
    expirou, mesmo que isso ultrapasse a folga padrão (o aprovador pode demorar
    para revisar).
    Só se aplica quando se está vendo o período que contém a data de hoje."""
    from sqlalchemy import or_, and_

    hoje = hoje_br()
    filtros = []
    for periodicidade, grace in GRACE_DAYS_BY_PERIODICIDADE.items():
        if not grace:
            continue
        inicio, fim = get_periodo(periodicidade, referencia)
        if not (inicio <= hoje <= fim):
            continue
        filtros.append(and_(
            model.periodicidade == periodicidade,
            model.periodo_fim < inicio,
            model.status.in_(['nao_iniciada', 'em_andamento']),
            or_(
                model.periodo_fim >= hoje - timedelta(days=grace),
                and_(
                    model.status_aprovacao == 'reprovada',
                    model.prazo_reenvio.isnot(None),
                    model.prazo_reenvio >= hoje,
                ),
            )
        ))
    return or_(*filtros) if filtros else None


def condicao_periodo_rotinas(periodo, referencia, data_inicio_str=None, data_fim_str=None, historico=False, modo=None):
    """Condição (SQLAlchemy) de período usada tanto na listagem quanto na exportação
    de rotinas. Retorna None quando não há nenhuma restrição de período a aplicar
    (chamador deve pular o .filter() nesse caso).

    `modo` ('atual' | 'historico' | 'intervalo') é o jeito explícito e preferencial
    de escolher o comportamento — reduz a inferência implícita a partir da
    combinação de data_inicio/data_fim/historico, que já causou um bug real de
    semântica de datas (sobreposição vs. contido). Se omitido (compatibilidade com
    os chamadores atuais), o modo é inferido dos parâmetros presentes, exatamente
    como antes.

    - intervalo (data_inicio/data_fim): filtro pelo período próprio de cada rotina
      (seu periodo_inicio e periodo_fim) contido no intervalo escolhido — não por
      sobreposição. Contido é proposital: com sobreposição, uma janela curta (ex.:
      01/07 a 02/07) também traria rotinas semanais/quinzenais/mensais cujo período
      apenas toca a borda da janela (ex.: uma semanal de 29/06 a 05/07), inundando
      o resultado e escondendo as diárias que o usuário queria ver (ex.: Checklist
      de Abertura do Stand, cujo período é o próprio dia). Mesmo critério já usado
      no filtro de datas de Relatórios de Preenchimento.

    - historico: sem nenhuma restrição de período — histórico completo, só
      filtrando por tipo de periodicidade se um tipo específico foi escolhido.
      Usado pela aba Acompanhamento, que existe justamente para revisar o
      histórico (não só o período corrente).

    - atual: comportamento original, restrito ao período atual de cada
      periodicidade (+ folga de carry-over quando aplicável). Usado pela tela de
      rotinas do próprio colaborador, que deve mostrar as tarefas do momento.

    Isso importa porque atividades diárias (ex.: Checklist de Abertura do Stand)
    não têm folga configurada em GRACE_DAYS_BY_PERIODICIDADE: no modo atual, sem
    historico/intervalo, só ficam visíveis no próprio dia em que foram criadas."""
    from sqlalchemy import or_, and_

    if modo is None:
        if data_inicio_str or data_fim_str:
            modo = 'intervalo'
        elif historico:
            modo = 'historico'
        else:
            modo = 'atual'

    if modo == 'intervalo':
        condicoes = []
        if data_inicio_str:
            condicoes.append(Rotina.periodo_inicio >= date.fromisoformat(data_inicio_str))
        if data_fim_str:
            condicoes.append(Rotina.periodo_fim <= date.fromisoformat(data_fim_str))
        if periodo != 'todas':
            condicoes.append(Rotina.periodicidade == periodo)
        return and_(*condicoes) if condicoes else None

    if modo == 'historico':
        return Rotina.periodicidade == periodo if periodo != 'todas' else None

    carry = filtro_carry_over(Rotina, referencia)
    if periodo == 'todas':
        base = filtro_periodo_atual(Rotina, referencia)
    else:
        inicio, fim = get_periodo(periodo, referencia)
        base = and_(
            Rotina.periodo_inicio >= inicio,
            Rotina.periodo_fim <= fim,
            Rotina.periodicidade == periodo
        )
        # No modo por periodicidade, restringe o carry-over à periodicidade vista.
        if carry is not None:
            carry = and_(carry, Rotina.periodicidade == periodo)

    return or_(base, carry) if carry is not None else base


def _stats_execucao(rotinas):
    """Total/concluídas/percentual de execução de uma lista de Rotina — mesma
    definição de "concluída" usada em toda a aplicação (aprovação pendente conta
    como cumprida; reprovada não)."""
    total = len(rotinas)
    concluidas = sum(1 for r in rotinas if r.status == 'concluida' and r.status_aprovacao != 'reprovada')
    percentual = round((concluidas / total * 100), 1) if total else 0
    return {'total': total, 'concluidas': concluidas, 'percentual_execucao': percentual}


def _stats_liderado(rotinas):
    """Total/concluídas/pendentes/atrasadas de uma lista de Rotina de UM
    liderado — base do Relatório Comparativo das Rotinas dos Liderados
    (Seção 3): concluída (mesma regra de _stats_execucao), atrasada (vencida
    — prazo já passou — ou já registrada como Não Realizada) e pendente
    (nem uma coisa nem outra: ainda em prazo)."""
    total = len(rotinas)
    concluidas = pendentes = atrasadas = 0
    for r in rotinas:
        if r.status == 'concluida' and r.status_aprovacao != 'reprovada':
            concluidas += 1
        elif r.status == 'nao_realizada' or rotina_vencida(r):
            atrasadas += 1
        else:
            pendentes += 1
    percentual = round((concluidas / total * 100), 1) if total else 0
    return {
        'total': total, 'concluidas': concluidas, 'pendentes': pendentes,
        'atrasadas': atrasadas, 'percentual_execucao': percentual,
    }


def _janela_anterior_em_carencia(referencia, periodicidades):
    """Monta a condição (SQLAlchemy) do(s) período(s) imediatamente anterior(es)
    ao que contém `referencia`, restrita às periodicidades que têm folga
    configurada (GRACE_DAYS_BY_PERIODICIDADE) E cujo período anterior ainda está
    dentro dessa folga hoje. Retorna (condicao, prazo_final) — ou (None, None) se
    nenhuma periodicidade relevante estiver nessa janela agora.

    Existe pra calcular o percentual do período "ainda em prazo de preenchimento"
    separado do período atual (Fase 2) — não confundir com filtro_carry_over, que
    filtra por status (só itens em aberto) e serve pra decidir o que continua
    aparecendo na LISTAGEM, não pra métrica de desempenho (que precisa de todas as
    rotinas do período anterior, concluídas ou não, pra calcular o percentual real
    daquele período)."""
    from sqlalchemy import or_, and_

    hoje = hoje_br()
    condicoes = []
    prazo_mais_distante = None
    for periodicidade in periodicidades:
        grace = GRACE_DAYS_BY_PERIODICIDADE.get(periodicidade)
        if not grace:
            continue
        inicio_atual, _ = get_periodo(periodicidade, referencia)
        inicio_ant, fim_ant = get_periodo(periodicidade, inicio_atual - timedelta(days=1))
        prazo_final = fim_ant + timedelta(days=grace)
        if hoje > prazo_final:
            continue
        condicoes.append(and_(
            Rotina.periodicidade == periodicidade,
            Rotina.periodo_inicio == inicio_ant,
            Rotina.periodo_fim == fim_ant,
        ))
        if prazo_mais_distante is None or prazo_final > prazo_mais_distante:
            prazo_mais_distante = prazo_final
    if not condicoes:
        return None, None
    return or_(*condicoes), prazo_mais_distante


def rotina_vencida_pendente(rotina):
    prazo_limite = rotina.prazo_limite
    return (
        rotina.atividade
        and rotina.atividade.obrigatoria
        and rotina.status in ['nao_iniciada', 'em_andamento']
        and prazo_limite
        and prazo_limite < hoje_br()
    )


def rotina_vencida(rotina):
    """Atividade obrigatória cujo prazo (com folga) já passou — independente do status."""
    prazo_limite = rotina.prazo_limite
    return bool(
        rotina.atividade
        and rotina.atividade.obrigatoria
        and prazo_limite
        and prazo_limite < hoje_br()
    )


def rotina_ainda_nao_liberada(rotina):
    """O período da rotina ainda não começou (ex.: Semana 3 gerada
    antecipadamente pelo painel mensal, mas hoje ainda estamos na Semana 2) —
    bloqueada pra edição/conclusão até a data de início chegar."""
    return bool(rotina.periodo_inicio and rotina.periodo_inicio > hoje_br())


def rotina_justificada(rotina):
    """Pendência já justificada: justificativa (comentario) e plano de ação (plano_semana) preenchidos."""
    return bool((rotina.comentario or '').strip() and (rotina.plano_semana or '').strip())


def marcar_vencidas_nao_realizadas(rotinas, ator_id=None):
    """Marca automaticamente como 'nao_realizada' as atividades obrigatórias vencidas
    que ainda estão 'nao_iniciada'/'em_andamento'. Idempotente (só altera o que precisa)."""
    mudou = False
    for r in rotinas:
        if r.status in ('nao_iniciada', 'em_andamento') and rotina_vencida(r):
            anterior = r.status
            r.status = 'nao_realizada'
            add_rotina_history(
                r, ator_id or r.usuario_id, 'mudanca_status',
                observacao='Marcada automaticamente como Não Realizada (prazo vencido).',
                status_anterior=anterior, status_novo='nao_realizada'
            )
            mudou = True
    if mudou:
        db.session.commit()
    return mudou


def _gerar_rotinas_para_usuarios(usuario_ids=None, referencia=None, periodicidade_filtro=None):
    """Núcleo da geração de rotinas — reaproveitado pelo endpoint administrativo
    (/gerar, disparado manualmente por um admin) e pelo endpoint de cron
    (/interno/gerar-e-fechar, disparado por um agendador externo). Idempotente,
    mesmo padrão de ensure_rotinas_atuais."""
    referencia = referencia or hoje_br()
    query = Usuario.query.filter_by(status='ativo')
    if usuario_ids and isinstance(usuario_ids, list) and len(usuario_ids) > 0:
        query = query.filter(Usuario.id.in_(usuario_ids))
    usuarios = query.all()

    criadas = 0
    for usuario in usuarios:
        cat_query = AtividadeCatalogo.query.filter(
            AtividadeCatalogo.perfil.in_(usuario.perfis_list),
            AtividadeCatalogo.ativo == True
        )
        if periodicidade_filtro and periodicidade_filtro != 'todas':
            cat_query = cat_query.filter_by(periodicidade=periodicidade_filtro)

        atividades = cat_query.all()
        for atividade in atividades:
            inicio, fim = get_periodo(atividade.periodicidade, referencia)
            existe = Rotina.query.filter_by(
                usuario_id=usuario.id,
                atividade_id=atividade.id,
                periodo_inicio=inicio
            ).first()
            if not existe:
                db.session.add(Rotina(
                    usuario_id=usuario.id,
                    atividade_id=atividade.id,
                    periodo_inicio=inicio,
                    periodo_fim=fim,
                    periodicidade=atividade.periodicidade
                ))
                criadas += 1

    db.session.commit()
    return criadas


@rotinas_bp.route('/gerar', methods=['POST'])
@jwt_required()
def gerar_rotinas():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    data = request.get_json() or {}
    usuario_ids = data.get('usuario_ids')  # Lista de IDs ou None para todos
    referencia_str = data.get('referencia')
    periodicidade_filtro = data.get('periodicidade') # 'diaria', 'semanal', 'quinzenal', 'mensal' ou None
    referencia = date.fromisoformat(referencia_str) if referencia_str else hoje_br()

    if not periodicidade_filtro or periodicidade_filtro == 'todas':
        # "Todas" gera o mês inteiro (semanas/quinzenas/mês/dias), não só o
        # período atual — mesma geração usada em "Minhas Rotinas".
        criadas = _gerar_mes_para_usuarios(usuario_ids, referencia)
    else:
        criadas = _gerar_rotinas_para_usuarios(usuario_ids, referencia, periodicidade_filtro)
    return jsonify({'mensagem': f'{criadas} rotinas geradas com sucesso', 'total': criadas})


@rotinas_bp.route('/interno/gerar-e-fechar', methods=['POST'])
def gerar_e_fechar_automatico():
    """Endpoint pra ser chamado por um agendador externo (Cron Schedule do
    Railway — ver Fase 4a do plano de rotinas), não por usuários logados.
    Autenticado por segredo estático (env var CRON_SECRET, header
    X-Cron-Secret), não por JWT — evita depender de um token de usuário que
    pode expirar/ser revogado.

    Cobre, pra todos os usuários ativos e independente de login: geração das
    rotinas do mês inteiro (semanas/quinzenas/mês/dias — não só o período
    atual, pra que os dashboards de admin/superintendente reflitam o mês
    completo mesmo pra quem não abriu "Minhas Rotinas" ainda), marcação
    automática de vencidas como não realizadas, e fechamento dos períodos cuja
    folga já expirou (Fase 3)."""
    secret = os.environ.get('CRON_SECRET')
    if not secret or request.headers.get('X-Cron-Secret') != secret:
        return jsonify({'erro': 'Acesso negado'}), 403

    criadas = _gerar_mes_para_usuarios()

    rotinas_abertas = Rotina.query.filter(Rotina.status.in_(['nao_iniciada', 'em_andamento'])).all()
    marcar_vencidas_nao_realizadas(rotinas_abertas)

    fechados = 0
    for usuario in Usuario.query.filter_by(status='ativo').all():
        fechados += fechar_periodos_pendentes(usuario)

    return jsonify({
        'rotinas_geradas': criadas,
        'periodos_fechados': fechados,
    })


def ensure_rotinas_atuais(usuario, referencia=None):
    """Geração automática (Seção 3): cria, de forma idempotente, as rotinas do
    período atual (semanal/quinzenal/mensal/diária) para o usuário, conforme o
    catálogo do seu perfil. Chamado ao acessar as rotinas, sem necessidade de
    agendador externo."""
    if not usuario or not usuario.perfis_list:
        return 0
    referencia = referencia or hoje_br()
    atividades = AtividadeCatalogo.query.filter(
        AtividadeCatalogo.perfil.in_(usuario.perfis_list),
        AtividadeCatalogo.ativo == True
    ).all()
    criadas = 0
    for atividade in atividades:
        inicio, fim = get_periodo(atividade.periodicidade, referencia)
        existe = Rotina.query.filter_by(
            usuario_id=usuario.id,
            atividade_id=atividade.id,
            periodo_inicio=inicio
        ).first()
        if not existe:
            db.session.add(Rotina(
                usuario_id=usuario.id,
                atividade_id=atividade.id,
                periodo_inicio=inicio,
                periodo_fim=fim,
                periodicidade=atividade.periodicidade
            ))
            criadas += 1
    if criadas:
        db.session.commit()
    return criadas


def _dias_do_mes(primeiro_dia_mes, ultimo_dia_mes):
    """Lista de todas as datas do mês, um dia por vez — usado pela geração
    antecipada de atividades diárias em ensure_rotinas_mes."""
    dias = []
    d = primeiro_dia_mes
    while d <= ultimo_dia_mes:
        dias.append(d)
        d += timedelta(days=1)
    return dias


def ensure_rotinas_mes(usuario, referencia=None):
    """Gera, de forma idempotente, TODAS as rotinas do MÊS que contém
    `referencia` para o usuário — as 4 semanas, as 2 quinzenas, o período
    mensal, e cada dia do mês (não só o período corrente, como
    ensure_rotinas_atuais). Mesmo check de idempotência (usuario+atividade+
    periodo_inicio), então nunca duplica o que ensure_rotinas_atuais já tiver
    criado.

    Isso é o que permite o painel de Aderência Mensal mostrar o total certo
    pra um período que ainda não chegou (ex.: "Semana 3: 0 de 6" antes do dia
    15) e a lista de atividades de verdade ao clicar num card futuro — mesmo
    que bloqueadas pra edição até a data chegar (ver checagem de
    "ainda não liberada" em atualizar()/upload_evidencia()/salvar_formulario()).

    Chamada só a partir de minha_aderencia_mensal() — é a única tela que
    precisa do mês inteiro; as demais (listar(), exportar, etc.) continuam
    usando ensure_rotinas_atuais, que já basta pra elas."""
    if not usuario or not usuario.perfis_list:
        return 0
    referencia = referencia or hoje_br()
    primeiro_dia_mes = referencia.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)

    periodos_por_tipo = {
        'semanal': [(inicio, fim) for _, inicio, fim in _semanas_do_mes(referencia)],
        'quinzenal': [
            get_periodo('quinzenal', primeiro_dia_mes),
            get_periodo('quinzenal', primeiro_dia_mes.replace(day=16)),
        ],
        'mensal': [get_periodo('mensal', referencia)],
        'diaria': [(dia, dia) for dia in _dias_do_mes(primeiro_dia_mes, ultimo_dia_mes)],
    }

    atividades = AtividadeCatalogo.query.filter(
        AtividadeCatalogo.perfil.in_(usuario.perfis_list),
        AtividadeCatalogo.ativo == True
    ).all()

    criadas = 0
    for atividade in atividades:
        alvos = periodos_por_tipo.get(atividade.periodicidade)
        if not alvos:
            continue
        for inicio, fim in alvos:
            existe = Rotina.query.filter_by(
                usuario_id=usuario.id, atividade_id=atividade.id, periodo_inicio=inicio
            ).first()
            if not existe:
                db.session.add(Rotina(
                    usuario_id=usuario.id, atividade_id=atividade.id,
                    periodo_inicio=inicio, periodo_fim=fim, periodicidade=atividade.periodicidade,
                ))
                criadas += 1
    if criadas:
        db.session.commit()
    return criadas


def _gerar_mes_para_usuarios(usuario_ids=None, referencia=None):
    """Mesma ideia de _gerar_rotinas_para_usuarios, mas gera o mês inteiro (via
    ensure_rotinas_mes) pra cada usuário ativo, em vez de só o período atual.
    Usada pelo cron diário e pelo endpoint administrativo /gerar — sem isso, o
    mês inteiro só era pré-gerado quando o próprio usuário abria "Minhas
    Rotinas" (ensure_rotinas_mes chamado em minha_aderencia_mensal), então um
    colaborador que não tivesse logado ainda não aparecia com o mês completo
    pros dashboards de admin/superintendente."""
    query = Usuario.query.filter_by(status='ativo')
    if usuario_ids and isinstance(usuario_ids, list) and len(usuario_ids) > 0:
        query = query.filter(Usuario.id.in_(usuario_ids))
    usuarios = query.all()

    criadas = 0
    for usuario in usuarios:
        criadas += ensure_rotinas_mes(usuario, referencia)
    return criadas


def fechar_periodos_pendentes(usuario):
    """Grava um FechamentoPeriodo (snapshot) pra qualquer período do usuário cuja
    folga de conclusão E janela de reenvio pós-reprovação já tenham expirado
    hoje — e que ainda não tenha um fechamento gravado. Idempotente (não refecha
    o que já foi fechado), chamado sob demanda, mesmo padrão de
    ensure_rotinas_atuais (sem agendador externo necessário pra esta fase — ver
    Fase 4a do plano pra cobertura independente de login)."""
    hoje = hoje_br()
    periodos = db.session.query(
        Rotina.periodicidade, Rotina.periodo_inicio, Rotina.periodo_fim
    ).filter(
        Rotina.usuario_id == usuario.id,
        Rotina.periodo_fim < hoje,
    ).distinct().all()

    fechados = 0
    for periodicidade, periodo_inicio, periodo_fim in periodos:
        grace = GRACE_DAYS_BY_PERIODICIDADE.get(periodicidade, 0)
        prazo_final = periodo_fim + timedelta(days=grace + GRACE_DAYS_REENVIO)
        if hoje <= prazo_final:
            continue  # ainda dentro da folga ou da janela de reenvio pós-reprovação

        ja_existe = FechamentoPeriodo.query.filter_by(
            usuario_id=usuario.id, periodicidade=periodicidade, periodo_inicio=periodo_inicio
        ).first()
        if ja_existe:
            continue

        rotinas = Rotina.query.filter_by(
            usuario_id=usuario.id, periodicidade=periodicidade, periodo_inicio=periodo_inicio
        ).all()
        stats = _stats_execucao(rotinas)
        db.session.add(FechamentoPeriodo(
            usuario_id=usuario.id, periodicidade=periodicidade,
            periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
            total=stats['total'], concluidas=stats['concluidas'],
            percentual_execucao=stats['percentual_execucao'],
        ))
        fechados += 1
    if fechados:
        db.session.commit()
    return fechados


@rotinas_bp.route('/', methods=['GET'])
@jwt_required()
def listar():
    me = get_current_user()

    # Geração automática das rotinas do período atual do próprio usuário (Seção 3).
    ensure_rotinas_atuais(me)
    # Fecha (grava snapshot) períodos anteriores do próprio usuário cuja folga já
    # expirou, pra alimentar o histórico de aderência (Fase 3).
    fechar_periodos_pendentes(me)

    usuario_id = request.args.get('usuario_id', type=int)
    regional_id = request.args.get('regional_id', type=int)
    atividade_id = request.args.get('atividade_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status = request.args.get('status')
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    historico = request.args.get('historico', '').lower() in ('1', 'true')
    modo = request.args.get('modo')  # 'atual' | 'historico' | 'intervalo' — opcional, ver condicao_periodo_rotinas

    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()

    cond = condicao_periodo_rotinas(periodo, referencia, data_inicio, data_fim, historico, modo)
    query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id)
    if cond is not None:
        query = query.filter(cond)
    if atividade_id:
        query = query.filter(Rotina.atividade_id == atividade_id)

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
    # Visualizar a atividade já "lê" qualquer notificação de delegação que
    # este usuário tenha recebido dela — seja pelo campo oficial (responsavel_id
    # da rotina) ou por um item do Relatório Comercial — sem exigir ação
    # explícita (ver Seção 4).
    if marcar_notificacoes_lidas_por_rotina(r, usuario_id=me.id):
        db.session.commit()
    return jsonify(r.to_dict())


@rotinas_bp.route('/<int:rid>', methods=['PUT'])
@jwt_required()
def atualizar(rid):
    me = get_current_user()
    r = Rotina.query.get_or_404(rid)

    if not can_edit_rotina(me, r):
        return jsonify({'erro': 'Acesso negado'}), 403

    if rotina_ainda_nao_liberada(r):
        return jsonify({'erro': f'Atividade ainda não liberada. Disponível a partir de {r.periodo_inicio.strftime("%d/%m/%Y")}.'}), 400

    data = request.get_json()
    status_anterior = r.status
    responsavel_id_anterior = r.responsavel_id
    vencida_pendente = rotina_vencida(r)

    if 'status' in data:
        if vencida_pendente and data['status'] != 'nao_realizada':
            return jsonify({'erro': 'Atividade vencida. Registre como nao realizada com justificativa e plano de acao.'}), 400
        if data['status'] == 'concluida':
            if not r.formulario_preenchido:
                return jsonify({'erro': 'Preencha o Relatório Comercial antes de concluir a atividade'}), 400
            if not r.evidencias:
                return jsonify({'erro': 'Anexe pelo menos uma evidência antes de concluir a atividade'}), 400
        r.status = data['status']
        if data['status'] == 'concluida' and not r.data_conclusao:
            r.data_conclusao = get_now_br()
            # Atividades isentas (ex.: "Checklist de Abertura do Stand") já são
            # finalizadas na conclusão; as demais aguardam aprovação do Superintendente.
            nome_atividade = r.atividade.nome if r.atividade else None
            r.status_aprovacao = 'pendente' if atividade_requer_aprovacao(nome_atividade) else 'aprovada'
        elif data['status'] != 'concluida':
            r.data_conclusao = None
            # Se o status muda de concluída para outra coisa, resetar o status de aprovação
            if status_anterior == 'concluida' and r.status_aprovacao == 'pendente':
                r.status_aprovacao = 'pendente'

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
    if 'responsavel_id' in data:
        novo_responsavel_id = data['responsavel_id'] or None
        r.responsavel_id = novo_responsavel_id
        # Mantém o nome em texto (responsavel_acao) sincronizado com o usuário
        # escolhido, salvo se o front já mandou um texto explícito neste payload.
        if 'responsavel_acao' not in data:
            responsavel_usuario = Usuario.query.get(novo_responsavel_id) if novo_responsavel_id else None
            r.responsavel_acao = responsavel_usuario.nome if responsavel_usuario else None
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

    if vencida_pendente and r.status != 'nao_realizada':
        return jsonify({'erro': 'Atividade vencida. Nao e possivel preencher ou concluir apos o prazo.'}), 400

    if r.status == 'nao_realizada' and (not r.comentario or not r.plano_semana):
        return jsonify({'erro': 'Justificativa e Plano de Ação são obrigatórios para atividades não realizadas'}), 400

    # Notificação de delegação (Seção 4): dispara quando o responsável muda pra
    # alguém diferente do dono da atividade; a notificação anterior (se houver,
    # de outro responsável) já não importa mais pro novo destinatário.
    if r.responsavel_id != responsavel_id_anterior:
        notificar_delegacao(r, me)

    # Atividade concluída: encerra qualquer notificação de delegação pendente
    # desta rotina, mesmo que o responsável nunca tenha aberto a atividade.
    if r.status == 'concluida' and status_anterior != 'concluida':
        marcar_notificacoes_lidas_por_rotina(r)

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
    if not can_edit_rotina(me, rotina):
        return jsonify({'erro': 'Acesso negado'}), 403
    if rotina_vencida_pendente(rotina):
        return jsonify({'erro': 'Atividade vencida. Nao e possivel anexar evidencias apos o prazo.'}), 400
    if rotina_ainda_nao_liberada(rotina):
        return jsonify({'erro': f'Atividade ainda não liberada. Disponível a partir de {rotina.periodo_inicio.strftime("%d/%m/%Y")}.'}), 400

    arquivo = request.files.get('arquivo')
    if not arquivo or not arquivo.filename:
        return jsonify({'erro': 'Arquivo é obrigatório'}), 400
    if not allowed_file(arquivo.filename):
        return jsonify({'erro': 'Tipo de arquivo não permitido'}), 400

    nome_seguro = secure_filename(arquivo.filename) or 'arquivo'
    nome_final = f"{rotina.id}_{uuid.uuid4().hex}_{nome_seguro}"

    conteudo = arquivo.read()

    try:
        caminho = os.path.join(current_app.config['UPLOAD_FOLDER'], nome_final)
        with open(caminho, 'wb') as f:
            f.write(conteudo)
    except Exception as e:
        current_app.logger.warning(f"Não foi possível salvar arquivo no disco: {e}")

    evidencia = Evidencia(
        rotina_id=rotina.id,
        nome_arquivo=arquivo.filename,
        url=f"/uploads/{nome_final}",
        tipo=(arquivo.mimetype or 'arquivo')[:255],
        conteudo=conteudo,
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
    if not can_edit_rotina(me, rotina):
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
    from sqlalchemy import or_

    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    usuario_id = request.args.get('usuario_id', type=int)
    acao = request.args.get('acao')
    entidade = request.args.get('entidade')
    busca = (request.args.get('busca') or '').strip()
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 50, type=int), 1), 100)

    query = AuditLog.query
    if data_inicio:
        try:
            query = query.filter(AuditLog.criado_em >= datetime.combine(date.fromisoformat(data_inicio), datetime.min.time()))
        except ValueError:
            pass
    if data_fim:
        try:
            query = query.filter(AuditLog.criado_em < datetime.combine(date.fromisoformat(data_fim) + timedelta(days=1), datetime.min.time()))
        except ValueError:
            pass
    if usuario_id:
        query = query.filter(AuditLog.usuario_id == usuario_id)
    if acao:
        query = query.filter(AuditLog.acao == acao)
    if entidade:
        query = query.filter(AuditLog.entidade == entidade)
    if busca:
        like = f'%{busca}%'
        query = query.outerjoin(Usuario, AuditLog.usuario_id == Usuario.id).filter(or_(
            AuditLog.detalhes.ilike(like),
            AuditLog.entidade.ilike(like),
            AuditLog.entidade_id.ilike(like),
            Usuario.nome.ilike(like),
        ))

    total = query.count()
    registros = (query.order_by(AuditLog.criado_em.desc())
                 .offset((page - 1) * per_page).limit(per_page).all())

    # Facets para os filtros (valores distintos existentes nos logs).
    usuarios_facet = [
        {'id': uid, 'nome': nome}
        for uid, nome in db.session.query(Usuario.id, Usuario.nome)
        .join(AuditLog, AuditLog.usuario_id == Usuario.id)
        .distinct().order_by(Usuario.nome).all()
    ]
    acoes_facet = [a for (a,) in db.session.query(AuditLog.acao).distinct().order_by(AuditLog.acao).all() if a]
    entidades_facet = [e for (e,) in db.session.query(AuditLog.entidade).distinct().order_by(AuditLog.entidade).all() if e]

    return jsonify({
        'items': [r.to_dict() for r in registros],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'facets': {
            'usuarios': usuarios_facet,
            'acoes': acoes_facet,
            'entidades': entidades_facet,
        },
    })


@rotinas_bp.route('/minha-aderencia', methods=['GET'])
@jwt_required()
def minha_aderencia():
    me = get_current_user()
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()
    if periodo == 'todas':
        inicio, fim = get_periodo('mensal', referencia)
        rotinas = Rotina.query.filter(
            Rotina.usuario_id == me.id,
            filtro_periodo_atual(Rotina, referencia)
        ).all()
    else:
        inicio, fim = get_periodo(periodo, referencia)
        rotinas = Rotina.query.filter(
            Rotina.usuario_id == me.id,
            Rotina.periodo_inicio >= inicio,
            Rotina.periodo_fim <= fim,
            Rotina.periodicidade == periodo
        ).all()

    stats = _stats_execucao(rotinas)

    # Semana (ou mês) anterior ainda dentro da folga de conclusão: mostrado
    # separado do período atual, pra não "sumir" o resultado do usuário assim que
    # ensure_rotinas_atuais gera o período novo (ver Fase 2 do plano de rotinas).
    periodicidades_relevantes = PERIODICIDADES if periodo == 'todas' else (periodo,)
    cond_anterior, prazo_final = _janela_anterior_em_carencia(referencia, periodicidades_relevantes)
    anterior = None
    if cond_anterior is not None:
        rotinas_anteriores = Rotina.query.filter(Rotina.usuario_id == me.id, cond_anterior).all()
        if rotinas_anteriores:
            inicio_ant = min(r.periodo_inicio for r in rotinas_anteriores)
            fim_ant = max(r.periodo_fim for r in rotinas_anteriores)
            anterior = {
                **_stats_execucao(rotinas_anteriores),
                'periodo_inicio': inicio_ant.isoformat(),
                'periodo_fim': fim_ant.isoformat(),
                'prazo_final': prazo_final.isoformat(),
            }

    return jsonify({
        'periodo': periodo,
        'periodo_inicio': inicio.isoformat(),
        'periodo_fim': fim.isoformat(),
        **stats,
        'anterior': anterior,
    })


@rotinas_bp.route('/minha-aderencia/historico', methods=['GET'])
@jwt_required()
def minha_aderencia_historico():
    """Últimos fechamentos (semanas/meses já encerrados) do usuário logado —
    base pra tendência de aderência (Fase 3). Fecha qualquer período pendente
    antes de listar, pra não depender de já ter passado por listar()."""
    me = get_current_user()
    fechar_periodos_pendentes(me)

    limite = request.args.get('limite', 8, type=int)
    periodicidade = request.args.get('periodicidade', 'semanal')
    fechamentos = FechamentoPeriodo.query.filter_by(
        usuario_id=me.id, periodicidade=periodicidade
    ).order_by(FechamentoPeriodo.periodo_inicio.desc()).limit(limite).all()
    return jsonify([f.to_dict() for f in reversed(fechamentos)])


@rotinas_bp.route('/minha-aderencia/limites', methods=['GET'])
@jwt_required()
def minha_aderencia_limites():
    """Data de início da rotina mais antiga e a data de fim da mais recente do
    usuário logado — usado pelo front pra limitar a navegação por setas (Fase 1)
    ao intervalo onde realmente existe atividade, em vez de deixar navegar pra
    períodos vazios indefinidamente pra frente ou pra trás."""
    me = get_current_user()
    from sqlalchemy import func
    primeira = db.session.query(func.min(Rotina.periodo_inicio)).filter(Rotina.usuario_id == me.id).scalar()
    ultima = db.session.query(func.max(Rotina.periodo_fim)).filter(Rotina.usuario_id == me.id).scalar()
    return jsonify({
        'primeira_data': primeira.isoformat() if primeira else None,
        'ultima_data': ultima.isoformat() if ultima else None,
    })


def _stats_periodo_exato(usuario_id, periodicidade, inicio, fim):
    """Estatísticas de execução de uma categoria com limites exatos (usado pelas
    semanas/quinzena/mês da aderência mensal) — as rotinas dessa categoria são
    as que têm periodo_inicio/periodo_fim batendo exatamente com os limites
    calculados (mesmos limites usados na geração, ver get_periodo)."""
    rotinas = Rotina.query.filter_by(
        usuario_id=usuario_id, periodicidade=periodicidade,
        periodo_inicio=inicio, periodo_fim=fim,
    ).all()
    return {**_stats_execucao(rotinas), 'periodo_inicio': inicio.isoformat(), 'periodo_fim': fim.isoformat()}


@rotinas_bp.route('/minha-aderencia/mensal', methods=['GET'])
@jwt_required()
def minha_aderencia_mensal():
    """Aderência do mês inteiro do usuário logado, dividida em 6 categorias —
    Semana 1 a 4 (calendário fixo, ver get_periodo), Quinzenal (soma das duas
    quinzenas do mês) e Mensal — mais um bucket extra de Atividades Diárias só
    pra quem tem o perfil Coordenador (cd), fora da soma principal (ver decisão
    no plano). O percentual do topo é a soma de concluídas / soma de totais das
    6 categorias (sem contar diárias)."""
    from sqlalchemy import or_, and_

    me = get_current_user()
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()

    # Gera o mês inteiro (não só o período corrente) antes de calcular as
    # categorias — sem isso, um período que ainda não chegou mostraria "0 de 0"
    # em vez do total real, e clicar num card futuro não acharia nada pra listar.
    ensure_rotinas_mes(me, referencia)

    primeiro_dia_mes = referencia.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)

    semanas = [
        {'numero': numero, **_stats_periodo_exato(me.id, 'semanal', inicio, fim)}
        for numero, inicio, fim in _semanas_do_mes(referencia)
    ]

    inicio_q1, fim_q1 = get_periodo('quinzenal', primeiro_dia_mes)
    inicio_q2, fim_q2 = get_periodo('quinzenal', primeiro_dia_mes.replace(day=16))
    rotinas_quinzenal = Rotina.query.filter(
        Rotina.usuario_id == me.id, Rotina.periodicidade == 'quinzenal',
        or_(
            and_(Rotina.periodo_inicio == inicio_q1, Rotina.periodo_fim == fim_q1),
            and_(Rotina.periodo_inicio == inicio_q2, Rotina.periodo_fim == fim_q2),
        ),
    ).all()
    quinzenal = {
        **_stats_execucao(rotinas_quinzenal),
        'periodo_inicio': primeiro_dia_mes.isoformat(), 'periodo_fim': ultimo_dia_mes.isoformat(),
    }

    inicio_m, fim_m = get_periodo('mensal', referencia)
    mensal = _stats_periodo_exato(me.id, 'mensal', inicio_m, fim_m)

    total_geral = sum(c['total'] for c in semanas) + quinzenal['total'] + mensal['total']
    concluidas_geral = sum(c['concluidas'] for c in semanas) + quinzenal['concluidas'] + mensal['concluidas']
    percentual_geral = round((concluidas_geral / total_geral * 100), 1) if total_geral else 0

    diarias = None
    if 'cd' in me.perfis_list:
        qtd_ativ_diarias = AtividadeCatalogo.query.filter_by(
            perfil='cd', periodicidade='diaria', ativo=True
        ).count()
        if qtd_ativ_diarias > 0:
            dias_no_mes = (ultimo_dia_mes - primeiro_dia_mes).days + 1
            total_diarias = dias_no_mes * qtd_ativ_diarias
            concluidas_diarias = Rotina.query.join(
                AtividadeCatalogo, Rotina.atividade_id == AtividadeCatalogo.id
            ).filter(
                Rotina.usuario_id == me.id,
                AtividadeCatalogo.perfil == 'cd',
                Rotina.periodicidade == 'diaria',
                Rotina.periodo_inicio >= primeiro_dia_mes,
                Rotina.periodo_inicio <= ultimo_dia_mes,
                Rotina.status == 'concluida',
                Rotina.status_aprovacao != 'reprovada',
            ).count()
            diarias = {
                'total': total_diarias,
                'concluidas': concluidas_diarias,
                'percentual_execucao': round((concluidas_diarias / total_diarias * 100), 1) if total_diarias else 0,
                'periodo_inicio': primeiro_dia_mes.isoformat(),
                'periodo_fim': ultimo_dia_mes.isoformat(),
            }

    return jsonify({
        'periodo_inicio': primeiro_dia_mes.isoformat(),
        'periodo_fim': ultimo_dia_mes.isoformat(),
        'total': total_geral,
        'concluidas': concluidas_geral,
        'percentual_execucao': percentual_geral,
        'semanas': semanas,
        'quinzenal': quinzenal,
        'mensal': mensal,
        'diarias': diarias,
    })


COLUNAS_FORMULARIO_COMERCIAL = [
    'Categoria', 'Empreendimento', 'Data Execução', 'Hora Início', 'Hora Término',
    'Objetivo', 'Resumo da Execução', 'Principais Temas',
    'Leads - Resultado', 'Leads - Meta', 'Leads - Status',
    'Conversão - Resultado', 'Conversão - Meta', 'Conversão - Status',
    'Visitas - Resultado', 'Visitas - Meta', 'Visitas - Status',
    'Reservas - Resultado', 'Reservas - Meta', 'Reservas - Status',
    'Vendas - Resultado', 'Vendas - Meta', 'Vendas - Status',
    'Observação Evidências', 'Dificuldades', 'Motivo Desvio 1', 'Motivo Desvio 2',
    'Descrição da Causa', 'Necessita Apoio', 'Área de Apoio', 'Motivo Apoio',
    'Objetivo Atingido', 'Próximos Passos',
    'Qtde Evidências', 'Qtde Participantes', 'Qtde Ações no Plano',
]


def _is_list_of_dicts(val):
    return isinstance(val, list) and all(isinstance(item, dict) for item in val)


def _formatar_valor_customizado(val):
    """Formata um valor de campo customizado (fora do relatório padrão comercial)
    para caber numa única célula do CSV: dicts (inclusive aninhados, ex.: itens de
    checklist) viram 'k: v, k: v', listas viram '[k: v, ...]; [k: v, ...]' e o
    resto vira texto simples. Recursivo para suportar estruturas aninhadas
    (ex.: lista de empreendimentos, cada um com um dict de itens de checklist)."""
    if isinstance(val, dict):
        pares = [f"{k}: {_formatar_valor_customizado(v)}" for k, v in val.items() if v not in (None, '', [], {})]
        return ", ".join(pares)
    if isinstance(val, list):
        partes = []
        for item in val:
            if isinstance(item, dict):
                item_str = _formatar_valor_customizado(item)
                if item_str:
                    partes.append(f"[{item_str}]")
            elif isinstance(item, list):
                partes.append(_formatar_valor_customizado(item))
            else:
                partes.append(str(item))
        return "; ".join(partes)
    return val


def _achatar_formulario_comercial(r):
    """Achata o formulario_comercial (JSON, formato varia por perfil/atividade) em
    (linha_fixa, campos_customizados): linha_fixa segue COLUNAS_FORMULARIO_COMERCIAL;
    campos_customizados é um dict {chave: valor} com os campos fora do relatório
    padrão comercial (relatórios de SR/SP/CD/GV) — cada chave vira sua própria coluna
    dinâmica no export (ver _colunas_e_linhas_formulario), em vez de um resumo único.

    Os relatórios de SR/SP/CD/GV reaproveitam nomes de campo do relatório padrão
    (ex.: 'participantes', 'resultados') com formatos diferentes (texto solto em vez
    de lista de dicts, lista em vez de dict de indicadores). Por isso cada campo do
    padrão só é tratado como tal se realmente tiver o formato esperado; caso
    contrário cai nos campos customizados em vez de quebrar."""
    try:
        f = json.loads(r.formulario_comercial) if r.formulario_comercial else {}
        if not isinstance(f, dict):
            f = {}
    except Exception:
        f = {}

    resultados = f.get('resultados')
    resultados_e_dict = isinstance(resultados, dict)

    def ind(nome, campo):
        if not resultados_e_dict:
            return ''
        valor = resultados.get(nome)
        return valor.get(campo, '') if isinstance(valor, dict) else ''

    participantes_raw = f.get('participantes')
    participantes = participantes_raw if _is_list_of_dicts(participantes_raw) else []

    plano_raw = f.get('plano_acao')
    plano = plano_raw if _is_list_of_dicts(plano_raw) else []

    campos_padrao = [
        'categoria', 'empreendimento', 'data_execucao', 'hora_inicio', 'hora_termino',
        'objetivo', 'resumo_execucao', 'principais_temas',
        'observacao_evidencias', 'dificuldades', 'motivo_desvio_1', 'motivo_desvio_2',
        'descricao_causa', 'necessita_apoio', 'area_apoio', 'motivo_apoio',
        'objetivo_atingido', 'proximos_passos',
    ]
    if resultados_e_dict:
        campos_padrao.append('resultados')
    if participantes:
        campos_padrao.append('participantes')
    if plano:
        campos_padrao.append('plano_acao')

    campos_customizados = {
        k: _formatar_valor_customizado(v) for k, v in f.items() if k not in campos_padrao
    }

    linha_fixa = [
        f.get('categoria', ''),
        f.get('empreendimento', ''),
        f.get('data_execucao', ''),
        f.get('hora_inicio', ''),
        f.get('hora_termino', ''),
        f.get('objetivo', ''),
        f.get('resumo_execucao', ''),
        f.get('principais_temas', ''),
        ind('Leads', 'resultado_atual'), ind('Leads', 'meta'), ind('Leads', 'status'),
        ind('Conversão', 'resultado_atual'), ind('Conversão', 'meta'), ind('Conversão', 'status'),
        ind('Visitas', 'resultado_atual'), ind('Visitas', 'meta'), ind('Visitas', 'status'),
        ind('Reservas', 'resultado_atual'), ind('Reservas', 'meta'), ind('Reservas', 'status'),
        ind('Vendas', 'resultado_atual'), ind('Vendas', 'meta'), ind('Vendas', 'status'),
        f.get('observacao_evidencias', ''),
        f.get('dificuldades', ''),
        f.get('motivo_desvio_1', ''),
        f.get('motivo_desvio_2', ''),
        f.get('descricao_causa', ''),
        f.get('necessita_apoio', ''),
        f.get('area_apoio', ''),
        f.get('motivo_apoio', ''),
        f.get('objetivo_atingido', ''),
        f.get('proximos_passos', ''),
        len(r.evidencias),
        len([p for p in participantes if p.get('nome')]),
        len([a for a in plano if a.get('acao')]),
    ]
    return linha_fixa, campos_customizados


def _achatar_formulario_comercial_seguro(r):
    """Wrapper seguro: uma linha com formato inesperado não pode derrubar a
    exportação inteira (já aconteceu em produção). Se o achatamento falhar por
    qualquer motivo não previsto, devolve uma linha em branco com o JSON bruto
    num campo customizado 'erro' em vez de propagar a exceção."""
    try:
        return _achatar_formulario_comercial(r)
    except Exception:
        linha_fixa = [''] * len(COLUNAS_FORMULARIO_COMERCIAL)
        erro = {'erro': f"[erro ao processar relatório] {r.formulario_comercial or ''}"[:500]}
        return linha_fixa, erro


def _colunas_e_linhas_formulario(rotinas):
    """Monta as colunas do formulário comercial para um export: COLUNAS_FORMULARIO_COMERCIAL
    (fixas) seguidas de uma coluna por campo customizado que aparecer nas rotinas exportadas
    (dinâmico — calculado a partir dos dados desta chamada, não de um schema fixo). Retorna
    (colunas, linhas) prontos para concatenar após as colunas base de cada export."""
    linhas_fixas = []
    campos_por_linha = []
    chaves_customizadas = set()
    for r in rotinas:
        linha_fixa, campos = _achatar_formulario_comercial_seguro(r)
        linhas_fixas.append(linha_fixa)
        campos_por_linha.append(campos)
        chaves_customizadas.update(campos.keys())

    chaves_ordenadas = sorted(chaves_customizadas)
    colunas = [*COLUNAS_FORMULARIO_COMERCIAL, *chaves_ordenadas]
    linhas = [
        [*linha_fixa, *[campos.get(k, '') for k in chaves_ordenadas]]
        for linha_fixa, campos in zip(linhas_fixas, campos_por_linha)
    ]
    return colunas, linhas


def _export_csv(nome_arquivo, cabecalho, linhas):
    # Excel em locale pt-BR usa ';' como separador de lista ao abrir .csv por
    # duplo-clique e ignora ',' como delimitador — sem isso, a planilha inteira
    # cai numa única coluna e campos multi-linha (textareas) quebram em linhas
    # soltas. A diretiva 'sep=;' força o Excel a usar o delimitador correto
    # independente do locale.
    buffer = io.StringIO()
    buffer.write('sep=;\r\n')
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(cabecalho)
    writer.writerows(linhas)
    mem = io.BytesIO(buffer.getvalue().encode('utf-8-sig'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=nome_arquivo)


def _export_pdf(nome_arquivo, titulo, subtitulo, cabecalho, linhas):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), title=titulo,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(titulo, estilos['Title'])]
    if subtitulo:
        elementos.append(Paragraph(subtitulo, estilos['Normal']))
    elementos.append(Spacer(1, 0.6 * cm))

    dados = [cabecalho] + [[('' if c is None else str(c)) for c in linha] for linha in linhas]
    tabela = Table(dados, repeatRows=1)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7a1f2b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7f7')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela)
    doc.build(elementos)

    mem = io.BytesIO(buffer.getvalue())
    mem.seek(0)
    return send_file(mem, mimetype='application/pdf', as_attachment=True, download_name=nome_arquivo)


@rotinas_bp.route('/export', methods=['GET'])
@jwt_required()
def exportar_rotinas():
    me = get_current_user()

    usuario_id = request.args.get('usuario_id', type=int)
    regional_id = request.args.get('regional_id', type=int)
    atividade_id = request.args.get('atividade_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status = request.args.get('status')
    periodo = request.args.get('periodo', 'semanal')
    data_ref = request.args.get('data_ref')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    historico = request.args.get('historico', '').lower() in ('1', 'true')
    modo = request.args.get('modo')  # 'atual' | 'historico' | 'intervalo' — opcional, ver condicao_periodo_rotinas
    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()

    cond = condicao_periodo_rotinas(periodo, referencia, data_inicio, data_fim, historico, modo)
    query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id)
    if cond is not None:
        query = query.filter(cond)
    if atividade_id:
        query = query.filter(Rotina.atividade_id == atividade_id)

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
    colunas_form, linhas_form = _colunas_e_linhas_formulario(rotinas)
    linhas = [[
        r.usuario.nome if r.usuario else '',
        r.atividade.nome if r.atividade else '',
        r.periodicidade,
        r.status,
        r.periodo_inicio.isoformat() if r.periodo_inicio else '',
        r.periodo_fim.isoformat() if r.periodo_fim else '',
        r.data_conclusao.isoformat() if r.data_conclusao else '',
        r.comentario or '',
        r.justificativa or '',
        r.acao_corretiva or '',
        len(r.evidencias),
        *linhas_form[i],
    ] for i, r in enumerate(rotinas)]
    return _export_csv(
        f'rotinas_{periodo}.csv',
        ['Usuario', 'Atividade', 'Periodicidade', 'Status', 'Periodo Inicio', 'Periodo Fim', 'Conclusao', 'Comentario', 'Justificativa', 'Plano Acao', 'Qtde Evidencias', *colunas_form],
        linhas
    )


def _aplicar_filtros_dashboard(query, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro):
    """Filtros de visibilidade/segmentação comuns ao dashboard admin/superintendente
    — reaproveitado pela query principal, pelo período anterior em carência e pela
    segregação por semana/quinzena/mês, pra manter os mesmos filtros aplicados de
    forma consistente em todo o dashboard. `perfil_filtro` filtra pelo perfil-alvo
    da ATIVIDADE (mesma semântica já usada em "Execução por Perfil"), não pelo
    perfil do colaborador — assim continua combinável com `usuario_id` (que filtra
    o colaborador em si) sem os dois filtros se confundirem."""
    if me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
    elif regional_id:
        query = query.filter(Usuario.regional_id == regional_id)
    if usuario_id and me.perfil in ['admin', 'sr']:
        query = query.filter(Rotina.usuario_id == usuario_id)
    if perfil_filtro:
        query = query.join(AtividadeCatalogo, Rotina.atividade_id == AtividadeCatalogo.id).filter(
            AtividadeCatalogo.perfil == perfil_filtro
        )
    if atividade_id_filtro:
        query = query.filter(Rotina.atividade_id == atividade_id_filtro)
    return query


def _semanas_time(referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro):
    """Execução por semana de calendário (Semana 1 a 4) somada entre todos os
    colaboradores que passam pelos filtros do dashboard — mesma ideia de
    `minha_aderencia_mensal`, mas agregada pro time em vez de um usuário só."""
    semanas = []
    for numero, inicio, fim in _semanas_do_mes(referencia):
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'semanal',
            Rotina.periodo_inicio == inicio, Rotina.periodo_fim == fim,
        )
        query = _aplicar_filtros_dashboard(query, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)
        semanas.append({
            'numero': numero, **_stats_execucao(query.all()),
            'periodo_inicio': inicio.isoformat(), 'periodo_fim': fim.isoformat(),
        })
    return semanas


def _periodo_time(periodicidade, referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro):
    """Execução de um período exato (quinzenal combinado ou mensal) somada entre
    todos os colaboradores filtrados — mesmo espírito de _semanas_time."""
    from sqlalchemy import or_, and_

    if periodicidade == 'quinzenal':
        primeiro_dia_mes = referencia.replace(day=1)
        ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)
        inicio_q1, fim_q1 = get_periodo('quinzenal', primeiro_dia_mes)
        inicio_q2, fim_q2 = get_periodo('quinzenal', primeiro_dia_mes.replace(day=16))
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'quinzenal',
            or_(
                and_(Rotina.periodo_inicio == inicio_q1, Rotina.periodo_fim == fim_q1),
                and_(Rotina.periodo_inicio == inicio_q2, Rotina.periodo_fim == fim_q2),
            ),
        )
        periodo_inicio, periodo_fim = primeiro_dia_mes, ultimo_dia_mes
    else:
        periodo_inicio, periodo_fim = get_periodo('mensal', referencia)
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'mensal',
            Rotina.periodo_inicio == periodo_inicio, Rotina.periodo_fim == periodo_fim,
        )

    query = _aplicar_filtros_dashboard(query, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)
    return {
        **_stats_execucao(query.all()),
        'periodo_inicio': periodo_inicio.isoformat(), 'periodo_fim': periodo_fim.isoformat(),
    }


def _query_selecao_dashboard(selecao, referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro):
    """Resolve a seleção atual do dashboard num (rotinas, periodo_inicio,
    periodo_fim): uma semana específica ('semana1'..'semana4'), a quinzena
    combinada ('quinzenal'), o mês ('mensal') — ou, sem seleção (''), o mês
    inteiro somado (semanas + quinzenal + mensal), que é o novo padrão dos
    indicadores principais do dashboard (antes baseados só no "período atual").
    Diárias ficam de fora da soma padrão, mesmo critério já usado em
    minha_aderencia_mensal (o card de Atividades Diárias fica separado)."""
    from sqlalchemy import or_, and_

    primeiro_dia_mes = referencia.replace(day=1)
    ultimo_dia_mes = (primeiro_dia_mes + relativedelta(months=1)) - timedelta(days=1)

    if selecao and selecao.startswith('semana') and selecao[6:].isdigit():
        numero = int(selecao[6:])
        semanas = {n: (i, f) for n, i, f in _semanas_do_mes(referencia)}
        if numero not in semanas:
            numero = 1
        inicio, fim = semanas[numero]
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'semanal',
            Rotina.periodo_inicio == inicio, Rotina.periodo_fim == fim,
        )
        periodo_inicio, periodo_fim = inicio, fim
    elif selecao == 'quinzenal':
        inicio_q1, fim_q1 = get_periodo('quinzenal', primeiro_dia_mes)
        inicio_q2, fim_q2 = get_periodo('quinzenal', primeiro_dia_mes.replace(day=16))
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'quinzenal',
            or_(
                and_(Rotina.periodo_inicio == inicio_q1, Rotina.periodo_fim == fim_q1),
                and_(Rotina.periodo_inicio == inicio_q2, Rotina.periodo_fim == fim_q2),
            ),
        )
        periodo_inicio, periodo_fim = primeiro_dia_mes, ultimo_dia_mes
    elif selecao == 'mensal':
        inicio_m, fim_m = get_periodo('mensal', referencia)
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo', Rotina.periodicidade == 'mensal',
            Rotina.periodo_inicio == inicio_m, Rotina.periodo_fim == fim_m,
        )
        periodo_inicio, periodo_fim = inicio_m, fim_m
    else:
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.status == 'ativo',
            Rotina.periodicidade.in_(['semanal', 'quinzenal', 'mensal']),
            Rotina.periodo_inicio >= primeiro_dia_mes, Rotina.periodo_fim <= ultimo_dia_mes,
        )
        periodo_inicio, periodo_fim = primeiro_dia_mes, ultimo_dia_mes

    query = _aplicar_filtros_dashboard(query, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)
    return query.all(), periodo_inicio, periodo_fim


@rotinas_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    me = get_current_user()

    if me.perfil not in ['admin', 'sr']:
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id = request.args.get('regional_id', type=int)
    usuario_id = request.args.get('usuario_id', type=int)
    perfil_filtro = request.args.get('perfil')
    atividade_id_filtro = request.args.get('atividade_id', type=int)
    selecao = request.args.get('selecao', '')
    data_ref = request.args.get('data_ref')

    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()

    rotinas, inicio, fim = _query_selecao_dashboard(
        selecao, referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro
    )
    total = len(rotinas)
    concluidas = sum(1 for r in rotinas if r.status == 'concluida' and r.status_aprovacao != 'reprovada')
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
        if r.status == 'concluida' and r.status_aprovacao != 'reprovada':
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
        if r.status == 'concluida' and r.status_aprovacao != 'reprovada':
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

    # Segregação por semana/quinzena/mês do mês corrente — sempre o mês
    # inteiro, independente da seleção atual (é o que alimenta os cards
    # clicáveis que definem `selecao`). Mesmos filtros de visibilidade/
    # segmentação, somados entre todos os colaboradores filtrados. Mesmo
    # formato usado em minha_aderencia_mensal, só que agregado pro time.
    semanas_time = _semanas_time(referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)
    quinzenal_time = _periodo_time('quinzenal', referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)
    mensal_time = _periodo_time('mensal', referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro)

    return jsonify({
        'selecao': selecao,
        'periodo_inicio': inicio.isoformat(),
        'periodo_fim': fim.isoformat(),
        'total': total,
        'concluidas': concluidas,
        'nao_realizadas': nao_realizadas,
        'em_andamento': em_andamento,
        'nao_iniciadas': nao_iniciadas,
        'percentual_execucao': percentual,
        'por_perfil': por_perfil,
        'ranking': ranking,
        'semanas': semanas_time,
        'quinzenal': quinzenal_time,
        'mensal': mensal_time,
    })


@rotinas_bp.route('/dashboard/export', methods=['GET'])
@jwt_required()
def exportar_dashboard():
    me = get_current_user()
    if me.perfil not in ['admin', 'sr']:
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id = request.args.get('regional_id', type=int)
    usuario_id = request.args.get('usuario_id', type=int)
    perfil_filtro = request.args.get('perfil')
    atividade_id_filtro = request.args.get('atividade_id', type=int)
    selecao = request.args.get('selecao', '')
    data_ref = request.args.get('data_ref')
    referencia = date.fromisoformat(data_ref) if data_ref else hoje_br()

    rotinas, _inicio, _fim = _query_selecao_dashboard(
        selecao, referencia, me, regional_id, usuario_id, perfil_filtro, atividade_id_filtro
    )
    linhas = [[
        r.usuario.nome if r.usuario else '',
        r.usuario.regional.nome if r.usuario and r.usuario.regional else '',
        r.atividade.nome if r.atividade else '',
        r.periodicidade,
        r.status,
        r.data_conclusao.isoformat() if r.data_conclusao else ''
    ] for r in rotinas]
    return _export_csv(
        f'dashboard_{selecao or "mes"}.csv',
        ['Usuario', 'Regional', 'Atividade', 'Periodicidade', 'Status', 'Conclusao'],
        linhas
    )


def _montar_relatorio_liderados(me):
    """Monta o comparativo de rotinas dos liderados (Seção 3) a partir dos
    query params da requisição atual — usado tanto pelo endpoint JSON (tela)
    quanto pelos exports (CSV/PDF), pra manter os mesmos filtros nos dois.
    'Liderados' = colaboradores ativos (gv/cd/sp) da regional do Superintendente
    (mesmo critério de visibilidade já usado no dashboard e na listagem de
    rotinas pra perfil 'sr'); admin pode escolher a regional."""
    from sqlalchemy import and_

    regional_id = request.args.get('regional_id', type=int) if me.perfil == 'admin' else me.regional_id
    if not regional_id:
        return None, 'Informe a regional (regional_id).'

    usuario_id = request.args.get('usuario_id', type=int)
    periodicidade = request.args.get('periodicidade')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    if not data_inicio or not data_fim:
        inicio_mes, fim_mes = get_periodo('mensal', hoje_br())
        data_inicio = data_inicio or inicio_mes.isoformat()
        data_fim = data_fim or fim_mes.isoformat()

    liderados_query = Usuario.query.filter(
        Usuario.status == 'ativo',
        Usuario.regional_id == regional_id,
        Usuario.perfil.notin_(['admin', 'sr']),
    )
    if usuario_id:
        liderados_query = liderados_query.filter(Usuario.id == usuario_id)
    liderados = liderados_query.order_by(Usuario.nome).all()

    cond = condicao_periodo_rotinas('todas', hoje_br(), data_inicio, data_fim, modo='intervalo')
    if periodicidade and periodicidade != 'todas':
        filtro_periodicidade = Rotina.periodicidade == periodicidade
        cond = and_(cond, filtro_periodicidade) if cond is not None else filtro_periodicidade

    linhas = []
    totais = {'total': 0, 'concluidas': 0, 'pendentes': 0, 'atrasadas': 0}
    for u in liderados:
        query = Rotina.query.filter(Rotina.usuario_id == u.id)
        if cond is not None:
            query = query.filter(cond)
        stats = _stats_liderado(query.all())
        linhas.append({'usuario_id': u.id, 'nome': u.nome, 'perfil': u.perfil, **stats})
        for chave in totais:
            totais[chave] += stats[chave]
    totais['percentual_execucao'] = round((totais['concluidas'] / totais['total'] * 100), 1) if totais['total'] else 0

    linhas.sort(key=lambda x: x['percentual_execucao'], reverse=True)
    resultado = {
        'periodo_inicio': data_inicio, 'periodo_fim': data_fim,
        'regional_id': regional_id, 'regional_nome': liderados[0].regional.nome if liderados and liderados[0].regional else None,
        'liderados': linhas, 'totais': totais,
    }
    return resultado, None


@rotinas_bp.route('/relatorio-liderados', methods=['GET'])
@jwt_required()
def relatorio_liderados():
    """Relatório Comparativo das Rotinas dos Liderados (Seção 3): permite ao
    Superintendente comparar, por colaborador, o percentual de execução e a
    quantidade de atividades concluídas/pendentes/atrasadas num período — com
    filtro por período e por colaborador."""
    me = get_current_user()
    if me.perfil not in ('admin', 'sr'):
        return jsonify({'erro': 'Acesso negado'}), 403

    resultado, erro = _montar_relatorio_liderados(me)
    if erro:
        return jsonify({'erro': erro}), 400
    return jsonify(resultado)


@rotinas_bp.route('/relatorio-liderados/export', methods=['GET'])
@jwt_required()
def exportar_relatorio_liderados():
    me = get_current_user()
    if me.perfil not in ('admin', 'sr'):
        return jsonify({'erro': 'Acesso negado'}), 403

    resultado, erro = _montar_relatorio_liderados(me)
    if erro:
        return jsonify({'erro': erro}), 400

    formato = request.args.get('formato', 'csv').lower()
    cabecalho = ['Colaborador', 'Perfil', 'Total', 'Concluídas', 'Pendentes', 'Atrasadas', '% Execução']
    linhas = [[
        l['nome'], l['perfil'], l['total'], l['concluidas'], l['pendentes'], l['atrasadas'],
        f"{l['percentual_execucao']}%",
    ] for l in resultado['liderados']]
    linhas.append([
        'TOTAL', '', resultado['totais']['total'], resultado['totais']['concluidas'],
        resultado['totais']['pendentes'], resultado['totais']['atrasadas'], f"{resultado['totais']['percentual_execucao']}%",
    ])

    nome_base = f"comparativo_liderados_{resultado['periodo_inicio']}_a_{resultado['periodo_fim']}"
    if formato == 'pdf':
        return _export_pdf(
            f'{nome_base}.pdf',
            'Relatório Comparativo das Rotinas dos Liderados',
            f"Regional: {resultado['regional_nome'] or '—'} · Período: {resultado['periodo_inicio']} a {resultado['periodo_fim']}",
            cabecalho, linhas,
        )
    return _export_csv(f'{nome_base}.csv', cabecalho, linhas)


@rotinas_bp.route('/pendencias', methods=['GET'])
@jwt_required()
def pendencias():
    me = get_current_user()

    query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).join(AtividadeCatalogo).filter(
        Rotina.status.in_(['nao_iniciada', 'em_andamento', 'nao_realizada']),
        AtividadeCatalogo.obrigatoria == True
    )

    if me.perfil == 'sr':
        query = query.filter(Usuario.regional_id == me.regional_id)
    elif me.perfil not in ['admin']:
        query = query.filter(Rotina.usuario_id == me.id)

    todas = query.all()
    # Atividades vencidas ainda não tratadas passam automaticamente a "Não Realizada"
    # (histórico atribuído ao próprio dono da rotina).
    marcar_vencidas_nao_realizadas(todas)

    # Pendência = obrigatória não realizada (ou ainda vencida por segurança). As
    # justificadas permanecem na lista, apenas marcadas como tal.
    rotinas = [r for r in todas if r.status == 'nao_realizada' or rotina_vencida(r)]
    # Não justificadas primeiro; depois por prazo.
    rotinas.sort(key=lambda r: (rotina_justificada(r), r.prazo_limite or r.periodo_fim))

    resultado = []
    for r in rotinas:
        d = r.to_dict()
        d['justificada'] = rotina_justificada(r)
        resultado.append(d)
    return jsonify(resultado)


@rotinas_bp.route('/<int:rid>/aprovar', methods=['POST'])
@jwt_required()
def aprovar_atividade(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)
    
    # Verificar se o usuário tem permissão para aprovar
    # Superintendente aprova atividades da sua regional
    # Supervisor aprova atividades do seu superintendente
    # Admin aprova qualquer atividade
    
    if me.perfil == 'admin':
        # Admin pode aprovar qualquer coisa
        pass
    elif me.perfil == 'sr':
        if rotina.usuario_id == me.id:
            return jsonify({'erro': 'Você não pode aprovar suas próprias atividades'}), 403
        if rotina.usuario.regional_id != me.regional_id:
            return jsonify({'erro': 'Você só pode aprovar atividades de sua regional'}), 403
    else:
        return jsonify({'erro': 'Apenas Administrador e Superintendente podem aprovar atividades'}), 403
    
    # Verificar se a atividade está pendente de aprovação
    if rotina.status_aprovacao != 'pendente':
        return jsonify({'erro': f'Atividade já foi {rotina.status_aprovacao}'}), 400
    
    data = request.get_json() or {}

    # Atualizar status de aprovação
    rotina.status_aprovacao = 'aprovada'
    rotina.aprovador_id = me.id
    rotina.data_aprovacao = get_now_br()

    # Registrar no histórico de aprovações
    from backend.models import AprovacaoRotina
    aprovacao = AprovacaoRotina(
        rotina_id=rotina.id,
        aprovador_id=me.id,
        acao='aprovada',
        motivo=data.get('motivo'),
        duracao_revisao_segundos=data.get('duracao_revisao_segundos')
    )
    db.session.add(aprovacao)
    
    # Adicionar no histórico de rotinas
    add_rotina_history(
        rotina,
        me.id,
        'aprovacao_atividade',
        observacao=f'Atividade aprovada por {me.nome}',
        status_anterior=rotina.status,
        status_novo=rotina.status
    )
    
    log_audit(me.id, 'rotina_aprovacao', rotina.id, 'aprovar', {
        'rotina_id': rotina.id,
        'usuario_id': rotina.usuario_id,
        'status_aprovacao': 'aprovada'
    })
    
    db.session.commit()
    return jsonify(rotina.to_dict())


@rotinas_bp.route('/<int:rid>/reprovar', methods=['POST'])
@jwt_required()
def reprovar_atividade(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)
    
    # Verificar se o usuário tem permissão para reprovar
    if me.perfil == 'admin':
        pass
    elif me.perfil == 'sr':
        if rotina.usuario_id == me.id:
            return jsonify({'erro': 'Você não pode reprovar suas próprias atividades'}), 403
        if rotina.usuario.regional_id != me.regional_id:
            return jsonify({'erro': 'Você só pode reprovar atividades de sua regional'}), 403
    else:
        return jsonify({'erro': 'Apenas Administrador e Superintendente podem reprovar atividades'}), 403
    
    # Verificar se a atividade está pendente de aprovação
    if rotina.status_aprovacao != 'pendente':
        return jsonify({'erro': f'Atividade já foi {rotina.status_aprovacao}'}), 400
    
    data = request.get_json()
    motivo = data.get('motivo')
    
    if not motivo:
        return jsonify({'erro': 'Motivo da reprovação é obrigatório'}), 400
    
    # Atualizar status de aprovação
    rotina.status_aprovacao = 'reprovada'
    rotina.aprovador_id = me.id
    rotina.data_aprovacao = get_now_br()
    rotina.motivo_reprovacao = motivo

    # Conceder prazo extra ao colaborador para reenviar (data da reprovação + GRACE_DAYS_REENVIO)
    rotina.prazo_reenvio = hoje_br() + timedelta(days=GRACE_DAYS_REENVIO)
    rotina.status = 'em_andamento'  # Reabrir para correção

    from backend.models import AprovacaoRotina
    aprovacao = AprovacaoRotina(
        rotina_id=rotina.id,
        aprovador_id=me.id,
        acao='reprovada',
        motivo=motivo,
        duracao_revisao_segundos=data.get('duracao_revisao_segundos')
    )
    db.session.add(aprovacao)
    
    # Adicionar no histórico de rotinas
    add_rotina_history(
        rotina,
        me.id,
        'reprovacao_atividade',
        observacao=f'Atividade reprovada por {me.nome}: {motivo}',
        status_anterior=rotina.status,
        status_novo=rotina.status
    )
    
    log_audit(me.id, 'rotina_aprovacao', rotina.id, 'reprovar', {
        'rotina_id': rotina.id,
        'usuario_id': rotina.usuario_id,
        'status_aprovacao': 'reprovada',
        'motivo': motivo
    })
    
    db.session.commit()
    return jsonify(rotina.to_dict())


@rotinas_bp.route('/<int:rid>/aprovacoes', methods=['GET'])
@jwt_required()
def listar_aprovacoes(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)
    
    if not can_access_rotina(me, rotina):
        return jsonify({'erro': 'Acesso negado'}), 403
    
    from backend.models import AprovacaoRotina
    aprovacoes = AprovacaoRotina.query.filter_by(rotina_id=rid).order_by(AprovacaoRotina.criado_em.desc()).all()
    return jsonify([a.to_dict() for a in aprovacoes])


@rotinas_bp.route('/<int:rid>/reenviar', methods=['POST'])
@jwt_required()
def reenviar_para_aprovacao(rid):
    me = get_current_user()
    rotina = Rotina.query.get_or_404(rid)

    if rotina.usuario_id != me.id and me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    if rotina.status_aprovacao != 'reprovada':
        return jsonify({'erro': 'Apenas atividades reprovadas podem ser reenviadas'}), 400

    # Verificar se o prazo de reenvio não expirou
    if rotina.prazo_reenvio and rotina.prazo_reenvio < hoje_br():
        return jsonify({'erro': 'O prazo para reenvio desta atividade já expirou'}), 400

    # Validar requisitos de conclusão
    if not rotina.formulario_preenchido:
        return jsonify({'erro': 'Preencha o Relatório Comercial antes de reenviar a atividade'}), 400
    if not rotina.evidencias:
        return jsonify({'erro': 'Anexe pelo menos uma evidência antes de reenviar a atividade'}), 400

    status_anterior = rotina.status
    rotina.status = 'concluida'
    if not rotina.data_conclusao:
        rotina.data_conclusao = get_now_br()

    rotina.status_aprovacao = 'pendente'
    rotina.aprovador_id = None
    rotina.data_aprovacao = None
    rotina.motivo_reprovacao = None
    rotina.prazo_reenvio = None  # limpar prazo após reenvio bem-sucedido

    add_rotina_history(
        rotina,
        me.id,
        'reenvio_para_aprovacao',
        observacao='Atividade reenviada para aprovação pelo colaborador',
        status_anterior=status_anterior,
        status_novo=rotina.status
    )

    log_audit(me.id, 'rotina_aprovacao', rotina.id, 'reenviar', {
        'rotina_id': rotina.id,
        'usuario_id': rotina.usuario_id,
    })

    db.session.commit()
    return jsonify(rotina.to_dict())


@rotinas_bp.route('/<int:rid>/formulario', methods=['GET'])
@jwt_required()
def obter_formulario(rid):
    me = get_current_user()
    r = Rotina.query.get_or_404(rid)
    if not can_access_rotina(me, r):
        return jsonify({'erro': 'Acesso negado'}), 403
    dados = {}
    if r.formulario_comercial:
        try:
            dados = json.loads(r.formulario_comercial)
        except Exception:
            dados = {}
    return jsonify({'formulario': dados, 'formulario_preenchido': r.formulario_preenchido or False})


@rotinas_bp.route('/<int:rid>/formulario', methods=['PUT'])
@jwt_required()
def salvar_formulario(rid):
    me = get_current_user()
    r = Rotina.query.get_or_404(rid)
    if not can_edit_rotina(me, r):
        return jsonify({'erro': 'Acesso negado'}), 403
    if rotina_ainda_nao_liberada(r):
        return jsonify({'erro': f'Atividade ainda não liberada. Disponível a partir de {r.periodo_inicio.strftime("%d/%m/%Y")}.'}), 400
    # Em pendência (obrigatória vencida ou já "Não Realizada") o relatório não pode
    # ser preenchido — a atividade só recebe justificativa e plano de ação.
    if rotina_vencida(r) or r.status == 'nao_realizada':
        return jsonify({'erro': 'Atividade não realizada (pendência). Não é possível preencher o relatório.'}), 400

    data = request.get_json() or {}
    formulario = data.get('formulario', {})
    r.formulario_comercial = json.dumps(formulario, ensure_ascii=False)
    r.formulario_preenchido = True

    # Notifica quem foi selecionado como "Responsável" em qualquer campo/linha
    # do relatório (Seção 4) — não confundir com o responsavel_id oficial da
    # rotina (RotinaModal), notificado separadamente em atualizar().
    notificar_delegacoes_formulario(r, formulario, me)

    add_rotina_history(r, me.id, 'atualizacao_rotina',
                       observacao='Relatório Comercial preenchido',
                       status_anterior=r.status, status_novo=r.status)
    log_audit(me.id, 'rotina', r.id, 'formulario', {'rotina_id': r.id})
    db.session.commit()
    return jsonify({'mensagem': 'Relatório salvo com sucesso', 'formulario_preenchido': True})


@rotinas_bp.route('/relatorios-preenchimento', methods=['GET'])
@jwt_required()
def relatorios_preenchimento():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id  = request.args.get('regional_id', type=int)
    usuario_id   = request.args.get('usuario_id', type=int)
    perfil_filtro = request.args.get('perfil')
    atividade_id = request.args.get('atividade_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status       = request.args.get('status')
    data_inicio  = request.args.get('data_inicio')
    data_fim     = request.args.get('data_fim')
    busca        = request.args.get('busca', '').strip()

    query = (
        Rotina.query
        .join(Usuario, Rotina.usuario_id == Usuario.id)
        .join(AtividadeCatalogo, Rotina.atividade_id == AtividadeCatalogo.id)
        .filter(Rotina.formulario_preenchido == True)
    )

    if regional_id:
        query = query.filter(Usuario.regional_id == regional_id)
    if usuario_id:
        query = query.filter(Rotina.usuario_id == usuario_id)
    if perfil_filtro:
        query = query.filter(AtividadeCatalogo.perfil == perfil_filtro)
    if atividade_id:
        query = query.filter(Rotina.atividade_id == atividade_id)
    if periodicidade:
        query = query.filter(Rotina.periodicidade == periodicidade)
    if status:
        query = query.filter(Rotina.status == status)
    if data_inicio:
        query = query.filter(Rotina.periodo_inicio >= date.fromisoformat(data_inicio))
    if data_fim:
        query = query.filter(Rotina.periodo_fim <= date.fromisoformat(data_fim))
    if busca:
        from sqlalchemy import or_
        query = query.filter(or_(
            Usuario.nome.ilike(f'%{busca}%'),
            AtividadeCatalogo.nome.ilike(f'%{busca}%'),
        ))

    rotinas = query.order_by(Rotina.atualizado_em.desc()).all()
    result = []
    for r in rotinas:
        d = r.to_dict()
        try:
            d['formulario_data'] = json.loads(r.formulario_comercial) if r.formulario_comercial else {}
        except Exception:
            d['formulario_data'] = {}
        result.append(d)
    return jsonify(result)


@rotinas_bp.route('/relatorios-preenchimento/export', methods=['GET'])
@jwt_required()
def exportar_relatorios_preenchimento():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    regional_id  = request.args.get('regional_id', type=int)
    usuario_id   = request.args.get('usuario_id', type=int)
    perfil_filtro = request.args.get('perfil')
    atividade_id = request.args.get('atividade_id', type=int)
    periodicidade = request.args.get('periodicidade')
    status       = request.args.get('status')
    data_inicio  = request.args.get('data_inicio')
    data_fim     = request.args.get('data_fim')
    busca        = request.args.get('busca', '').strip()

    query = (
        Rotina.query
        .join(Usuario, Rotina.usuario_id == Usuario.id)
        .join(AtividadeCatalogo, Rotina.atividade_id == AtividadeCatalogo.id)
        .filter(Rotina.formulario_preenchido == True)
    )
    if regional_id:
        query = query.filter(Usuario.regional_id == regional_id)
    if usuario_id:
        query = query.filter(Rotina.usuario_id == usuario_id)
    if perfil_filtro:
        query = query.filter(AtividadeCatalogo.perfil == perfil_filtro)
    if atividade_id:
        query = query.filter(Rotina.atividade_id == atividade_id)
    if periodicidade:
        query = query.filter(Rotina.periodicidade == periodicidade)
    if status:
        query = query.filter(Rotina.status == status)
    if data_inicio:
        query = query.filter(Rotina.periodo_inicio >= date.fromisoformat(data_inicio))
    if data_fim:
        query = query.filter(Rotina.periodo_fim <= date.fromisoformat(data_fim))
    if busca:
        from sqlalchemy import or_
        query = query.filter(or_(
            Usuario.nome.ilike(f'%{busca}%'),
            AtividadeCatalogo.nome.ilike(f'%{busca}%'),
        ))

    rotinas = query.order_by(Rotina.atualizado_em.desc()).all()
    colunas_form, linhas_form = _colunas_e_linhas_formulario(rotinas)

    cabecalho = [
        'Colaborador', 'Regional', 'Cargo', 'Atividade', 'Periodicidade',
        'Período Início', 'Período Fim', 'Status', 'Status Aprovação',
        *colunas_form,
    ]

    linhas = [[
        r.usuario.nome if r.usuario else '',
        r.usuario.regional.nome if r.usuario and r.usuario.regional else '',
        r.atividade.perfil if r.atividade else '',
        r.atividade.nome if r.atividade else '',
        r.periodicidade or '',
        r.periodo_inicio.isoformat() if r.periodo_inicio else '',
        r.periodo_fim.isoformat() if r.periodo_fim else '',
        r.status or '',
        r.status_aprovacao or '',
        *linhas_form[i],
    ] for i, r in enumerate(rotinas)]

    return _export_csv('relatorios_preenchimento.csv', cabecalho, linhas)


@rotinas_bp.route('/metricas-aprovacao', methods=['GET'])
@jwt_required()
def metricas_aprovacao():
    me = get_current_user()
    if me.perfil != 'admin':
        return jsonify({'erro': 'Acesso negado'}), 403

    from backend.models import AprovacaoRotina
    limite = min(request.args.get('limit', 200, type=int), 500)
    aprovador_id = request.args.get('aprovador_id', type=int)

    query = AprovacaoRotina.query.order_by(AprovacaoRotina.criado_em.desc())
    if aprovador_id:
        query = query.filter_by(aprovador_id=aprovador_id)

    registros = query.limit(limite).all()

    # Agrupamento por aprovador
    por_aprovador = {}
    for a in registros:
        aid = a.aprovador_id
        if aid not in por_aprovador:
            por_aprovador[aid] = {
                'aprovador_id': aid,
                'aprovador_nome': a.aprovador.nome if a.aprovador else 'N/A',
                'total': 0,
                'aprovadas': 0,
                'reprovadas': 0,
                'com_tempo': 0,
                'soma_segundos': 0,
                'min_segundos': None,
                'max_segundos': None,
            }
        info = por_aprovador[aid]
        info['total'] += 1
        if a.acao == 'aprovada':
            info['aprovadas'] += 1
        else:
            info['reprovadas'] += 1
        if a.duracao_revisao_segundos is not None:
            info['com_tempo'] += 1
            info['soma_segundos'] += a.duracao_revisao_segundos
            if info['min_segundos'] is None or a.duracao_revisao_segundos < info['min_segundos']:
                info['min_segundos'] = a.duracao_revisao_segundos
            if info['max_segundos'] is None or a.duracao_revisao_segundos > info['max_segundos']:
                info['max_segundos'] = a.duracao_revisao_segundos

    for info in por_aprovador.values():
        ct = info['com_tempo']
        info['media_segundos'] = round(info['soma_segundos'] / ct) if ct > 0 else None

    return jsonify({
        'registros': [a.to_dict() for a in registros],
        'por_aprovador': sorted(por_aprovador.values(), key=lambda x: x['total'], reverse=True),
    })


@rotinas_bp.route('/para-aprovar', methods=['GET'])
@jwt_required()
def atividades_para_aprovar():
    me = get_current_user()
    # status_aprovacao=todas retorna pendentes+aprovadas+reprovadas; default=pendente
    filtro_status = request.args.get('status_aprovacao', 'pendente')

    from sqlalchemy import or_, and_

    if me.perfil == 'admin':
        query = Rotina.query.filter(Rotina.status == 'concluida')
        if filtro_status != 'todas':
            query = query.filter(Rotina.status_aprovacao == filtro_status)
        rotinas = query.order_by(Rotina.data_conclusao.desc()).all()
    elif me.perfil == 'sr':
        # SR vê atividades concluídas da sua regional (exceto as próprias, que só o supervisor aprova)
        query = Rotina.query.join(Usuario, Rotina.usuario_id == Usuario.id).filter(
            Usuario.regional_id == me.regional_id,
            Rotina.status == 'concluida',
            Rotina.usuario_id != me.id
        )
        if filtro_status != 'todas':
            query = query.filter(Rotina.status_aprovacao == filtro_status)
        rotinas = query.order_by(Rotina.data_conclusao.desc()).all()
    else:
        return jsonify({'erro': 'Apenas Administrador e Superintendente podem visualizar atividades para aprovação'}), 403

    return jsonify([r.to_dict() for r in rotinas])
