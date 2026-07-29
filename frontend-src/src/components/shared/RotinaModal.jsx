import { useState, useEffect, useCallback, useRef } from 'react';
import { CheckCircle, Paperclip, ExternalLink, Trash2, FileText, AlertTriangle, AlertCircle, UploadCloud } from 'lucide-react';
import { apiFetch } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';
import { Modal } from '../ui/Modal';
import { Select, Textarea } from '../ui/Input';
import Button from '../ui/Button';
import { PeriodoBadge } from '../ui/Badge';
import { PERIODO_LABELS, fmtDate, fmtDatetime } from '../../utils/constants';
import FormularioComercialModal from './FormularioComercialModal';

function EvidenciasList({ evidencias, rotinaId, canEdit, onReload }) {
  const { toast } = useToast();
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  // Upload imediato ao selecionar ou soltar arquivos (sem botão extra).
  const uploadFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setUploading(true);
    let ok = 0;
    for (const f of files) {
      const form = new FormData();
      form.append('arquivo', f);
      const r = await apiFetch(`/api/rotinas/${rotinaId}/evidencias`, { method: 'POST', body: form });
      if (r?.ok) ok += 1;
      else toast(r?.data?.erro || `Erro ao anexar ${f.name}`, 'error');
    }
    if (ok > 0) { toast(ok > 1 ? `${ok} evidências anexadas!` : 'Evidência anexada!', 'success'); onReload(); }
    setUploading(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (!canEdit || uploading) return;
    uploadFiles(e.dataTransfer.files);
  };

  const remove = async (eid) => {
    if (!confirm('Remover esta evidência?')) return;
    const r = await apiFetch(`/api/rotinas/evidencias/${eid}`, { method: 'DELETE' });
    if (r?.ok) { toast('Removida!', 'success'); onReload(); }
  };

  return (
    <div>
      {evidencias?.length > 0 ? (
        <div className="space-y-2 mb-3">
          {evidencias.map(e => (
            <div key={e.id} className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg">
              <a href={e.url} target="_blank" rel="noopener noreferrer" download={e.nome_arquivo}
                 className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-800 truncate min-w-0">
                <Paperclip size={13} className="shrink-0" />
                <span className="truncate">{e.nome_arquivo}</span>
                <ExternalLink size={12} className="shrink-0" />
              </a>
              {canEdit && (
                <button onClick={() => remove(e.id)} className="ml-2 p-1 text-gray-400 hover:text-error transition-colors shrink-0">
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-400 mb-3">Nenhuma evidência anexada.</p>
      )}
      {canEdit && (
        <>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={e => uploadFiles(e.target.files)}
          />
          <div
            role="button"
            tabIndex={0}
            onClick={() => !uploading && inputRef.current?.click()}
            onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && !uploading) inputRef.current?.click(); }}
            onDragOver={e => { e.preventDefault(); if (!uploading) setDragActive(true); }}
            onDragLeave={e => { e.preventDefault(); setDragActive(false); }}
            onDrop={onDrop}
            className={`flex flex-col items-center justify-center gap-1.5 px-4 py-5 rounded-xl border-2 border-dashed
              cursor-pointer transition-colors text-center
              ${dragActive ? 'border-primary-400 bg-primary-50' : 'border-gray-200 hover:border-primary-300 hover:bg-gray-50'}
              ${uploading ? 'opacity-60 pointer-events-none' : ''}`}
          >
            {uploading ? (
              <>
                <div className="h-5 w-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-xs text-gray-500">Enviando...</span>
              </>
            ) : (
              <>
                <UploadCloud size={22} className="text-primary-500" />
                <span className="text-sm text-gray-600 font-medium">Arraste arquivos aqui ou clique para anexar</span>
                <span className="text-[11px] text-gray-400">Você pode selecionar vários arquivos de uma vez</span>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function HistoricoList({ historico }) {
  if (!historico?.length) return <p className="text-sm text-gray-400">Nenhum histórico registrado.</p>;
  return (
    <div className="space-y-3">
      {historico.map(h => (
        <div key={h.id} className="flex gap-3">
          <div className="w-2 h-2 rounded-full bg-primary-400 mt-1.5 shrink-0" />
          <div>
            <div className="text-sm font-medium text-gray-700">{(h.acao || '').replace(/_/g, ' ')}</div>
            <div className="text-xs text-gray-400">{h.usuario_nome || 'Sistema'} · {fmtDatetime(h.criado_em)}</div>
            {h.observacao && <div className="text-xs text-gray-500 mt-0.5 italic">{h.observacao}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function RotinaModal({ rotinaId, onClose, onSaved }) {
  const { currentUser } = useAuth();
  const { toast } = useToast();
  const [rotina, setRotina] = useState(null);
  const [historico, setHistorico] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showFormulario, setShowFormulario] = useState(false);

  const [status, setStatus] = useState('');
  const [comentario, setComentario] = useState('');
  const [justificativa, setJustificativa] = useState('');
  const [acaoCorretiva, setAcaoCorretiva] = useState('');
  const [responsavelId, setResponsavelId] = useState('');
  const [colegas, setColegas] = useState([]);
  const [novoPrazo, setNovoPrazo] = useState('');
  const [planoSemana, setPlanoSemana] = useState('');
  const [checklist, setChecklist] = useState('');
  const [relatorio, setRelatorio] = useState('');
  const [visitas, setVisitas] = useState('');
  const [resultados, setResultados] = useState('');
  const [carteira, setCarteira] = useState('');
  const [metas, setMetas] = useState('');

  const loadRotina = useCallback(async (onlyMetadata = false) => {
    if (!rotinaId) return;
    if (!onlyMetadata) setLoading(true);
    
    const [r, h] = await Promise.all([
      apiFetch(`/api/rotinas/${rotinaId}`),
      apiFetch(`/api/rotinas/${rotinaId}/historico`),
    ]);
    
    if (r?.ok) {
      const d = r.data;
      setRotina(d);
      
      // Only set form fields if it's the initial load
      if (!onlyMetadata) {
        // Atividade obrigatória vencida (pendência) já entra como "Não Realizada":
        // o colaborador só precisa registrar justificativa e plano de ação.
        const vencidaPendente = d.pendente_prazo && ['nao_iniciada', 'em_andamento'].includes(d.status);
        setStatus(vencidaPendente ? 'nao_realizada' : d.status);
        setComentario(d.comentario || '');
        setJustificativa(d.justificativa || '');
        setAcaoCorretiva(d.acao_corretiva || '');
        setResponsavelId(d.responsavel_id ? String(d.responsavel_id) : '');
        setNovoPrazo(d.novo_prazo || '');
        setPlanoSemana(d.plano_semana || '');
        setChecklist(d.checklist || '');
        setRelatorio(d.relatorio || '');
        setVisitas(d.visitas_ativacoes || '');
        setResultados(d.resultados_visita || '');
        setCarteira(d.carteira_ativa || '');
        setMetas(d.metas_canal || '');
      }
    }
    if (h?.ok) setHistorico(h.data);
    setLoading(false);
  }, [rotinaId]);

  useEffect(() => { loadRotina(); }, [loadRotina]);

  useEffect(() => {
    apiFetch('/api/usuarios/?status=ativo&escopo=delegacao').then(r => { if (r?.ok) setColegas(r.data); });
  }, []);

  const isOverdue = !!rotina?.pendente_prazo;
  // Pendência: atividade obrigatória vencida (qualquer status) ou já marcada como
  // "Não Realizada". Nesse caso é tratada como não realizada — sem relatório,
  // sem evidência obrigatória, apenas justificativa e plano de ação.
  const isPendencia = !!rotina?.vencida || status === 'nao_realizada';
  // Apenas o admin e o próprio dono podem preencher/editar. O Superintendente
  // pode visualizar e aprovar, mas nunca preencher o relatório de terceiros.
  const canEdit = currentUser?.perfil === 'admin' ||
                  rotina?.usuario_id === currentUser?.id;
  const canFill = canEdit && !isOverdue;
  const canRegisterOverdue = canEdit && isOverdue;
  // Em pendência (não realizada) o relatório não pode ser preenchido.
  const canFillReport = canEdit && !isPendencia;

  const planoObrigatorio = status === 'nao_realizada';

  const save = async () => {
    if (isOverdue && status !== 'nao_realizada') {
      toast('Atividade vencida. Registre como Não Realizada e preencha o Plano de Ação.', 'error');
      return;
    }
    if (!comentario || !comentario.trim()) {
      toast(planoObrigatorio ? 'A justificativa é obrigatória.' : 'O comentário é obrigatório.', 'error');
      return;
    }
    if (planoObrigatorio && !planoSemana.trim()) {
      toast('O Plano de Ação é obrigatório quando a atividade não foi realizada.', 'error');
      return;
    }
    if (status === 'concluida' && (!rotina?.evidencias || rotina.evidencias.length === 0)) {
      toast('Anexe pelo menos uma evidência antes de concluir a atividade', 'error');
      return;
    }
    if (status === 'concluida' && !rotina?.formulario_preenchido) {
      toast('Preencha o Relatório Comercial antes de concluir a atividade', 'error');
      return;
    }
    setSaving(true);
    const payload = {
      status, comentario, justificativa, acao_corretiva: acaoCorretiva,
      responsavel_id: responsavelId || null, novo_prazo: novoPrazo || null,
      plano_semana: planoSemana, checklist, relatorio,
      visitas_ativacoes: visitas, resultados_visita: resultados,
      carteira_ativa: carteira, metas_canal: metas,
    };
    const r = await apiFetch(`/api/rotinas/${rotinaId}`, { method: 'PUT', body: JSON.stringify(payload) });
    if (r?.ok) { toast('Rotina atualizada!', 'success'); onSaved?.(); onClose?.(); }
    else toast('Erro ao salvar', 'error');
    setSaving(false);
  };

  return (
    <>
    <Modal
      open={!!rotinaId}
      onClose={onClose}
      title={loading ? 'Carregando...' : (rotina?.atividade_nome || 'Detalhes da Atividade')}
      size="lg"
      footer={
        canEdit && !loading ? (
          <>
            <Button variant="secondary" onClick={onClose}>Cancelar</Button>
            <Button
              variant={rotina?.formulario_preenchido ? 'secondary' : 'primary'}
              icon={FileText}
              onClick={() => setShowFormulario(true)}
              disabled={!canFillReport && !rotina?.formulario_preenchido}
            >
              {rotina?.formulario_preenchido ? 'Ver Relatório' : 'Preencher Relatório'}
            </Button>
            <Button onClick={save} loading={saving}>Salvar Alterações</Button>
          </>
        ) : (
          <>
            {rotina && (
              <Button variant="secondary" icon={FileText} onClick={() => setShowFormulario(true)}>
                Ver Relatório
              </Button>
            )}
            <Button variant="secondary" onClick={onClose}>Fechar</Button>
          </>
        )
      }
    >
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : rotina && (
        <div className="space-y-5">
          {isPendencia && (
            <div className="flex items-start gap-2 p-3 bg-red-50 rounded-xl text-sm text-red-700 border border-red-200">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <span>Atividade vencida, registrada como Não Realizada. Preencha a justificativa e o plano de ação.</span>
            </div>
          )}
          {/* Formulário obrigatório alert */}
          {!rotina.formulario_preenchido && !isPendencia && (
            <div className="flex items-start gap-2 p-3 bg-warning-light rounded-xl text-sm text-warning-dark border border-yellow-200">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <span>O <strong>Relatório Comercial</strong> é obrigatório. Preencha-o antes de concluir a atividade.</span>
            </div>
          )}
          {rotina.formulario_preenchido && (
            <div className="flex items-center gap-2 p-3 bg-green-50 rounded-xl text-sm text-success-dark border border-green-100">
              <FileText size={16} />
              Relatório Comercial preenchido
            </div>
          )}

          {/* Evidência obrigatória */}
          {(!rotina.evidencias || rotina.evidencias.length === 0) && !isPendencia && (
            <div className="flex items-start gap-2 p-3 bg-orange-50 rounded-xl text-sm text-orange-700 border border-orange-200">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span><strong>Evidência obrigatória.</strong> Anexe pelo menos um arquivo antes de concluir a atividade.</span>
            </div>
          )}

          {/* Descrição da atividade */}
          {rotina.atividade_descricao && (
            <div className="p-3 bg-blue-50 border border-blue-100 rounded-xl">
              <p className="text-xs font-semibold text-blue-700 mb-1">O que precisa ser feito</p>
              <p className="text-sm text-blue-800">{rotina.atividade_descricao}</p>
            </div>
          )}

          {/* Meta info grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-gray-50 rounded-xl">
            <div>
              <div className="text-xs font-medium text-gray-400 mb-1">Periodicidade</div>
              <PeriodoBadge periodo={rotina.periodicidade} label={PERIODO_LABELS[rotina.periodicidade]} />
            </div>
            <div>
              <div className="text-xs font-medium text-gray-400 mb-1">Período</div>
              {rotina.periodo_label && (
                <div className="text-xs font-semibold text-gray-800">{rotina.periodo_label}</div>
              )}
              <div className="text-xs text-gray-700">{fmtDate(rotina.periodo_inicio)} → {fmtDate(rotina.periodo_fim)}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-gray-400 mb-1">Usuário</div>
              <div className="text-xs text-gray-700">{rotina.usuario_nome}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-gray-400 mb-1">Evidência</div>
              <div className="text-xs text-gray-500">{rotina.tipo_evidencia || '—'}</div>
            </div>
          </div>

          <Select label="Status" value={status} onChange={e => setStatus(e.target.value)} disabled={!canEdit || isPendencia}>
            <option value="nao_iniciada" disabled={isPendencia}>Não Iniciada</option>
            <option value="em_andamento" disabled={isPendencia}>Em Andamento</option>
            <option value="concluida" disabled={isPendencia}>Concluída</option>
            <option value="nao_realizada">Não Realizada</option>
          </Select>

          <Textarea label={planoObrigatorio ? 'Justificativa' : 'Comentário'} value={comentario} onChange={e => setComentario(e.target.value)}
            rows={2} placeholder={planoObrigatorio ? 'Justifique por que a atividade não foi realizada...' : 'Observações sobre a execução...'}
            disabled={!(canFill || canRegisterOverdue)} required />

          <Textarea label={planoObrigatorio ? 'Plano de Ação' : 'Plano da Semana'} value={planoSemana} onChange={e => setPlanoSemana(e.target.value)}
            rows={3} placeholder={planoObrigatorio ? 'Obrigatório: descreva o plano de ação para a atividade não realizada...' : 'Registre o plano da semana...'}
            disabled={!(canFill || canRegisterOverdue)} required={planoObrigatorio} />

          <div>
            <Select
              label="Responsável pela Ação"
              value={responsavelId}
              onChange={e => setResponsavelId(e.target.value)}
              disabled={!(canFill || canRegisterOverdue)}
            >
              <option value="">Nenhum (eu mesmo cuido)</option>
              {colegas.map(u => (
                <option key={u.id} value={u.id}>{u.nome}{u.id === currentUser?.id ? ' (eu)' : ''}</option>
              ))}
            </Select>
            {responsavelId && Number(responsavelId) !== currentUser?.id && (
              <p className="text-xs text-gray-400 mt-1">
                A pessoa selecionada recebe uma notificação e pode acompanhar esta atividade até concluí-la.
              </p>
            )}
          </div>

          <div className="border-t border-gray-100 pt-5">
            <div className="flex items-center gap-2 mb-3">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Evidências e Anexos</h4>
              {!isPendencia && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-100 text-red-600">Obrigatório</span>
              )}
            </div>
            {status === 'concluida' && (!rotina.evidencias || rotina.evidencias.length === 0) && !isOverdue && (
              <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
                Anexe pelo menos uma evidência para concluir esta atividade.
              </p>
            )}
            <EvidenciasList evidencias={rotina.evidencias} rotinaId={rotinaId} canEdit={canFill} onReload={() => loadRotina(true)} />
          </div>

          <div className="border-t border-gray-100 pt-5">
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Histórico</h4>
            <HistoricoList historico={historico} />
          </div>

          {rotina.data_conclusao && (
            <div className="flex items-center gap-2 p-3 bg-green-50 rounded-xl text-sm text-success-dark border border-green-100">
              <CheckCircle size={16} />
              Concluída em {fmtDatetime(rotina.data_conclusao)}
            </div>
          )}
        </div>
      )}
    </Modal>

    {showFormulario && (
      <FormularioComercialModal
        rotinaId={rotinaId}
        rotina={rotina}
        currentUser={currentUser}
        readOnly={!canFillReport}
        onClose={() => setShowFormulario(false)}
        onSaved={() => { loadRotina(true); }}
      />
    )}
  </>
  );
}
