import { useState, useEffect, useCallback, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, CheckCheck } from 'lucide-react';
import { apiFetch } from '../../api/client';
import { fmtDatetime } from '../../utils/constants';
import RotinaModal from '../shared/RotinaModal';

const POLL_MS = 30000;

export default function NotificacoesBell({ onVerTodas }) {
  const [aberto, setAberto] = useState(false);
  const [contagem, setContagem] = useState(0);
  const [notificacoes, setNotificacoes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [rotinaAberta, setRotinaAberta] = useState(null);
  const ref = useRef(null);

  const carregarContagem = useCallback(async () => {
    const r = await apiFetch('/api/notificacoes/nao-lidas/contagem');
    if (r?.ok) setContagem(r.data.total);
  }, []);

  useEffect(() => {
    carregarContagem();
    const id = setInterval(carregarContagem, POLL_MS);
    return () => clearInterval(id);
  }, [carregarContagem]);

  useEffect(() => {
    function onClickFora(e) {
      if (ref.current && !ref.current.contains(e.target)) setAberto(false);
    }
    document.addEventListener('mousedown', onClickFora);
    return () => document.removeEventListener('mousedown', onClickFora);
  }, []);

  const abrirPainel = async () => {
    const vaiAbrir = !aberto;
    setAberto(vaiAbrir);
    if (vaiAbrir) {
      setLoading(true);
      const r = await apiFetch('/api/notificacoes/');
      if (r?.ok) setNotificacoes(r.data);
      setLoading(false);
    }
  };

  const abrirAtividade = (n) => {
    setAberto(false);
    setRotinaAberta(n.rotina_id);
  };

  const marcarTodasLidas = async () => {
    const r = await apiFetch('/api/notificacoes/marcar-todas-lidas', { method: 'POST' });
    if (r?.ok) {
      setContagem(0);
      setNotificacoes(prev => prev.map(n => ({ ...n, lida: true })));
    }
  };

  const fecharRotina = () => {
    setRotinaAberta(null);
    carregarContagem();
    apiFetch('/api/notificacoes/').then(r => { if (r?.ok) setNotificacoes(r.data); });
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={abrirPainel}
        className="relative p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors"
        aria-label="Notificações"
      >
        <Bell size={18} />
        {contagem > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-0.5 rounded-full bg-error text-white text-[10px] font-semibold flex items-center justify-center">
            {contagem > 9 ? '9+' : contagem}
          </span>
        )}
      </button>

      <AnimatePresence>
        {aberto && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 mt-2 w-80 bg-white rounded-xl border border-gray-100 shadow-lg z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h4 className="text-sm font-semibold text-gray-800">Notificações</h4>
              {contagem > 0 && (
                <button onClick={marcarTodasLidas} className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-800">
                  <CheckCheck size={13} /> Marcar todas como lidas
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {loading ? (
                <div className="py-8 text-center text-xs text-gray-400">Carregando...</div>
              ) : notificacoes.length === 0 ? (
                <div className="py-8 text-center text-xs text-gray-400">Nenhuma notificação.</div>
              ) : (
                notificacoes.map(n => (
                  <button
                    key={n.id}
                    onClick={() => abrirAtividade(n)}
                    className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors ${!n.lida ? 'bg-primary-50/40' : ''}`}
                  >
                    <div className="flex items-start gap-2">
                      {!n.lida && <span className="w-1.5 h-1.5 rounded-full bg-primary-500 mt-1.5 shrink-0" />}
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-gray-800 line-clamp-2">{n.titulo}</div>
                        {n.mensagem && <div className="text-[11px] text-gray-500 mt-0.5 line-clamp-2">{n.mensagem}</div>}
                        <div className="text-[10px] text-gray-400 mt-1">{fmtDatetime(n.criado_em)}</div>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
            <button
              onClick={() => { setAberto(false); onVerTodas?.(); }}
              className="w-full text-center py-2.5 text-xs font-medium text-primary-600 hover:bg-gray-50 border-t border-gray-100 transition-colors"
            >
              Ver todas as notificações
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <RotinaModal rotinaId={rotinaAberta} onClose={fecharRotina} onSaved={fecharRotina} />
    </div>
  );
}
