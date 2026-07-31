import { Menu } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { PERFIL_LABELS } from '../../utils/constants';
import Avatar from '../ui/Avatar';
import NotificacoesBell from './NotificacoesBell';

const PAGE_TITLES = {
  dashboard:      'Dashboard',
  rotinas:        'Minhas Rotinas',
  acompanhamento: 'Acompanhamento do Time',
  comparativo_liderados: 'Comparativo Liderados',
  notificacoes: 'Notificações',
  pendencias:     'Pendências',
  usuarios:       'Gestão de Usuários',
  regionais:      'Regionais',
  atividades:     'Catálogo de Atividades',
  perfil:         'Meu Perfil',
  auditoria:      'Auditoria',
};

export default function Header({ activePage, onToggleMobile, onNavigate }) {
  const { currentUser } = useAuth();
  const title = PAGE_TITLES[activePage] || activePage;

  return (
    <header className="h-[56px] bg-white border-b border-gray-100 flex items-center justify-between px-6 shrink-0 z-30">
      {/* Left */}
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleMobile}
          className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors"
          aria-label="Abrir menu"
        >
          <Menu size={20} />
        </button>
        <div>
          <h1 className="text-base font-semibold text-gray-900">{title}</h1>
          <p className="text-xs text-gray-400">GC Comercial · Sistema Operacional</p>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        <NotificacoesBell onVerTodas={() => onNavigate?.('notificacoes')} />
        <div className="flex items-center gap-2.5">
          <Avatar src={currentUser?.foto_url} name={currentUser?.nome} size="sm" />
          <div className="hidden sm:block text-right">
            <div className="text-sm font-medium text-gray-800 leading-tight">{currentUser?.nome}</div>
            <div className="text-xs text-gray-400">{PERFIL_LABELS[currentUser?.perfil] || currentUser?.perfil}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
