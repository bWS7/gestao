import json
from backend.extensions import db
from backend.models import AuditLog


def log_audit(usuario_id, entidade, entidade_id, acao, detalhes):
    registro = AuditLog(
        usuario_id=usuario_id,
        entidade=entidade,
        entidade_id=str(entidade_id) if entidade_id is not None else None,
        acao=acao,
        detalhes=json.dumps(detalhes, ensure_ascii=False, default=str)
    )
    db.session.add(registro)


def diff_payload(before, after):
    mudancas = {}
    for chave, valor_anterior in before.items():
        valor_novo = after.get(chave)
        if valor_anterior != valor_novo:
            mudancas[chave] = {'antes': valor_anterior, 'depois': valor_novo}
    return mudancas
