import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, FileText, Target } from 'lucide-react';
import { apiFetch } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { Modal } from '../ui/Modal';
import { Select, Input, Textarea } from '../ui/Input';
import Button from '../ui/Button';
import { getReportType, REPORT_TITLES, REPORT_OBJECTIVES, buildEmptyForm, validateRequiredReport, normalizeLoadedForm } from './reportConfigs';
import EmpreendimentoSelect from './EmpreendimentoSelect';
import { ColegasProvider } from './ColegasContext';
import {
  FormReuniaoPerformance, FormResultadoSemanal, FormDecoesCanal,
  FormAnaliseRiscos, FormAcompanhamentoLiderados, FormComiteMensal,
  FormCanalParcerias, FormRotinaVisitas, FormCarteiraParceiros,
  FormReativacaoExpansao, FormTreinamentoParceiros,
  FormChecklistStand, FormReuniaoStand, FormRelatorioGeralEmp,
  FormAnaliseConcorrencia, FormRelatorioMensalEmp,
  FormFunilVendas, FormPerformanceCorretores, FormAlinhamentoIndividual,
  FormTreinamentoTime, FormMonitoramentoRotinas, FormResultadoGeralTime,
  ResponsavelSelect,
} from './ReportForms';

// ── Legacy constants (for padrao report) ─────────────────────
const CATEGORIAS = ['Reunião', 'Treinamento', 'Diagnóstico', 'Acompanhamento', 'Planejamento', 'Relatório', 'Comitê', 'Externo'];
const STATUS_INDICADOR = ['OK', 'Atenção', 'Crítico'];
const MOTIVOS_DESVIO = ['Atraso operacional', 'Baixa conversão', 'Perda de lead', 'Falta de padrão', 'Erro de processo', 'Falha de comunicação', 'Baixa produtividade', 'Falta de treinamento', 'Problema sistêmico'];
const PRIORIDADES = ['Alta', 'Média', 'Baixa'];
const STATUS_ACAO = ['Aberto', 'Em andamento', 'Concluído'];
const AREAS_ESCALONAMENTO = ['Diretoria', 'Marketing', 'Crédito', 'TI', 'Produto', 'Jurídico', 'Operações', 'RH'];
const SIM_NAO = ['Sim', 'Parcialmente', 'Não'];
const INDICADORES = ['Leads', 'Conversão', 'Visitas', 'Reservas', 'Vendas'];

const PERFIL_LABELS = {
  admin: 'Administrador', sr: 'Superintendente Regional',
  gv: 'Gerente de Vendas', cd: 'Coordenador de Produto', sp: 'Supervisor de Parceria',
};

function SectionTitle({ number, title }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <div className="w-6 h-6 rounded-full bg-primary-600 text-white text-xs font-bold flex items-center justify-center shrink-0">{number}</div>
      <h3 className="text-sm font-semibold text-gray-800 uppercase tracking-wide">{title}</h3>
    </div>
  );
}

function Section({ children, className = '' }) {
  return <div className={`border border-gray-100 rounded-xl p-4 space-y-3 ${className}`}>{children}</div>;
}

function emptyParticipante() { return { nome: '', cargo: '', area: '', observacoes: '' }; }
function emptyAcao() { return { acao: '', responsavel: '', prazo: '', prioridade: 'Alta', status: 'Aberto' }; }

function buildLegacyInitialForm() {
  return {
    categoria: '', empreendimento: '', data_execucao: new Date().toISOString().split('T')[0],
    hora_inicio: '', hora_termino: '', objetivo: '', resumo_execucao: '', principais_temas: '',
    participantes: [emptyParticipante()],
    resultados: INDICADORES.reduce((acc, ind) => { acc[ind] = { resultado_atual: '', meta: '', status: '', observacoes: '' }; return acc; }, {}),
    observacao_evidencias: '', dificuldades: '', motivo_desvio_1: '', motivo_desvio_2: '',
    descricao_causa: '', plano_acao: [emptyAcao()],
    necessita_apoio: '', area_apoio: '', motivo_apoio: '', objetivo_atingido: '', proximos_passos: '',
  };
}

