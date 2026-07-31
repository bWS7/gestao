import { useState, useEffect, useCallback } from 'react';
import { Download, FileText, Users2, TrendingUp } from 'lucide-react';
import { apiFetch, downloadExport } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Modal } from '../components/ui/Modal';
import { Card } from '../components/ui/Card';
import { Table, Thead, Th, Tbody, Tr, Td } from '../components/ui/Table';
import { Input, Select } from '../components/ui/Input';
import Button from '../components/ui/Button';
import { EmptyState, PageSpinner } from '../components/ui/Spinner';
import Pagination, { usePagination } from '../components/ui/Pagination';
import { StatusBadge, PeriodoBadge } from '../components/ui/Badge';
import { PERFIL_LABELS, STATUS_LABELS, PERIODO_LABELS, fmtDate, fmtDatetime } from '../utils/constants';
import RotinaModal from '../components/shared/RotinaModal';

const ATIVIDADES_PER_PAGE = 15;

// Lista paginada das atividades de UM liderado no período/filtros vigentes na
// tela — aberta ao clicar no nome do colaborador, pra o Superintendente/admin
// ver exatamente o que está sendo feito sem precisar sair do comparativo.
function AtividadesLideradoModal({ liderado, dataInicio, dataFim, periodicidade, onClose }) {
  const [rotinas, setRotinas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    let url = `/api/rotinas/?usuario_id=${liderado.usuario_id}&periodo=todas&historico=1&data_inicio=${dataInicio}&data_fim=${dataFim}`;
    if (periodicidade && periodicidade !== 'todas') url += `&periodicidade=${periodicidade}`;
    const r = await apiFetch(url);
    if (r?.ok) setRotinas(r.data);
    setLoading(false);
  }, [liderado.usuario_id, dataInicio, dataFim, periodicidade]);

  useEffect(() => { load(); }, [load]);

  const { page, setPage, pages, total, slice } = usePagination(rotinas, ATIVIDADES_PER_PAGE, rotinas);

  return (
    <>
      <Modal open onClose={onClose} title={`Atividades de ${liderado.nome}`} size="xl">
        {loading ? (
          <PageSpinner />
        ) : rotinas.length === 0 ? (
          <EmptyState icon={TrendingUp} title="Nenhuma atividade no período" description="Ajuste o período ou a periodicidade para ver outras atividades." />
        ) : (
          <div className="-mx-4 sm:-mx-6">
            <Table>
              <Thead>
                <tr>
                  <Th>Atividade</Th>
                  <Th>Periodicidade</Th>
                  <Th>Período</Th>
                  <Th>Status</Th>
                  <Th>Conclusão</Th>
                </tr>
              </Thead>
              <Tbody>
                {slice.map(r => (
                  <Tr key={r.id} onClick={() => setOpenId(r.id)}>
                    <Td className="max-w-[240px]">
                      <span className="font-medium text-gray-700 line-clamp-2">{r.atividade_nome}</span>
                    </Td>
                    <Td><PeriodoBadge periodo={r.periodicidade} label={PERIODO_LABELS[r.periodicidade]} /></Td>
                    <Td><span className="text-xs text-gray-500 whitespace-nowrap">{fmtDate(r.periodo_inicio)} → {fmtDate(r.periodo_fim)}</span></Td>
                    <Td>
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={r.status} label={STATUS_LABELS[r.status]} />
                        {r.vencida && r.status !== 'concluida' && (
                          <span className="text-[10px] font-medium text-error">Atrasada</span>
                        )}
                      </div>
                    </Td>
                    <Td><span className="text-xs text-gray-500">{r.data_conclusao ? fmtDatetime(r.data_conclusao) : '—'}</span></Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
            <Pagination page={page} pages={pages} total={total} perPage={ATIVIDADES_PER_PAGE} onChange={setPage} />
          </div>
        )}
      </Modal>

      <RotinaModal rotinaId={openId} onClose={() => setOpenId(null)} onSaved={load} />
    </>
  );
}

function primeiroDiaMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
}
function ultimoDiaMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0).toISOString().slice(0, 10);
}

