import { useState, useEffect, useCallback } from 'react';
import { Bell, CheckCheck, ExternalLink } from 'lucide-react';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import Button from '../components/ui/Button';
import { EmptyState, PageSpinner } from '../components/ui/Spinner';
import { fmtDatetime } from '../utils/constants';
import RotinaModal from '../components/shared/RotinaModal';

const FILTROS = [
  { value: '', label: 'Todas' },
  { value: '1', label: 'Não lidas' },
];

export default function NotificacoesPage() {
  const [notificacoes, setNotificacoes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [naoLidas, setNaoLidas] = useState('');
  const [rotinaAberta, setRotinaAberta] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    let url = '/api/notificacoes/?limite=100';
    if (naoLidas) url += `&nao_lidas=${naoLidas}`;
    const r = await apiFetch(url);
    if (r?.ok) setNotificacoes(r.data);
    setLoading(false);
  }, [naoLidas]);

  useEffect(() => { load(); }, [load]);

  const abrirAtividade = (n) => setRotinaAberta(n.rotina_id);

  const fecharRotina = () => {
    setRotinaAberta(null);
    load();
  };

  const marcarTodasLidas = async () => {
    const r = await apiFetch('/api/notificacoes/marcar-todas-lidas', { method: 'POST' });
    if (r?.ok) load();
  };

  const totalNaoLidas = notificacoes.filter(n => !n.lida).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1.5">
          {FILTROS.map(f => (
            <button
              key={f.value}
              onClick={() => setNaoLidas(f.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                naoLidas === f.value ? 'bg-primary-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {totalNaoLidas > 0 && (
          <Button variant="secondary" icon={CheckCheck} onClick={marcarTodasLidas} className="ml-auto">
            Marcar todas como lidas
          </Button>
        )}
      </div>

      {loading ? (
        <PageSpinner />
      ) : (
        <Card>
          {notificacoes.length === 0 ? (
            <EmptyState icon={Bell} title="Nenhuma notificação" description="Quando alguém te designar responsável por uma atividade, ela aparece aqui." />
          ) : (
            <div className="divide-y divide-gray-50">
              {notificacoes.map(n => (
                <button
                  key={n.id}
                  onClick={() => abrirAtividade(n)}
                  className={`w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors flex items-start gap-3 ${!n.lida ? 'bg-primary-50/40' : ''}`}
                >
                  {!n.lida && <span className="w-2 h-2 rounded-full bg-primary-500 mt-1.5 shrink-0" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-gray-800">{n.titulo}</span>
                      {!n.lida && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary-100 text-primary-700 shrink-0">Não lida</span>
                      )}
                    </div>
                    {n.mensagem && <p className="text-sm text-gray-500 mt-0.5">{n.mensagem}</p>}
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-gray-400">
                      <span>{fmtDatetime(n.criado_em)}</span>
                      {n.criado_por_nome && <span>Por {n.criado_por_nome}</span>}
                    </div>
                  </div>
                  <ExternalLink size={14} className="text-gray-300 shrink-0 mt-1" />
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      <RotinaModal rotinaId={rotinaAberta} onClose={fecharRotina} onSaved={fecharRotina} />
    </div>
  );
}