// ── Legacy form (Relatório Padrão) ───────────────────────────
function LegacyForm({ form, set, setResultado, setParticipante, addParticipante, removeParticipante, setAcao, addAcao, removeAcao, readOnly, rotina, currentUser }) {
  const periodicidadeLabel = { diaria: 'Diaria', semanal: 'Semanal', quinzenal: 'Quinzenal', mensal: 'Mensal' }[rotina?.periodicidade] || '';

  return (
    <div className="space-y-5">
      <Section>
        <SectionTitle number="1" title="Identificação da Atividade" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input label="Atividade" value={rotina?.atividade_nome || ''} disabled />
          <Select label="Categoria" value={form.categoria} onChange={e => set('categoria', e.target.value)} disabled={readOnly}>
            <option value="">Selecione...</option>
            {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Input label="Responsável" value={rotina?.usuario_nome || currentUser?.nome || ''} disabled />
          <Input label="Cargo" value={PERFIL_LABELS[rotina?.perfil || currentUser?.perfil] || ''} disabled />
          <Input label="Regional" value={currentUser?.regional_nome || ''} disabled />
          <EmpreendimentoSelect value={form.empreendimento} onChange={v => set('empreendimento', v)} disabled={readOnly} />
          <Input type="date" label="Data da execução" value={form.data_execucao} onChange={e => set('data_execucao', e.target.value)} disabled={readOnly} />
          <Input label="Periodicidade" value={periodicidadeLabel} disabled />
          <Input type="time" label="Hora início" value={form.hora_inicio} onChange={e => set('hora_inicio', e.target.value)} disabled={readOnly} />
          <Input type="time" label="Hora término" value={form.hora_termino} onChange={e => set('hora_termino', e.target.value)} disabled={readOnly} />
        </div>
      </Section>

      <Section>
        <SectionTitle number="2" title="Objetivo da Atividade" />
        <Textarea value={form.objetivo} onChange={e => set('objetivo', e.target.value)} placeholder="Descreva o objetivo..." rows={3} disabled={readOnly} />
      </Section>

      <Section>
        <SectionTitle number="3" title="Execução da Atividade" />
        <Textarea label="Resumo da execução" value={form.resumo_execucao} onChange={e => set('resumo_execucao', e.target.value)} rows={3} disabled={readOnly} />
        <Textarea label="Principais temas abordados" value={form.principais_temas} onChange={e => set('principais_temas', e.target.value)} rows={2} disabled={readOnly} />
      </Section>

      <Section>
        <SectionTitle number="4" title="Participantes" />
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs min-w-[480px]">
            <thead><tr className="border-b border-gray-100">
              {['Nome', 'Cargo', 'Área', 'Observações', ''].map(h => <th key={h} className="text-left text-gray-400 font-medium pb-2 pr-2">{h}</th>)}
            </tr></thead>
            <tbody>
              {form.participantes.map((p, i) => (
                <tr key={i} className="border-b border-gray-50">
                  {['nome', 'cargo', 'area', 'observacoes'].map(f => (
                    <td key={f} className="pr-2 py-1.5">
                      <input className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50"
                        value={p[f]} onChange={e => setParticipante(i, f, e.target.value)} disabled={readOnly} />
                    </td>
                  ))}
                  <td className="py-1.5">{!readOnly && form.participantes.length > 1 && (
                    <button onClick={() => removeParticipante(i)} className="p-1 text-gray-300 hover:text-error transition-colors"><Trash2 size={13} /></button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!readOnly && <button onClick={addParticipante} className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 font-medium mt-1"><Plus size={13} /> Adicionar participante</button>}
      </Section>

      <Section>
        <SectionTitle number="5" title="Resultados / Indicadores" />
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs min-w-[520px]">
            <thead><tr className="border-b border-gray-100">
              {['Indicador', 'Resultado Atual', 'Meta', 'Status', 'Observações'].map(h => <th key={h} className="text-left text-gray-400 font-medium pb-2 pr-2">{h}</th>)}
            </tr></thead>
            <tbody>
              {INDICADORES.map(ind => {
                const row = form.resultados[ind] || {};
                return (
                  <tr key={ind} className="border-b border-gray-50">
                    <td className="pr-2 py-1.5 font-medium text-gray-700">{ind}</td>
                    <td className="pr-2 py-1.5"><input className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={row.resultado_atual || ''} onChange={e => setResultado(ind, 'resultado_atual', e.target.value)} disabled={readOnly} /></td>
                    <td className="pr-2 py-1.5"><input className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={row.meta || ''} onChange={e => setResultado(ind, 'meta', e.target.value)} disabled={readOnly} /></td>
                    <td className="pr-2 py-1.5">
                      <select className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={row.status || ''} onChange={e => setResultado(ind, 'status', e.target.value)} disabled={readOnly}>
                        <option value="">—</option>{STATUS_INDICADOR.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className="py-1.5"><input className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={row.observacoes || ''} onChange={e => setResultado(ind, 'observacoes', e.target.value)} disabled={readOnly} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Section>
        <SectionTitle number="6" title="Evidências da Execução" />
        <p className="text-xs text-gray-500 -mt-1">Arquivos de evidência são anexados diretamente na atividade.</p>
        <Textarea label="Observação das evidências" value={form.observacao_evidencias} onChange={e => set('observacao_evidencias', e.target.value)} rows={2} disabled={readOnly} />
      </Section>

      <Section>
        <SectionTitle number="7" title="Dificuldades Identificadas" />
        <Textarea label="Problemas ou desvios encontrados" value={form.dificuldades} onChange={e => set('dificuldades', e.target.value)} rows={3} disabled={readOnly} />
      </Section>

      <Section>
        <SectionTitle number="8" title="Análise de Causa" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Select label="Motivo do desvio 1" value={form.motivo_desvio_1} onChange={e => set('motivo_desvio_1', e.target.value)} disabled={readOnly}>
            <option value="">Selecione...</option>{MOTIVOS_DESVIO.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
          <Select label="Motivo do desvio 2" value={form.motivo_desvio_2} onChange={e => set('motivo_desvio_2', e.target.value)} disabled={readOnly}>
            <option value="">Selecione...</option>{MOTIVOS_DESVIO.map(m => <option key={m} value={m}>{m}</option>)}
          </Select>
        </div>
        <Textarea label="Descrição da causa" value={form.descricao_causa} onChange={e => set('descricao_causa', e.target.value)} rows={3} disabled={readOnly} />
      </Section>

      <Section>
        <SectionTitle number="9" title="Plano de Ação" />
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-xs min-w-[560px]">
            <thead><tr className="border-b border-gray-100">
              {['Ação Definida', 'Responsável', 'Prazo', 'Prioridade', 'Status', ''].map(h => <th key={h} className="text-left text-gray-400 font-medium pb-2 pr-2">{h}</th>)}
            </tr></thead>
            <tbody>
              {form.plano_acao.map((a, i) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="pr-2 py-1.5"><input className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={a.acao} onChange={e => setAcao(i, 'acao', e.target.value)} disabled={readOnly} /></td>
                  <td className="pr-2 py-1.5">
                    <ResponsavelSelect
                      className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50"
                      idValue={a.responsavel_id} nomeValue={a.responsavel}
                      onSelect={(id, nome) => { setAcao(i, 'responsavel_id', id); setAcao(i, 'responsavel', nome); }}
                      disabled={readOnly}
                    />
                  </td>
                  <td className="pr-2 py-1.5"><input type="date" className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={a.prazo} onChange={e => setAcao(i, 'prazo', e.target.value)} disabled={readOnly} /></td>
                  <td className="pr-2 py-1.5"><select className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={a.prioridade} onChange={e => setAcao(i, 'prioridade', e.target.value)} disabled={readOnly}>{PRIORIDADES.map(p => <option key={p} value={p}>{p}</option>)}</select></td>
                  <td className="pr-2 py-1.5"><select className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:bg-gray-50" value={a.status} onChange={e => setAcao(i, 'status', e.target.value)} disabled={readOnly}>{STATUS_ACAO.map(s => <option key={s} value={s}>{s}</option>)}</select></td>
                  <td className="py-1.5">{!readOnly && form.plano_acao.length > 1 && (
                    <button onClick={() => removeAcao(i)} className="p-1 text-gray-300 hover:text-error transition-colors"><Trash2 size={13} /></button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!readOnly && <button onClick={addAcao} className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800 font-medium mt-1"><Plus size={13} /> Adicionar ação</button>}
      </Section>

      <Section>
        <SectionTitle number="10" title="Necessidade de Escalonamento" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Select label="Necessita apoio de outra área?" value={form.necessita_apoio} onChange={e => set('necessita_apoio', e.target.value)} disabled={readOnly}>
            <option value="">Selecione...</option>{SIM_NAO.map(s => <option key={s} value={s}>{s}</option>)}
          </Select>
          {form.necessita_apoio && form.necessita_apoio !== 'Não' && (
            <Select label="Área de apoio" value={form.area_apoio} onChange={e => set('area_apoio', e.target.value)} disabled={readOnly}>
              <option value="">Selecione...</option>{AREAS_ESCALONAMENTO.map(a => <option key={a} value={a}>{a}</option>)}
            </Select>
          )}
        </div>
        {form.necessita_apoio && form.necessita_apoio !== 'Não' && (
          <Textarea label="Motivo do apoio" value={form.motivo_apoio} onChange={e => set('motivo_apoio', e.target.value)} rows={2} disabled={readOnly} />
        )}
      </Section>

      <Section>
        <SectionTitle number="11" title="Avaliação Final da Atividade" />
        <Select label="O objetivo foi atingido?" value={form.objetivo_atingido} onChange={e => set('objetivo_atingido', e.target.value)} disabled={readOnly}>
          <option value="">Selecione...</option>{SIM_NAO.map(s => <option key={s} value={s}>{s}</option>)}
        </Select>
        <Textarea label="Próximos passos" value={form.proximos_passos} onChange={e => set('proximos_passos', e.target.value)} rows={3} disabled={readOnly} />
      </Section>
    </div>
  );
}

// ── Main Modal ───────────────────────────────────────────────
export default function FormularioComercialModal({ rotinaId, rotina, currentUser, onClose, onSaved, readOnly = false }) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);
  const [colegas, setColegas] = useState([]);

  // Colegas da regional do usuário logado — usados por todo campo
  // "Responsável" dos relatórios (vira uma lista de vinculação, não texto livre).
  useEffect(() => {
    apiFetch('/api/usuarios/?status=ativo&escopo=delegacao').then(r => { if (r?.ok) setColegas(r.data); });
  }, []);

  const reportType = getReportType(rotina?.atividade_nome, rotina?.perfil || currentUser?.perfil);
  const isCustom = reportType !== 'padrao';
  const title = REPORT_TITLES[reportType] || 'Relatório Padrão Comercial';

  const load = useCallback(async () => {
    if (!rotinaId) return;
    setLoading(true);
    const r = await apiFetch(`/api/rotinas/${rotinaId}/formulario`);
    if (r?.ok) {
      let dados = r.data.formulario && Object.keys(r.data.formulario).length > 0
        ? r.data.formulario : null;

      if (!dados) {
        // Build empty form based on type
        const custom = buildEmptyForm(reportType);
        dados = custom || buildLegacyInitialForm();
      }

      // Migra relatórios antigos para o formato de blocos repetíveis quando aplicável.
      dados = normalizeLoadedForm(reportType, dados);

      // Legacy form safety
      if (!isCustom) {
        if (!Array.isArray(dados.participantes) || dados.participantes.length === 0) dados.participantes = [emptyParticipante()];
        if (!Array.isArray(dados.plano_acao) || dados.plano_acao.length === 0) dados.plano_acao = [emptyAcao()];
        if (!dados.resultados) dados.resultados = INDICADORES.reduce((acc, ind) => { acc[ind] = { resultado_atual: '', meta: '', status: '', observacoes: '' }; return acc; }, {});
      }

      setForm(dados);
    }
    setLoading(false);
  }, [rotinaId, reportType, isCustom]);

  useEffect(() => { load(); }, [load]);

  // ── Generic setters ──
  const set = (field, value) => setForm(prev => ({ ...prev, [field]: value }));

  const setList = (listName, index, field, value) =>
    setForm(prev => {
      const list = [...(prev[listName] || [])];
      list[index] = { ...list[index], [field]: value };
      return { ...prev, [listName]: list };
    });

  const addItem = (listName, empty) =>
    setForm(prev => ({ ...prev, [listName]: [...(prev[listName] || []), empty] }));

  const removeItem = (listName, index) =>
    setForm(prev => ({ ...prev, [listName]: prev[listName].filter((_, i) => i !== index) }));

  // ── Legacy-specific setters ──
  const setResultado = (ind, field, value) =>
    setForm(prev => ({ ...prev, resultados: { ...prev.resultados, [ind]: { ...prev.resultados[ind], [field]: value } } }));

  const setParticipante = (i, f, v) => setList('participantes', i, f, v);
  const addParticipante = () => addItem('participantes', emptyParticipante());
  const removeParticipante = (i) => removeItem('participantes', i);

  const setAcao = (i, f, v) => setList('plano_acao', i, f, v);
  const addAcao = () => addItem('plano_acao', emptyAcao());
  const removeAcao = (i) => removeItem('plano_acao', i);

  const save = async () => {
    if (isCustom && !validateRequiredReport(reportType, form)) {
      toast('Preencha todos os campos obrigatórios do relatório.', 'error');
      return;
    }

    setSaving(true);
    const r = await apiFetch(`/api/rotinas/${rotinaId}/formulario`, {
      method: 'PUT', body: JSON.stringify({ formulario: form }),
    });
    if (r?.ok) { toast('Relatório salvo!', 'success'); onSaved?.(); onClose?.(); }
    else toast(r?.data?.erro || 'Erro ao salvar formulário', 'error');
    setSaving(false);
  };

  if (loading || !form) {
    return (
      <Modal open title={title} onClose={onClose} size="xl">
        <div className="flex justify-center py-16">
          <div className="h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
        </div>
      </Modal>
    );
  }

  const formProps = { form, set, setList, addItem, removeItem, readOnly };

  return (
    <ColegasProvider value={colegas}>
    <Modal
      open onClose={onClose} title={title} size="xl"
      footer={readOnly
        ? <Button variant="secondary" onClick={onClose}>Fechar</Button>
        : <><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button icon={FileText} onClick={save} loading={saving}>Salvar Relatório</Button></>
      }
    >
      {/* Objective banner for custom reports */}
      {isCustom && REPORT_OBJECTIVES[reportType] && (
        <div className="flex items-start gap-2 p-3 mb-5 bg-primary-50 border border-primary-100 rounded-xl">
          <Target size={16} className="text-primary-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-semibold text-primary-700 mb-0.5">Objetivo</p>
            <p className="text-sm text-primary-800">{REPORT_OBJECTIVES[reportType]}</p>
          </div>
        </div>
      )}

      {/* Render correct form */}
      {reportType === 'reuniao_performance' && <FormReuniaoPerformance {...formProps} />}
      {reportType === 'resultado_semanal' && <FormResultadoSemanal {...formProps} />}
      {reportType === 'decisoes_canal' && <FormDecoesCanal {...formProps} />}
      {reportType === 'analise_riscos' && <FormAnaliseRiscos {...formProps} />}
      {reportType === 'acompanhamento_liderados' && <FormAcompanhamentoLiderados {...formProps} />}
      {reportType === 'comite_mensal' && <FormComiteMensal {...formProps} />}
      {reportType === 'canal_parcerias' && <FormCanalParcerias {...formProps} />}
      {reportType === 'rotina_visitas' && <FormRotinaVisitas {...formProps} />}
      {reportType === 'carteira_parceiros' && <FormCarteiraParceiros {...formProps} />}
      {reportType === 'reativacao_expansao' && <FormReativacaoExpansao {...formProps} />}
      {reportType === 'treinamento_parceiros' && <FormTreinamentoParceiros {...formProps} />}
      {reportType === 'checklist_stand' && <FormChecklistStand {...formProps} />}
      {reportType === 'reuniao_stand' && <FormReuniaoStand {...formProps} />}
      {reportType === 'relatorio_geral_emp' && <FormRelatorioGeralEmp {...formProps} />}
      {reportType === 'analise_concorrencia' && <FormAnaliseConcorrencia {...formProps} />}
      {reportType === 'relatorio_mensal_emp' && <FormRelatorioMensalEmp {...formProps} />}
      {reportType === 'funil_vendas' && <FormFunilVendas {...formProps} />}
      {reportType === 'performance_corretores' && <FormPerformanceCorretores {...formProps} />}
      {reportType === 'alinhamento_individual' && <FormAlinhamentoIndividual {...formProps} />}
      {reportType === 'treinamento_time' && <FormTreinamentoTime {...formProps} />}
      {reportType === 'monitoramento_rotinas' && <FormMonitoramentoRotinas {...formProps} />}
      {reportType === 'resultado_geral_time' && <FormResultadoGeralTime {...formProps} />}
      {reportType === 'padrao' && (
        <LegacyForm
          form={form} set={set}
          setResultado={setResultado}
          setParticipante={setParticipante} addParticipante={addParticipante} removeParticipante={removeParticipante}
          setAcao={setAcao} addAcao={addAcao} removeAcao={removeAcao}
          readOnly={readOnly} rotina={rotina} currentUser={currentUser}
        />
      )}
    </Modal>
    </ColegasProvider>
  );
}