function BarraComparativa({ pct }) {
  const cor = pct >= 80 ? 'bg-success' : pct >= 50 ? 'bg-warning' : 'bg-error';
  return (
    <div className="w-full h-2 rounded-full bg-gray-100 overflow-hidden">
      <div className={`h-full ${cor} transition-all`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

export default function ComparativoLideradosPage() {
  const { currentUser } = useAuth();
  const { toast } = useToast();
  const ehAdmin = currentUser?.perfil === 'admin';
  const [dados, setDados] = useState(null);
  const [usuarios, setUsuarios] = useState([]);
  const [regionais, setRegionais] = useState([]);
  const [regionalId, setRegionalId] = useState('');
  const [loading, setLoading] = useState(true);
  const [usuarioId, setUsuarioId] = useState('');
  const [periodicidade, setPeriodicidade] = useState('todas');
  const [dataInicio, setDataInicio] = useState(primeiroDiaMes());
  const [dataFim, setDataFim] = useState(ultimoDiaMes());
  const [lideradoAberto, setLideradoAberto] = useState(null);

  // Admin não tem regional própria (diferente do Superintendente, que o
  // backend já resolve sozinho) — precisa escolher qual regional comparar.
  useEffect(() => {
    if (!ehAdmin) return;
    apiFetch('/api/regionais/?ativo=true').then(r => {
      if (r?.ok) {
        setRegionais(r.data);
        if (r.data.length === 1) setRegionalId(String(r.data[0].id));
      }
    });
  }, [ehAdmin]);

  useEffect(() => {
    let url = '/api/usuarios/?status=ativo';
    if (ehAdmin && regionalId) url += `&regional_id=${regionalId}`;
    apiFetch(url).then(r => {
      if (r?.ok) setUsuarios(r.data.filter(u => !['admin', 'sr'].includes(u.perfil)));
    });
  }, [ehAdmin, regionalId]);

  const podeCarregar = !ehAdmin || !!regionalId;

  const load = useCallback(async () => {
    if (!podeCarregar) { setLoading(false); return; }
    setLoading(true);
    let url = `/api/rotinas/relatorio-liderados?data_inicio=${dataInicio}&data_fim=${dataFim}`;
    if (usuarioId) url += `&usuario_id=${usuarioId}`;
    if (periodicidade && periodicidade !== 'todas') url += `&periodicidade=${periodicidade}`;
    if (ehAdmin && regionalId) url += `&regional_id=${regionalId}`;
    const r = await apiFetch(url);
    if (r?.ok) setDados(r.data);
    else toast(r?.data?.erro || 'Erro ao carregar relatório', 'error');
    setLoading(false);
  }, [usuarioId, periodicidade, dataInicio, dataFim, ehAdmin, regionalId, podeCarregar, toast]);

  useEffect(() => { load(); }, [load]);

  const exportar = (formato) => {
    let url = `/api/rotinas/relatorio-liderados/export?formato=${formato}&data_inicio=${dataInicio}&data_fim=${dataFim}`;
    if (usuarioId) url += `&usuario_id=${usuarioId}`;
    if (periodicidade && periodicidade !== 'todas') url += `&periodicidade=${periodicidade}`;
    if (ehAdmin && regionalId) url += `&regional_id=${regionalId}`;
    downloadExport(url, `comparativo_liderados.${formato}`).catch(() => toast('Erro ao exportar', 'error'));
  };

  const liderados = dados?.liderados || [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        {ehAdmin && (
          <Select value={regionalId} onChange={e => setRegionalId(e.target.value)} className="w-52">
            <option value="">Selecione a Regional...</option>
            {regionais.map(r => (
              <option key={r.id} value={r.id}>{r.nome}</option>
            ))}
          </Select>
        )}
        <Input type="date" value={dataInicio} onChange={e => setDataInicio(e.target.value)} className="w-40" title="Data início" />
        <Input type="date" value={dataFim} onChange={e => setDataFim(e.target.value)} className="w-40" title="Data fim" />
        <Select value={usuarioId} onChange={e => setUsuarioId(e.target.value)} className="w-52">
          <option value="">Todos os Liderados</option>
          {usuarios.map(u => (
            <option key={u.id} value={u.id}>{u.nome} ({PERFIL_LABELS[u.perfil] || u.perfil})</option>
          ))}
        </Select>
        <Select value={periodicidade} onChange={e => setPeriodicidade(e.target.value)} className="w-36">
          <option value="todas">Todas</option>
          <option value="diaria">Diária</option>
          <option value="semanal">Semanal</option>
          <option value="quinzenal">Quinzenal</option>
          <option value="mensal">Mensal</option>
        </Select>
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" icon={Download} onClick={() => exportar('csv')} disabled={!podeCarregar}>Excel (CSV)</Button>
          <Button variant="secondary" icon={FileText} onClick={() => exportar('pdf')} disabled={!podeCarregar}>PDF</Button>
        </div>
      </div>

      {!podeCarregar ? (
        <EmptyState icon={Users2} title="Selecione uma regional" description="Escolha a regional para ver o comparativo dos liderados." />
      ) : loading ? (
        <PageSpinner />
      ) : (
        <>
          {dados?.totais && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Card className="p-4">
                <div className="text-xs text-gray-400 mb-1">Total de Rotinas</div>
                <div className="text-xl font-semibold text-gray-900">{dados.totais.total}</div>
              </Card>
              <Card className="p-4">
                <div className="text-xs text-gray-400 mb-1">Concluídas</div>
                <div className="text-xl font-semibold text-success">{dados.totais.concluidas}</div>
              </Card>
              <Card className="p-4">
                <div className="text-xs text-gray-400 mb-1">Pendentes</div>
                <div className="text-xl font-semibold text-warning">{dados.totais.pendentes}</div>
              </Card>
              <Card className="p-4">
                <div className="text-xs text-gray-400 mb-1">Atrasadas</div>
                <div className="text-xl font-semibold text-error">{dados.totais.atrasadas}</div>
              </Card>
            </div>
          )}

          <Card>
            {liderados.length === 0 ? (
              <EmptyState icon={Users2} title="Nenhum liderado encontrado" description="Ajuste os filtros de período ou colaborador." />
            ) : (
              <Table>
                <Thead>
                  <tr>
                    <Th>Colaborador</Th>
                    <Th>Total</Th>
                    <Th>Concluídas</Th>
                    <Th>Pendentes</Th>
                    <Th>Atrasadas</Th>
                    <Th>% Execução</Th>
                  </tr>
                </Thead>
                <Tbody>
                  {liderados.map(l => (
                    <Tr key={l.usuario_id} onClick={() => setLideradoAberto(l)}>
                      <Td>
                        <div className="font-medium text-gray-800">{l.nome}</div>
                        <div className="text-xs text-gray-400">{PERFIL_LABELS[l.perfil] || l.perfil}</div>
                      </Td>
                      <Td>{l.total}</Td>
                      <Td className="text-success font-medium">{l.concluidas}</Td>
                      <Td className="text-warning font-medium">{l.pendentes}</Td>
                      <Td className="text-error font-medium">{l.atrasadas}</Td>
                      <Td className="min-w-[140px]">
                        <div className="flex items-center gap-2">
                          <BarraComparativa pct={l.percentual_execucao} />
                          <span className="text-xs font-semibold text-gray-700 shrink-0 w-10 text-right">{l.percentual_execucao}%</span>
                        </div>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </Card>
        </>
      )}

      {lideradoAberto && (
        <AtividadesLideradoModal
          liderado={lideradoAberto}
          dataInicio={dataInicio}
          dataFim={dataFim}
          periodicidade={periodicidade}
          onClose={() => setLideradoAberto(null)}
        />
      )}
    </div>
  );
}
