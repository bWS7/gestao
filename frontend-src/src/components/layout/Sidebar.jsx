import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, ClipboardList, AlertCircle, Users, Map,
  BookOpen, Shield, LogOut, User, Activity, TrendingUp, Menu, Timer, FileBarChart, Building2, Users2, Bell
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { PERFIL_LABELS } from '../../utils/constants';
import Avatar from '../ui/Avatar';

const NAV_SECTIONS = {
  principal: {
    label: 'Principal',
    items: [
      { id: 'dashboard',            label: 'Dashboard',          icon: LayoutDashboard,  roles: ['admin', 'sr'] },
      { id: 'rotinas',              label: 'Minhas Rotinas',     icon: ClipboardList,    roles: null },
      { id: 'notificacoes',         label: 'Notificações',       icon: Bell,             roles: null },
      { id: 'pendencias',           label: 'Pendências',         icon: AlertCircle,      roles: null },
      { id: 'pendencias_aprovacao', label: 'Aprovações',         icon: Activity,         roles: ['admin', 'sr'] },
    ],
  },
  gestao: {
    label: 'Gestão',
    items: [
      { id: 'acompanhamento', label: 'Acompanhamento',   icon: TrendingUp,       roles: ['admin', 'sr'] },
      { id: 'comparativo_liderados', label: 'Comparativo Liderados', icon: Users2, roles: ['admin', 'sr'] },
    ],
  },
  admin: {
    label: 'Administração',
    items: [
      { id: 'usuarios',       label: 'Usuários',          icon: Users,            roles: ['admin'] },
      { id: 'regionais',      label: 'Regionais',         icon: Map,              roles: ['admin'] },
      { id: 'empreendimentos', label: 'Empreendimentos',  icon: Building2,        roles: ['admin'] },
      { id: 'atividades',     label: 'Catálogo',          icon: BookOpen,         roles: ['admin'] },
      { id: 'auditoria',          label: 'Auditoria',         icon: Shield,  roles: ['admin'] },
      { id: 'relatorios',         label: 'Relatórios',        icon: FileBarChart, roles: ['admin'] },
      { id: 'metricas_aprovacao', label: 'Tempo de Revisão',  icon: Timer,        roles: ['admin'] },
    ],
  },
};

function NavItem({ item, active, collapsed, onNavigate }) {
  const Icon = item.icon;
  return (
    <button
      onClick={() => onNavigate(item.id)}
      title={collapsed ? item.label : undefined}
      className={`
        relative group flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg text-xs font-medium
        transition-all duration-150
        ${active
          ? 'bg-primary-600 text-white shadow-sm'
          : 'text-gray-400 hover:bg-sidebar-hover hover:text-gray-200'
        }
      `}
    >
      <Icon size={16} className="shrink-0" />
      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{ opacity: 0, width: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden whitespace-nowrap"
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>
      {/* Tooltip when collapsed */}
      {collapsed && (
        <div className="absolute left-full ml-2.5 px-2.5 py-1.5 bg-gray-900 text-white text-xs rounded-lg
                        opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity duration-150
                        whitespace-nowrap z-50 shadow-lg border border-gray-700">
          {item.label}
        </div>
      )}
    </button>
  );
}

export default function Sidebar({ activePage, onNavigate, mobileOpen, onCloseMobile }) {
  const { currentUser, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  if (!currentUser) return null;

  const perfil = currentUser.perfil;
  const canAccess = (roles) => {
    if (!roles) return true;
    return roles.includes(perfil);
  };

  return (
    <>
      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            onClick={onCloseMobile}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside
        animate={{ width: collapsed ? 60 : 190 }}
        transition={{ duration: 0.22, ease: 'easeInOut' }}
        className={`
          fixed top-0 left-0 h-full z-50 bg-sidebar-bg flex flex-col overflow-x-hidden overflow-y-auto
          transition-transform duration-200
          lg:relative lg:translate-x-0 lg:z-auto
          [ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:display-none
          ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Logo / Toggle */}
        <div 
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center gap-3 px-4 py-3 border-b border-sidebar-border shrink-0 min-h-[56px] cursor-pointer hover:bg-sidebar-hover transition-colors"
        >
          <div className="shrink-0 w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center">
            <Menu size={18} className="text-white" />
          </div>
          <AnimatePresence>
            {!collapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="overflow-hidden"
              >
                <div className="text-white font-semibold text-[13px] whitespace-nowrap">GC Comercial</div>
                <div className="text-sidebar-text text-[10px] whitespace-nowrap">Gestão de Rotinas</div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* User info */}
        <div className="px-3 py-3 border-b border-sidebar-border shrink-0">
          <div className="flex items-center gap-3">
            <Avatar src={currentUser.foto_url} name={currentUser.nome} size="sm" />
            <AnimatePresence>
              {!collapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="overflow-hidden min-w-0"
                >
                  <div className="text-white text-[11px] font-medium truncate">{currentUser.nome}</div>
                  <div className="text-sidebar-text text-[10px] truncate">{PERFIL_LABELS[perfil] || perfil}</div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
          {Object.entries(NAV_SECTIONS).map(([sectionKey, section]) => {
            const visibleItems = section.items.filter(item => canAccess(item.roles));
            if (!visibleItems.length) return null;
            return (
              <div key={sectionKey}>
                <AnimatePresence>
                  {!collapsed && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-sidebar-label"
                    >
                      {section.label}
                    </motion.div>
                  )}
                </AnimatePresence>
                <div className="space-y-0.5">
                  {visibleItems.map(item => (
                    <NavItem
                      key={item.id}
                      item={item}
                      active={activePage === item.id}
                      collapsed={collapsed}
                      onNavigate={(page) => { 
                        onNavigate(page); 
                        onCloseMobile?.(); 
                      }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-2 py-3 border-t border-sidebar-border space-y-0.5 shrink-0">
          <NavItem
            item={{ id: 'perfil', label: 'Meu Perfil', icon: User }}
            active={activePage === 'perfil'}
            collapsed={collapsed}
            onNavigate={(page) => { onNavigate(page); onCloseMobile?.(); }}
          />
          <button
            onClick={logout}
            title={collapsed ? 'Sair' : undefined}
            className="relative group flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg text-xs font-medium
                       text-gray-400 hover:bg-red-500/10 hover:text-red-400 transition-all duration-150"
          >
            <LogOut size={16} className="shrink-0" />
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="whitespace-nowrap"
                >
                  Sair
                </motion.span>
              )}
            </AnimatePresence>
            {collapsed && (
              <div className="absolute left-full ml-2.5 px-2.5 py-1.5 bg-gray-900 text-white text-xs rounded-lg
                              opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 shadow-lg border border-gray-700">
                Sair
              </div>
            )}
          </button>
        </div>

      </motion.aside>
    </>
  );
}
