import { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import AppLayout from './components/layout/AppLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import RotinasPage from './pages/RotinasPage';
import AcompanhamentoPage from './pages/AcompanhamentoPage';
import PendenciasPage from './pages/PendenciasPage';
import PendenciasAprovacaoPage from './pages/PendenciasAprovacaoPage';
import UsuariosPage from './pages/UsuariosPage';
import RegionaisPage from './pages/RegionaisPage';
import EmpreendimentosPage from './pages/EmpreendimentosPage';
import AtividadesPage from './pages/AtividadesPage';
import AuditoriaPage from './pages/AuditoriaPage';
import MetricasAprovacaoPage from './pages/MetricasAprovacaoPage';
import RelatoriosPreenchimentoPage from './pages/RelatoriosPreenchimentoPage';
import ComparativoLideradosPage from './pages/ComparativoLideradosPage';
import NotificacoesPage from './pages/NotificacoesPage';
import MeuPerfil from './pages/MeuPerfil';

const PAGES = {
  dashboard:            DashboardPage,
  rotinas:              RotinasPage,
  acompanhamento:       AcompanhamentoPage,
  pendencias:           PendenciasPage,
  pendencias_aprovacao: PendenciasAprovacaoPage,
  usuarios:             UsuariosPage,
  regionais:            RegionaisPage,
  empreendimentos:      EmpreendimentosPage,
  atividades:           AtividadesPage,
  perfil:               MeuPerfil,
  auditoria:            AuditoriaPage,
  metricas_aprovacao:   MetricasAprovacaoPage,
  relatorios:           RelatoriosPreenchimentoPage,
  comparativo_liderados: ComparativoLideradosPage,
  notificacoes:         NotificacoesPage,
};

// Role-based access
const PAGE_ROLES = {
  dashboard:            ['admin', 'sr'],
  acompanhamento:       ['admin', 'sr'],
  pendencias_aprovacao: ['admin', 'sr'],
  usuarios:             ['admin'],
  regionais:            ['admin'],
  empreendimentos:      ['admin'],
  atividades:           ['admin'],
  auditoria:            ['admin'],
  metricas_aprovacao:   ['admin'],
  relatorios:           ['admin'],
  comparativo_liderados: ['admin', 'sr'],
};

function AppContent() {
  const { currentUser, loading } = useAuth();
  
  // Initialize state based on user role
  const getDefaultPage = (user) => {
    if (!user) return 'dashboard';
    return ['admin', 'sr'].includes(user.perfil) ? 'dashboard' : 'rotinas';
  };

  const [activePage, setActivePage] = useState(() => getDefaultPage(currentUser));

  // Sync active page if user changes (e.g. login/logout in same tab)
  useEffect(() => {
    if (currentUser) {
      setActivePage(prev => {
        const roles = PAGE_ROLES[prev];
        if (roles && !roles.includes(currentUser.perfil)) {
          return getDefaultPage(currentUser);
        }
        return prev;
      });
    }
  }, [currentUser]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary-600 flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-sm text-gray-400">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!currentUser) return <LoginPage />;

  const navigate = (page) => {
    const roles = PAGE_ROLES[page];
    if (roles && !roles.includes(currentUser.perfil)) {
      // Redirect to appropriate default
      setActivePage(['admin', 'sr'].includes(currentUser.perfil) ? 'dashboard' : 'rotinas');
      return;
    }
    setActivePage(page);
  };

  const PageComponent = PAGES[activePage] || RotinasPage;

  return (
    <AppLayout activePage={activePage} onNavigate={navigate}>
      <PageComponent />
    </AppLayout>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </AuthProvider>
  );
}
