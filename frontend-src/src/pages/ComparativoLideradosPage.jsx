import { useState, useEffect, useCallback } from 'react';
import { Download, FileText, Users2 } from 'lucide-react';
import { apiFetch, downloadExport } from '../api/client';
import { useToast } from '../context/ToastContext';
import { Card } from '../components/ui/Card';
import { Table, Thead, Th, Tbody, Tr, Td } from '../components/ui/Table';
import { Input, Select } from '../components/ui/Input';
import Button from '../components/ui/Button';
import { EmptyState, PageSpinner } from '../components/ui/Spinner';
import { PERFIL_LABELS } from '../utils/constants';

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
  const { toast } = useToast();
  const [dados, setDados] = useState(null);
  const [usuarios, setUsuarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [usuarioId, setUsuarioId] = useState('');
  const [periodicidade, setPeriodicidade] = useState('todas');
  const [dataInicio, setDataInicio] = useState(primeiroDiaMes());
  const [dataFim, setDataFim] = useState(ultimoDiaMes());

  useEffect(() => {
    apiFetch('/api/usuarios/?status=ativo').then(r => {
      if (r?.ok) setUsuarios(r.data.filter(u => !['admin', 'sr'].includes(u.perfil)));
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    let url = `/api/rotinas/relatorio-liderados?data_inicio=${dataInicio}&data_fim=${dataFim}`;
    if (usuarioId) url += `&usuario_id=${usuarioId}`;
    if (periodicidade && periodicidade !== 'todas') url += `&periodicidade=${periodicidade}`;
    const r = await apiFetch(url);
    if (r?.ok) setDados(r.data);
    else toast(r?.data?.erro || 'Erro ao carregar relatório', 'error');
    setLoading(false);
  }, [usuarioId, periodicidade, dataInicio, dataFim, toast]);

  useEffect(() => { load(); }, [load]);

  const exportar = (formato) => {
    let url = `/api/rotinas/relatorio-liderados/export?formato=${formato}&data_inicio=${dataInicio}&data_fim=${dataFim}`;
    if (usuarioId) url += `&usuario_id=${usuarioId}`;
    if (periodicidade && periodicidade !== 'todas') url += `&periodicidade=${periodicidade}`;
    downloadExport(url, `comparativo_liderados.${formato}`).catch(() => toast('Erro ao exportar', 'error'));
  };

  const liderados = dados?.liderados || [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
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
          <Button variant="secondary" icon={Download} onClick={() => exportar('csv')}>Excel (CSV)</Button>
          <Button variant="secondary" icon={FileText} onClick={() => exportar('pdf')}>PDF</Button>
        </div>
      </div>

      {loading ? (
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
                    <Tr key={l.usuario_id}>
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
    </div>
  );
}
