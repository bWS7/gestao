// ── GESTÃO COMERCIAL — MAIN APP ──
const API = '';
let currentUser = null;
let token = localStorage.getItem('gc_token') || null;

// ── AUTH ──
async function apiFetch(path, opts = {}) {
  const isFormData = opts.body instanceof FormData;
  const headers = { ...(isFormData ? {} : { 'Content-Type': 'application/json' }), ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); return null; }
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

async function login(email, senha) {
  const r = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, senha })
  });
  if (r && r.ok) {
    token = r.data.token;
    currentUser = r.data.usuario;
    localStorage.setItem('gc_token', token);
    localStorage.setItem('gc_user', JSON.stringify(currentUser));
    return true;
  }
  return r?.data?.erro || 'Erro ao fazer login';
}

function logout() {
  token = null;
  currentUser = null;
  localStorage.removeItem('gc_token');
  localStorage.removeItem('gc_user');
  showLogin();
}

// ── TOAST ──
function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

async function downloadExport(path, filename) {
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(API + path, { headers });
  if (!res.ok) {
    toast('Erro ao exportar relatório', 'error');
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function downloadCsvFromRows(filename, headers, rows) {
  const escape = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const csv = [headers.map(escape).join(','), ...rows.map(row => row.map(escape).join(','))].join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── NAVIGATION ──
function showLogin() {
  document.getElementById('login-screen').style.display = 'flex';
  document.querySelector('.app-layout').classList.remove('visible');
}

function showApp() {
  document.getElementById('login-screen').style.display = 'none';
  document.querySelector('.app-layout').classList.add('visible');
  renderSidebar();
  navigate(['admin', 'sr'].includes(currentUser?.perfil) ? 'dashboard' : 'rotinas');
}

function toggleSidebar() {
  const layout = document.querySelector('.app-layout');
  layout.classList.toggle('sidebar-collapsed');
  document.querySelector('.drawer-overlay')?.classList.toggle('show', !layout.classList.contains('sidebar-collapsed'));
}

function closeSidebar() {
  document.querySelector('.app-layout').classList.add('sidebar-collapsed');
  document.querySelector('.drawer-overlay')?.classList.remove('show');
}

function navigate(page) {
  if (page === 'dashboard' && !['admin', 'sr'].includes(currentUser?.perfil)) {
    page = 'rotinas';
  }
  if (page === 'acompanhamento' && !['admin', 'sr'].includes(currentUser?.perfil)) {
    page = 'rotinas';
  }
  if (page === 'auditoria' && currentUser?.perfil !== 'admin') {
    page = 'rotinas';
  }
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');
  document.getElementById('topbar-title').textContent = PAGE_TITLES[page] || page;
  PAGE_LOADERS[page]?.();
  closeSidebar();
}

const PAGE_TITLES = {
  dashboard: 'Dashboard',
  rotinas: 'Minhas Rotinas',
  acompanhamento: 'Acompanhamento do Time',
  usuarios: 'Usuários',
  regionais: 'Regionais',
  atividades: 'Catálogo de Atividades',
  pendencias: 'Pendências',
  perfil: 'Meu Perfil',
  auditoria: 'Auditoria'
};

// ── PERFIL LABELS ──
const PERFIL_LABELS = {
  admin: 'Administrador',
  sr: 'Superintendente',
  gv: 'Gerente de Vendas',
  cd: 'Coordenador de Produto',
  sp: 'Supervisor de Parceria'
};

const STATUS_LABELS = {
  nao_iniciada: 'Não Iniciada', em_andamento: 'Em Andamento',
  concluida: 'Concluída', nao_realizada: 'Não Realizada'
};

const PERIODO_LABELS = { semanal: 'Semanal', quinzenal: 'Quinzenal', mensal: 'Mensal' };

// ── SIDEBAR ──
function renderSidebar() {
  if (!currentUser) return;
  const u = currentUser;
  document.getElementById('user-name').textContent = u.nome;
  document.getElementById('user-role').textContent = PERFIL_LABELS[u.perfil] || u.perfil;
  document.getElementById('user-avatar').textContent = u.nome.charAt(0).toUpperCase();
  document.getElementById('topbar-user').textContent = `${u.nome} · ${PERFIL_LABELS[u.perfil] || u.perfil}`;

  const nav = document.getElementById('sidebar-nav');
  const isAdmin = u.perfil === 'admin';
  const canViewDashboard = ['admin', 'sr'].includes(u.perfil);
  const canViewTeam = ['admin', 'sr'].includes(u.perfil);

  let html = `
    <div class="nav-section">
      <div class="nav-section-label">Principal</div>
      ${canViewDashboard ? `
      <button class="nav-link" data-page="dashboard" onclick="navigate('dashboard')">
        Dashboard
      </button>` : ''}
      <button class="nav-link" data-page="rotinas" onclick="navigate('rotinas')">
        Minhas Rotinas
      </button>
      <button class="nav-link" data-page="pendencias" onclick="navigate('pendencias')">
        Pendências
      </button>
    </div>`;

  if (canViewTeam) {
    html += `
    <div class="nav-section">
      <div class="nav-section-label">Gestão</div>
      <button class="nav-link" data-page="acompanhamento" onclick="navigate('acompanhamento')">
        Acompanhamento
      </button>
    </div>`;
  }

  if (isAdmin) {
    html += `
    <div class="nav-section">
      <div class="nav-section-label">Administração</div>
      <button class="nav-link" data-page="usuarios" onclick="navigate('usuarios')">
        Usuários
      </button>
      <button class="nav-link" data-page="regionais" onclick="navigate('regionais')">
        Regionais
      </button>
      <button class="nav-link" data-page="atividades" onclick="navigate('atividades')">
        Catálogo de Atividades
      </button>
      <button class="nav-link" data-page="auditoria" onclick="navigate('auditoria')">
        Auditoria
      </button>
    </div>`;
  }

  nav.innerHTML = html;
}

// ══════════════════════════════════════
// ── DASHBOARD ──
// ══════════════════════════════════════
async function loadDashboard() {
  const wrap = document.getElementById('dashboard-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const periodo = document.getElementById('dash-periodo')?.value || 'semanal';
  const regional_id = document.getElementById('dash-regional')?.value || '';

  let url = `/api/rotinas/dashboard?periodo=${periodo}`;
  if (regional_id) url += `&regional_id=${regional_id}`;

  const r = await apiFetch(url);
  if (!r || !r.ok) { wrap.innerHTML = '<p class="text-muted">Erro ao carregar dashboard.</p>'; return; }
  const d = r.data;

  const pct = d.percentual_execucao;
  const pctColor = pct >= 80 ? '#38A169' : pct >= 50 ? '#E65100' : '#C62828';

  // Load regionais for filter if admin
  let regionalFilter = '';
  if (currentUser.perfil === 'admin') {
    const rr = await apiFetch('/api/regionais/?ativo=true');
    if (rr && rr.ok) {
      const opts = rr.data.map(r => `<option value="${r.id}">${r.nome}</option>`).join('');
      regionalFilter = `
        <select id="dash-regional" class="form-control form-select" onchange="loadDashboard()" style="width:160px">
          <option value="">Todas Regionais</option>${opts}
        </select>`;
    }
  }

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <select id="dash-periodo" class="form-control form-select" onchange="loadDashboard()" style="width:140px">
        <option value="semanal" ${periodo==='semanal'?'selected':''}>Semanal</option>
        <option value="quinzenal" ${periodo==='quinzenal'?'selected':''}>Quinzenal</option>
        <option value="mensal" ${periodo==='mensal'?'selected':''}>Mensal</option>
      </select>
      ${regionalFilter}
      <button class="btn btn-secondary btn-sm" onclick="exportDashboard()">Exportar CSV</button>
      <span class="text-muted" style="font-size:.8rem">
        ${fmtDate(d.periodo_inicio)} → ${fmtDate(d.periodo_fim)}
      </span>
    </div>

    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-label">% de Execução</div>
        <div class="stat-value">${pct}%</div>
        <div class="stat-sub">${d.concluidas} de ${d.total} atividades</div>
        <div class="stat-icon">%</div>
        <div class="progress-bar" style="margin-top:.75rem;background:rgba(255,255,255,.2)">
          <div class="progress-fill" style="width:${pct}%;background:rgba(255,255,255,.8)"></div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Concluídas</div>
        <div class="stat-value" style="color:#38A169">${d.concluidas}</div>
        <div class="stat-sub">de ${d.total} previstas</div>
        <div class="stat-icon">OK</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Não Realizadas</div>
        <div class="stat-value" style="color:var(--vermelho)">${d.nao_realizadas}</div>
        <div class="stat-sub">requerem plano de ação</div>
        <div class="stat-icon">!</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Em Andamento</div>
        <div class="stat-value" style="color:#E65100">${d.em_andamento}</div>
        <div class="stat-sub">+ ${d.nao_iniciadas} não iniciadas</div>
        <div class="stat-icon">...</div>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Por Perfil</div>
        </div>
        <div class="card-body">
          ${renderPorPerfil(d.por_perfil)}
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title">Ranking de Aderência</div>
        </div>
        <div class="card-body">
          ${renderRanking(d.ranking)}
        </div>
      </div>
    </div>

    ${currentUser.perfil === 'admin' ? `
    <div class="card action-panel">
      <div class="card-header">
        <div class="card-title">Gerar Rotinas do Período</div>
      </div>
      <div class="card-body">
        <span class="text-muted" style="font-size:.875rem">Gera automaticamente as atividades para todos os usuários ativos conforme o catálogo.</span>
        <button class="btn btn-primary btn-sm" style="white-space:nowrap" onclick="gerarRotinas()">Gerar Agora</button>
      </div>
    </div>` : ''}
    </div>
  `;
}

function renderPorPerfil(por_perfil) {
  if (!por_perfil || !Object.keys(por_perfil).length) return '<p class="text-muted text-center">Sem dados</p>';
  return Object.entries(por_perfil).map(([perfil, info]) => `
    <div style="margin-bottom:1rem">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem">
        <span class="badge badge-${perfil}">${PERFIL_LABELS[perfil] || perfil}</span>
        <span style="font-weight:700;font-size:.9rem">${info.percentual}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" style="width:${info.percentual}%"></div>
      </div>
      <div style="font-size:.72rem;color:var(--cinza-light);margin-top:.2rem">${info.concluidas}/${info.total} concluídas</div>
    </div>
  `).join('');
}

function renderRanking(ranking) {
  if (!ranking || !ranking.length) return '<p class="text-muted text-center">Sem dados</p>';
  return ranking.slice(0, 10).map((r, i) => {
    const cls = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
    return `
    <div class="ranking-item">
      <div class="rank-num ${cls}">${i + 1}</div>
      <div class="rank-info">
        <div class="rank-name">${r.nome}</div>
        <div class="rank-sub">${r.regional} · ${r.concluidas}/${r.total}</div>
      </div>
      <div class="rank-pct">${r.percentual}%</div>
    </div>`;
  }).join('');
}

async function gerarRotinas() {
  const r = await apiFetch('/api/rotinas/gerar', { method: 'POST', body: JSON.stringify({}) });
  if (r && r.ok) {
    toast(`${r.data.total} rotinas geradas com sucesso!`, 'success');
    loadDashboard();
  } else {
    toast('Erro ao gerar rotinas', 'error');
  }
}

function exportDashboard() {
  const periodo = document.getElementById('dash-periodo')?.value || 'semanal';
  const regionalId = document.getElementById('dash-regional')?.value || '';
  let url = `/api/rotinas/dashboard/export?periodo=${periodo}`;
  if (regionalId) url += `&regional_id=${regionalId}`;
  downloadExport(url, `dashboard_${periodo}.csv`);
}

// ══════════════════════════════════════
// ── ROTINAS ──
// ══════════════════════════════════════
async function loadRotinas() {
  const wrap = document.getElementById('rotinas-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const periodo = document.getElementById('rotinas-periodo')?.value || 'semanal';
  const status = document.getElementById('rotinas-status')?.value || '';

  let url = `/api/rotinas/?periodo=${periodo}&usuario_id=${currentUser.id}`;
  if (status) url += `&status=${status}`;

  const [r, aderenciaResp] = await Promise.all([
    apiFetch(url),
    apiFetch(`/api/rotinas/minha-aderencia?periodo=${periodo}`)
  ]);
  if (!r || !r.ok) { wrap.innerHTML = '<p class="text-muted">Erro ao carregar rotinas.</p>'; return; }

  const rotinas = r.data;
  const aderencia = aderenciaResp?.ok ? aderenciaResp.data : { percentual_execucao: 0, concluidas: 0, total: 0 };

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <select id="rotinas-periodo" class="form-control form-select" onchange="loadRotinas()" style="width:140px">
        <option value="semanal" ${periodo==='semanal'?'selected':''}>Semanal</option>
        <option value="quinzenal" ${periodo==='quinzenal'?'selected':''}>Quinzenal</option>
        <option value="mensal" ${periodo==='mensal'?'selected':''}>Mensal</option>
      </select>
      <select id="rotinas-status" class="form-control form-select" onchange="loadRotinas()" style="width:160px">
        <option value="">Todos os Status</option>
        <option value="nao_iniciada">Não Iniciada</option>
        <option value="em_andamento">Em Andamento</option>
        <option value="concluida">Concluída</option>
        <option value="nao_realizada">Não Realizada</option>
      </select>
      <button class="btn btn-secondary btn-sm" onclick="exportRotinas()">Exportar CSV</button>
    </div>
    <div class="stats-grid" style="grid-template-columns:1fr">
      <div class="stat-card">
        <div class="stat-label">Aderência Pessoal</div>
        <div class="stat-value" style="color:var(--vinho)">${aderencia.percentual_execucao}%</div>
        <div class="stat-sub">${aderencia.concluidas} de ${aderencia.total} atividades concluídas no período</div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:${aderencia.percentual_execucao}%"></div>
        </div>
      </div>
    </div>
    <div>
    ${rotinas.length === 0
      ? '<div class="empty-state"><div class="icon">--</div><p>Nenhuma rotina encontrada para este período.</p></div>'
      : rotinas.map(r => renderRotinaCard(r)).join('')
    }
    </div>
    </div>`;
}

function renderRotinaCard(r) {
  const obrig = r.atividade_obrigatoria ? 'Obrigatória' : 'Opcional';
  return `
  <div class="rotina-card ${r.status}" onclick="openRotinaModal(${r.id})">
    <div class="rotina-card-header">
      <div>
        <div class="rotina-name">${r.atividade_nome}</div>
        <div class="rotina-meta">
          <span class="badge badge-${r.periodicidade}">${PERIODO_LABELS[r.periodicidade]}</span>
          <span class="badge badge-${r.status}">${STATUS_LABELS[r.status]}</span>
          <span>${obrig}</span>
        </div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        <div style="font-size:.75rem;color:var(--cinza-light)">${fmtDate(r.periodo_inicio)} → ${fmtDate(r.periodo_fim)}</div>
        ${r.data_conclusao ? `<div style="font-size:.72rem;color:#38A169;margin-top:.2rem">Concluída em ${fmtDatetime(r.data_conclusao)}</div>` : ''}
      </div>
    </div>
    ${r.comentario ? `<div style="font-size:.8rem;color:var(--cinza);margin-top:.5rem">${r.comentario}</div>` : ''}
  </div>`;
}

async function openRotinaModal(id) {
  const [r, historicoResp] = await Promise.all([
    apiFetch(`/api/rotinas/${id}`),
    apiFetch(`/api/rotinas/${id}/historico`)
  ]);
  if (!r || !r.ok) return;
  const rotina = r.data;
  const historico = historicoResp?.ok ? historicoResp.data : [];

  const canEdit = currentUser.perfil === 'admin' || rotina.usuario_id === currentUser.id || currentUser.perfil === 'sr';

  document.getElementById('rotina-modal-title').textContent = rotina.atividade_nome;
  document.getElementById('rotina-modal-body').innerHTML = `
    <input type="hidden" id="rm-id" value="${rotina.id}">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:1.25rem">
      <div><div class="form-label">Periodicidade</div><span class="badge badge-${rotina.periodicidade}">${PERIODO_LABELS[rotina.periodicidade]}</span></div>
      <div><div class="form-label">Período</div><span style="font-size:.875rem">${fmtDate(rotina.periodo_inicio)} → ${fmtDate(rotina.periodo_fim)}</span></div>
      <div><div class="form-label">Usuário</div><span style="font-size:.875rem">${rotina.usuario_nome}</span></div>
      <div><div class="form-label">Tipo de Evidência</div><span style="font-size:.8rem;color:var(--cinza)">${rotina.tipo_evidencia || '—'}</span></div>
    </div>

    <div class="form-group">
      <label class="form-label">Status</label>
      <select id="rm-status" class="form-control form-select" ${!canEdit?'disabled':''}>
        <option value="nao_iniciada" ${rotina.status==='nao_iniciada'?'selected':''}>Não Iniciada</option>
        <option value="em_andamento" ${rotina.status==='em_andamento'?'selected':''}>Em Andamento</option>
        <option value="concluida" ${rotina.status==='concluida'?'selected':''}>Concluída</option>
        <option value="nao_realizada" ${rotina.status==='nao_realizada'?'selected':''}>Não Realizada</option>
      </select>
    </div>

    <div class="form-group">
      <label class="form-label">Comentário</label>
      <textarea id="rm-comentario" class="form-control" rows="2" placeholder="Observações sobre a execução..." ${!canEdit?'disabled':''}>${rotina.comentario || ''}</textarea>
    </div>

    ${['sr', 'gv', 'cd'].includes(rotina.perfil) ? `
    <div class="form-group">
      <label class="form-label">Plano da Semana</label>
      <textarea id="rm-plano-semana" class="form-control" rows="2" placeholder="Registre o plano da semana..." ${!canEdit?'disabled':''}>${rotina.plano_semana || ''}</textarea>
    </div>` : ''}

    ${rotina.perfil === 'cd' ? `
    <div class="form-grid cols-2">
      <div class="form-group">
        <label class="form-label">Checklist</label>
        <textarea id="rm-checklist" class="form-control" rows="3" placeholder="Checklist operacional do período..." ${!canEdit?'disabled':''}>${rotina.checklist || ''}</textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Relatório</label>
        <textarea id="rm-relatorio" class="form-control" rows="3" placeholder="Resumo do relatório do empreendimento..." ${!canEdit?'disabled':''}>${rotina.relatorio || ''}</textarea>
      </div>
    </div>` : ''}

    ${rotina.perfil === 'sp' ? `
    <div class="form-grid cols-2">
      <div class="form-group">
        <label class="form-label">Visitas / Ativações</label>
        <textarea id="rm-visitas" class="form-control" rows="3" placeholder="Registre as visitas e ativações realizadas..." ${!canEdit?'disabled':''}>${rotina.visitas_ativacoes || ''}</textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Resultados por Visita</label>
        <textarea id="rm-resultados" class="form-control" rows="3" placeholder="Resultados gerados por visita..." ${!canEdit?'disabled':''}>${rotina.resultados_visita || ''}</textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Carteira Ativa</label>
        <textarea id="rm-carteira" class="form-control" rows="3" placeholder="Acompanhe a carteira ativa..." ${!canEdit?'disabled':''}>${rotina.carteira_ativa || ''}</textarea>
      </div>
      <div class="form-group">
        <label class="form-label">Metas do Canal</label>
        <textarea id="rm-metas" class="form-control" rows="3" placeholder="Registre e acompanhe as metas do canal..." ${!canEdit?'disabled':''}>${rotina.metas_canal || ''}</textarea>
      </div>
    </div>` : ''}

    <div id="rm-justificativa-wrap" class="form-group" style="${rotina.status!=='nao_realizada'&&rotina.status!=='em_andamento'?'display:none':''}">
      <label class="form-label">Justificativa</label>
      <textarea id="rm-justificativa" class="form-control" rows="2" placeholder="Por que não foi realizada?" ${!canEdit?'disabled':''}>${rotina.justificativa || ''}</textarea>
    </div>

    <div id="rm-acao-wrap" class="form-group" style="${rotina.status!=='nao_realizada'?'display:none':''}">
      <label class="form-label">Ação Corretiva</label>
      <textarea id="rm-acao" class="form-control" rows="2" placeholder="O que será feito para corrigir?" ${!canEdit?'disabled':''}>${rotina.acao_corretiva || ''}</textarea>
    </div>

    <div id="rm-plano-wrap" class="form-grid cols-2" style="${rotina.status!=='nao_realizada'?'display:none':''}">
      <div class="form-group">
        <label class="form-label">Responsável pela ação</label>
        <input type="text" id="rm-responsavel" class="form-control" value="${rotina.responsavel_acao || ''}" ${!canEdit?'disabled':''}>
      </div>
      <div class="form-group">
        <label class="form-label">Novo prazo</label>
        <input type="date" id="rm-novo-prazo" class="form-control" value="${rotina.novo_prazo || ''}" ${!canEdit?'disabled':''}>
      </div>
    </div>

    <div class="divider"></div>
    <h4 style="font-size:.9rem;font-weight:700;margin-bottom:.75rem">Evidências e anexos</h4>
    <div id="rm-evidencias-list">${renderEvidencias(rotina, canEdit)}</div>
    ${canEdit ? `
    <div class="form-group mt-2">
      <input type="file" id="rm-evidencia-arquivo" class="form-control">
    </div>
    <button class="btn btn-secondary btn-sm" type="button" onclick="uploadEvidencia(${rotina.id})">Anexar Evidência</button>` : ''}

    <div class="divider"></div>
    <h4 style="font-size:.9rem;font-weight:700;margin-bottom:.75rem">Histórico e auditoria</h4>
    <div id="rm-historico-list">${renderHistoricoRotina(historico)}</div>

    ${rotina.data_conclusao ? `<div class="alert alert-success" style="margin-top:.5rem">Concluída em ${fmtDatetime(rotina.data_conclusao)}</div>` : ''}
  `;

  // toggle justificativa
  document.getElementById('rm-status')?.addEventListener('change', function() {
    const s = this.value;
    document.getElementById('rm-justificativa-wrap').style.display =
      (s === 'nao_realizada' || s === 'em_andamento') ? '' : 'none';
    document.getElementById('rm-acao-wrap').style.display =
      s === 'nao_realizada' ? '' : 'none';
    document.getElementById('rm-plano-wrap').style.display =
      s === 'nao_realizada' ? '' : 'none';
  });

  document.getElementById('rm-save-btn').style.display = canEdit ? '' : 'none';
  openModal('rotina-modal');
}

async function saveRotina() {
  const id = document.getElementById('rm-id').value;
  const payload = {
    status: document.getElementById('rm-status').value,
    comentario: document.getElementById('rm-comentario').value,
    justificativa: document.getElementById('rm-justificativa')?.value || '',
    acao_corretiva: document.getElementById('rm-acao')?.value || '',
    responsavel_acao: document.getElementById('rm-responsavel')?.value || '',
    novo_prazo: document.getElementById('rm-novo-prazo')?.value || null,
    checklist: document.getElementById('rm-checklist')?.value || '',
    relatorio: document.getElementById('rm-relatorio')?.value || '',
    plano_semana: document.getElementById('rm-plano-semana')?.value || '',
    visitas_ativacoes: document.getElementById('rm-visitas')?.value || '',
    resultados_visita: document.getElementById('rm-resultados')?.value || '',
    carteira_ativa: document.getElementById('rm-carteira')?.value || '',
    metas_canal: document.getElementById('rm-metas')?.value || ''
  };
  if (payload.status === 'nao_realizada' && (!payload.justificativa || !payload.acao_corretiva)) {
    toast('Preencha a justificativa e o plano de ação', 'error');
    return;
  }
  const r = await apiFetch(`/api/rotinas/${id}`, {
    method: 'PUT', body: JSON.stringify(payload)
  });
  if (r && r.ok) {
    toast('Rotina atualizada!', 'success');
    closeModal('rotina-modal');
    loadRotinas();
    if (['admin', 'sr'].includes(currentUser.perfil)) loadDashboard();
  } else {
    toast('Erro ao salvar', 'error');
  }
}

function renderEvidencias(rotina, canEdit) {
  if (!rotina.evidencias?.length) return '<p class="text-muted">Nenhuma evidência anexada.</p>';
  return rotina.evidencias.map(e => `
    <div class="chip" style="justify-content:space-between;width:100%;margin-bottom:.5rem">
      <a href="${e.url}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none;overflow:hidden;text-overflow:ellipsis">${e.nome_arquivo}</a>
      ${canEdit ? `<button class="btn btn-ghost btn-sm" type="button" onclick="deleteEvidencia(${e.id}, ${rotina.id})">Excluir</button>` : ''}
    </div>
  `).join('');
}

function renderHistoricoRotina(historico) {
  if (!historico?.length) return '<p class="text-muted">Nenhum histórico registrado.</p>';
  return historico.map(h => `
    <div style="padding:.65rem 0;border-bottom:1px solid #F0F0F0">
      <div style="font-size:.8rem;font-weight:600">${(h.acao || '').replace(/_/g, ' ')}</div>
      <div style="font-size:.75rem;color:var(--cinza-light)">${h.usuario_nome || 'Sistema'} · ${fmtDatetime(h.criado_em)}</div>
      <div style="font-size:.78rem;color:var(--cinza)">${h.observacao || 'Sem observações'}</div>
    </div>
  `).join('');
}

async function uploadEvidencia(rotinaId) {
  const arquivo = document.getElementById('rm-evidencia-arquivo')?.files?.[0];
  if (!arquivo) {
    toast('Selecione um arquivo para anexar', 'error');
    return;
  }
  const form = new FormData();
  form.append('arquivo', arquivo);
  const r = await apiFetch(`/api/rotinas/${rotinaId}/evidencias`, { method: 'POST', body: form });
  if (r && r.ok) {
    toast('Evidência anexada!', 'success');
    openRotinaModal(rotinaId);
  } else {
    toast(r?.data?.erro || 'Erro ao anexar evidência', 'error');
  }
}

async function deleteEvidencia(eid, rotinaId) {
  if (!confirm('Deseja remover esta evidência?')) return;
  const r = await apiFetch(`/api/rotinas/evidencias/${eid}`, { method: 'DELETE' });
  if (r && r.ok) {
    toast('Evidência removida!', 'success');
    openRotinaModal(rotinaId);
  } else {
    toast(r?.data?.erro || 'Erro ao remover evidência', 'error');
  }
}

function exportRotinas() {
  const periodo = document.getElementById('rotinas-periodo')?.value || 'semanal';
  const status = document.getElementById('rotinas-status')?.value || '';
  let url = `/api/rotinas/export?periodo=${periodo}`;
  if (status) url += `&status=${status}`;
  downloadExport(url, `rotinas_${periodo}.csv`);
}

// ══════════════════════════════════════
// ── ACOMPANHAMENTO ──
// ══════════════════════════════════════
async function loadAcompanhamento() {
  const wrap = document.getElementById('acomp-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const periodo = document.getElementById('acomp-periodo')?.value || 'semanal';
  const usuario_id = document.getElementById('acomp-usuario')?.value || '';
  const status = document.getElementById('acomp-status')?.value || '';

  let url = `/api/rotinas/?periodo=${periodo}`;
  if (usuario_id) url += `&usuario_id=${usuario_id}`;
  if (status) url += `&status=${status}`;

  // Load users for filter
  const ur = await apiFetch('/api/usuarios/?status=ativo');
  const usuariosOpts = ur?.ok ? ur.data.filter(u => u.id !== currentUser.id)
    .map(u => `<option value="${u.id}" ${usuario_id==u.id?'selected':''}>${u.nome} (${PERFIL_LABELS[u.perfil]||u.perfil})</option>`).join('') : '';

  const r = await apiFetch(url);
  const rotinas = r?.ok ? r.data : [];

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <select id="acomp-periodo" class="form-control form-select" onchange="loadAcompanhamento()" style="width:140px">
        <option value="semanal">Semanal</option>
        <option value="quinzenal">Quinzenal</option>
        <option value="mensal">Mensal</option>
      </select>
      <select id="acomp-usuario" class="form-control form-select" onchange="loadAcompanhamento()" style="width:200px">
        <option value="">Todos os Usuários</option>${usuariosOpts}
      </select>
      <select id="acomp-status" class="form-control form-select" onchange="loadAcompanhamento()" style="width:160px">
        <option value="">Todos os Status</option>
        <option value="nao_iniciada">Não Iniciada</option>
        <option value="em_andamento">Em Andamento</option>
        <option value="concluida">Concluída</option>
        <option value="nao_realizada">Não Realizada</option>
      </select>
      <button class="btn btn-secondary btn-sm" onclick="exportAcompanhamento()">Exportar CSV</button>
    </div>

    <div class="card">
      <div class="card-body" style="padding:0">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Usuário</th>
                <th>Atividade</th>
                <th>Periodicidade</th>
                <th>Período</th>
                <th>Status</th>
                <th>Conclusão</th>
                <th>Ação</th>
              </tr>
            </thead>
            <tbody>
              ${rotinas.length === 0 ? `<tr><td colspan="7" class="text-center text-muted" style="padding:2rem">Nenhuma rotina encontrada</td></tr>` :
                rotinas.map(r => `
                  <tr>
                    <td><strong>${r.usuario_nome}</strong></td>
                    <td>${r.atividade_nome}</td>
                    <td><span class="badge badge-${r.periodicidade}">${PERIODO_LABELS[r.periodicidade]}</span></td>
                    <td style="font-size:.8rem;color:var(--cinza-light)">${fmtDate(r.periodo_inicio)}</td>
                    <td><span class="badge badge-${r.status}">${STATUS_LABELS[r.status]}</span></td>
                    <td style="font-size:.8rem">${r.data_conclusao ? fmtDatetime(r.data_conclusao) : '—'}</td>
                    <td><button class="btn btn-ghost btn-sm btn-icon" onclick="openRotinaModal(${r.id})" title="Visualizar">Ver</button></td>
                  </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </div>`;
}

function exportAcompanhamento() {
  const periodo = document.getElementById('acomp-periodo')?.value || 'semanal';
  const usuarioId = document.getElementById('acomp-usuario')?.value || '';
  const status = document.getElementById('acomp-status')?.value || '';
  let url = `/api/rotinas/export?periodo=${periodo}`;
  if (usuarioId) url += `&usuario_id=${usuarioId}`;
  if (status) url += `&status=${status}`;
  downloadExport(url, `acompanhamento_${periodo}.csv`);
}

// ══════════════════════════════════════
// ── PENDÊNCIAS ──
// ══════════════════════════════════════
async function loadPendencias() {
  const wrap = document.getElementById('pendencias-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const r = await apiFetch('/api/rotinas/pendencias');
  const pendencias = r?.ok ? r.data : [];

  wrap.innerHTML = `<div class="analytics-page">` + (pendencias.length === 0
    ? '<div class="empty-state"><div class="icon">--</div><p>Nenhuma pendência encontrada.</p></div>'
    : `<div class="card"><div class="card-body" style="padding:0"><div class="table-wrap"><table>
      <thead><tr><th>Usuário</th><th>Atividade</th><th>Período Limite</th><th>Status</th><th>Justificativa</th><th>Ação</th></tr></thead>
      <tbody>${pendencias.map(r => `
        <tr>
          <td><strong>${r.usuario_nome}</strong></td>
          <td>${r.atividade_nome} ${r.atividade_obrigatoria ? '<span style="color:var(--vermelho)">★</span>' : ''}</td>
          <td style="color:var(--vermelho);font-weight:600;font-size:.85rem">${fmtDate(r.periodo_fim)}</td>
          <td><span class="badge badge-${r.status}">${STATUS_LABELS[r.status]}</span></td>
          <td style="font-size:.8rem;color:var(--cinza)">${r.justificativa || '—'}</td>
          <td><button class="btn btn-ghost btn-sm btn-icon" onclick="openRotinaModal(${r.id})" title="Registrar">Abrir</button></td>
        </tr>`).join('')}
      </tbody></table></div></div></div>`) + `</div>`;
}

// ══════════════════════════════════════
// ── USUÁRIOS ──
// ══════════════════════════════════════
async function loadUsuarios() {
  const wrap = document.getElementById('usuarios-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const perfil = document.getElementById('u-perfil')?.value || '';
  const status = document.getElementById('u-status')?.value || '';

  let url = '/api/usuarios/?';
  if (perfil) url += `perfil=${perfil}&`;
  if (status) url += `status=${status}`;

  const [ur, rr] = await Promise.all([apiFetch(url), apiFetch('/api/regionais/')]);
  const usuarios = ur?.ok ? ur.data : [];
  const regionais = rr?.ok ? rr.data : [];
  const regMap = Object.fromEntries(regionais.map(r => [r.id, r.nome]));

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <select id="u-perfil" class="form-control form-select" onchange="loadUsuarios()" style="width:160px">
        <option value="">Todos os Perfis</option>
        ${Object.entries(PERFIL_LABELS).map(([v,l]) => `<option value="${v}">${l}</option>`).join('')}
      </select>
      <select id="u-status" class="form-control form-select" onchange="loadUsuarios()" style="width:130px">
        <option value="">Todos</option>
        <option value="ativo">Ativo</option>
        <option value="inativo">Inativo</option>
        <option value="bloqueado">Bloqueado</option>
      </select>
      <button class="btn btn-primary btn-sm" onclick="openUsuarioModal()">+ Novo Usuário</button>
    </div>
    <div class="card"><div class="card-body" style="padding:0"><div class="table-wrap"><table>
      <thead><tr><th>Nome</th><th>Email</th><th>Perfil</th><th>Regional</th><th>Status</th><th>Ações</th></tr></thead>
      <tbody>${usuarios.length === 0 ? `<tr><td colspan="6" class="text-center text-muted" style="padding:2rem">Nenhum usuário encontrado</td></tr>` :
        usuarios.map(u => `<tr>
          <td><strong>${u.nome}</strong></td>
          <td style="color:var(--cinza)">${u.email}</td>
          <td><span class="badge badge-${u.perfil}">${PERFIL_LABELS[u.perfil]||u.perfil}</span></td>
          <td>${regMap[u.regional_id] || '—'}</td>
          <td><span class="badge badge-${u.status}">${u.status}</span></td>
          <td style="display:flex;gap:.25rem">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openUsuarioModal(${JSON.stringify(u).replace(/"/g,'&quot;')})" title="Editar">Editar</button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="toggleUsuarioStatus(${u.id},'${u.status}')" title="Alterar status">Status</button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="deleteUsuario(${u.id})" title="Excluir">Excluir</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table></div></div></div>
    </div>`;
}

async function openUsuarioModal(u = null) {
  const rr = await apiFetch('/api/regionais/?ativo=true');
  const regionais = rr?.ok ? rr.data : [];
  const ur = await apiFetch('/api/usuarios/');
  const usuarios = ur?.ok ? ur.data : [];

  document.getElementById('u-modal-title').textContent = u ? 'Editar Usuário' : 'Novo Usuário';
  document.getElementById('u-modal-body').innerHTML = `
    <input type="hidden" id="um-id" value="${u?.id || ''}">
    <div class="form-grid cols-2">
      <div class="form-group">
        <label class="form-label">Nome Completo *</label>
        <input type="text" id="um-nome" class="form-control" value="${u?.nome||''}" required>
      </div>
      <div class="form-group">
        <label class="form-label">Email *</label>
        <input type="email" id="um-email" class="form-control" value="${u?.email||''}">
      </div>
      <div class="form-group">
        <label class="form-label">Perfil *</label>
        <select id="um-perfil" class="form-control form-select">
          ${Object.entries(PERFIL_LABELS).map(([v,l]) => `<option value="${v}" ${u?.perfil===v?'selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Regional</label>
        <select id="um-regional" class="form-control form-select">
          <option value="">Nenhuma</option>
          ${regionais.map(r => `<option value="${r.id}" ${u?.regional_id===r.id?'selected':''}>${r.nome}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Supervisor</label>
        <select id="um-supervisor" class="form-control form-select">
          <option value="">Nenhum</option>
          ${usuarios.filter(uu => uu.id !== u?.id).map(uu => `<option value="${uu.id}" ${u?.supervisor_id===uu.id?'selected':''}>${uu.nome}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Status</label>
        <select id="um-status" class="form-control form-select">
          <option value="ativo" ${!u||u.status==='ativo'?'selected':''}>Ativo</option>
          <option value="inativo" ${u?.status==='inativo'?'selected':''}>Inativo</option>
          <option value="bloqueado" ${u?.status==='bloqueado'?'selected':''}>Bloqueado</option>
        </select>
      </div>
    </div>
    ${!u ? `<div class="form-group"><label class="form-label">Senha Inicial</label>
      <input type="password" id="um-senha" class="form-control" placeholder="Mínimo 6 caracteres (padrão: 123456)"></div>` : ''}
  `;
  openModal('usuario-modal');
}

async function saveUsuario() {
  const id = document.getElementById('um-id').value;
  const payload = {
    nome: document.getElementById('um-nome').value,
    email: document.getElementById('um-email').value,
    perfil: document.getElementById('um-perfil').value,
    regional_id: document.getElementById('um-regional').value || null,
    supervisor_id: document.getElementById('um-supervisor').value || null,
    status: document.getElementById('um-status').value
  };
  const senha = document.getElementById('um-senha')?.value;
  if (senha) payload.senha = senha;

  const method = id ? 'PUT' : 'POST';
  const url = id ? `/api/usuarios/${id}` : '/api/usuarios/';
  const r = await apiFetch(url, { method, body: JSON.stringify(payload) });

  if (r && r.ok) {
    toast(id ? 'Usuário atualizado!' : 'Usuário criado!', 'success');
    closeModal('usuario-modal');
    loadUsuarios();
  } else {
    toast(r?.data?.erro || 'Erro ao salvar', 'error');
  }
}

async function toggleUsuarioStatus(id, statusAtual) {
  const novoStatus = statusAtual === 'ativo' ? 'inativo' : 'ativo';
  const r = await apiFetch(`/api/usuarios/${id}`, {
    method: 'PUT', body: JSON.stringify({ status: novoStatus })
  });
  if (r && r.ok) { toast(`Status alterado para ${novoStatus}`, 'success'); loadUsuarios(); }
  else toast('Erro ao alterar status', 'error');
}

async function deleteUsuario(id) {
  if (!confirm('Deseja inativar este usuário?')) return;
  const r = await apiFetch(`/api/usuarios/${id}`, { method: 'DELETE' });
  if (r && r.ok) {
    toast('Usuário inativado!', 'success');
    loadUsuarios();
  } else {
    toast(r?.data?.erro || 'Erro ao excluir usuário', 'error');
  }
}

// ══════════════════════════════════════
// ── REGIONAIS ──
// ══════════════════════════════════════
async function loadRegionais() {
  const wrap = document.getElementById('regionais-content');
  wrap.innerHTML = `<div class="spinner"></div>`;
  const r = await apiFetch('/api/regionais/');
  const regionais = r?.ok ? r.data : [];

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <button class="btn btn-primary btn-sm" onclick="openRegionalModal()">+ Nova Regional</button>
    </div>
    <div class="card"><div class="card-body" style="padding:0"><div class="table-wrap"><table>
      <thead><tr><th>Nome</th><th>Descrição</th><th>Status</th><th>Criado em</th><th>Ações</th></tr></thead>
      <tbody>${regionais.length === 0 ? `<tr><td colspan="5" class="text-center text-muted" style="padding:2rem">Nenhuma regional cadastrada</td></tr>` :
        regionais.map(r => `<tr>
          <td><strong>${r.nome}</strong></td>
          <td style="color:var(--cinza)">${r.descricao||'—'}</td>
          <td><span class="badge badge-${r.ativo?'ativo':'inativo'}">${r.ativo?'Ativa':'Inativa'}</span></td>
          <td style="font-size:.8rem;color:var(--cinza-light)">${fmtDate(r.criado_em)}</td>
          <td style="display:flex;gap:.25rem">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openRegionalModal(${JSON.stringify(r).replace(/"/g,'&quot;')})" title="Editar">Editar</button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="toggleRegional(${r.id},${r.ativo})" title="Alterar status">Status</button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="deleteRegional(${r.id})" title="Excluir">Excluir</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table></div></div></div>
    </div>`;
}

async function openRegionalModal(r = null) {
  document.getElementById('reg-modal-title').textContent = r ? 'Editar Regional' : 'Nova Regional';
  document.getElementById('reg-modal-body').innerHTML = `
    <input type="hidden" id="rm2-id" value="${r?.id||''}">
    <div class="form-group"><label class="form-label">Nome *</label>
      <input type="text" id="rm2-nome" class="form-control" value="${r?.nome||''}"></div>
    <div class="form-group"><label class="form-label">Descrição</label>
      <textarea id="rm2-descricao" class="form-control" rows="2">${r?.descricao||''}</textarea></div>
    ${r ? `<div class="form-group"><label class="form-label">Status</label>
      <select id="rm2-ativo" class="form-control form-select">
        <option value="true" ${r.ativo?'selected':''}>Ativa</option>
        <option value="false" ${!r.ativo?'selected':''}>Inativa</option>
      </select></div>` : ''}
  `;
  openModal('regional-modal');
}

async function saveRegional() {
  const id = document.getElementById('rm2-id').value;
  const payload = {
    nome: document.getElementById('rm2-nome').value,
    descricao: document.getElementById('rm2-descricao').value
  };
  const ativoEl = document.getElementById('rm2-ativo');
  if (ativoEl) payload.ativo = ativoEl.value === 'true';

  const method = id ? 'PUT' : 'POST';
  const url = id ? `/api/regionais/${id}` : '/api/regionais/';
  const r = await apiFetch(url, { method, body: JSON.stringify(payload) });

  if (r && r.ok) {
    toast(id ? 'Regional atualizada!' : 'Regional criada!', 'success');
    closeModal('regional-modal');
    loadRegionais();
  } else {
    toast(r?.data?.erro || 'Erro ao salvar', 'error');
  }
}

async function toggleRegional(id, ativo) {
  const r = await apiFetch(`/api/regionais/${id}`, {
    method: 'PUT', body: JSON.stringify({ ativo: !ativo })
  });
  if (r && r.ok) { toast('Status alterado', 'success'); loadRegionais(); }
}

async function deleteRegional(id) {
  if (!confirm('Deseja inativar esta regional?')) return;
  const r = await apiFetch(`/api/regionais/${id}`, { method: 'DELETE' });
  if (r && r.ok) {
    toast('Regional inativada!', 'success');
    loadRegionais();
  } else {
    toast(r?.data?.erro || 'Erro ao excluir regional', 'error');
  }
}

// ══════════════════════════════════════
// ── ATIVIDADES CATÁLOGO ──
// ══════════════════════════════════════
async function loadAtividades() {
  const wrap = document.getElementById('atividades-content');
  wrap.innerHTML = `<div class="spinner"></div>`;

  const perfil = document.getElementById('at-perfil')?.value || '';
  const periodo = document.getElementById('at-periodo')?.value || '';

  let url = '/api/atividades/?ativo=true';
  if (perfil) url += `&perfil=${perfil}`;
  if (periodo) url += `&periodicidade=${periodo}`;

  const r = await apiFetch(url);
  const atividades = r?.ok ? r.data : [];

  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="filter-bar">
      <select id="at-perfil" class="form-control form-select" onchange="loadAtividades()" style="width:170px">
        <option value="">Todos os Perfis</option>
        ${Object.entries(PERFIL_LABELS).filter(([v]) => v !== 'admin')
          .map(([v,l]) => `<option value="${v}">${l}</option>`).join('')}
      </select>
      <select id="at-periodo" class="form-control form-select" onchange="loadAtividades()" style="width:140px">
        <option value="">Todas</option>
        <option value="semanal">Semanal</option>
        <option value="quinzenal">Quinzenal</option>
        <option value="mensal">Mensal</option>
      </select>
      <button class="btn btn-primary btn-sm" onclick="openAtividadeModal()">+ Nova Atividade</button>
      <button class="btn btn-secondary btn-sm" onclick="exportAtividades()">Exportar CSV</button>
    </div>
    <div class="card"><div class="card-body" style="padding:0"><div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Nome</th><th>Perfil</th><th>Periodicidade</th><th>Obrigatória</th><th>Evidência</th><th>Ações</th></tr></thead>
      <tbody>${atividades.length === 0 ? `<tr><td colspan="7" class="text-center text-muted" style="padding:2rem">Nenhuma atividade encontrada</td></tr>` :
        atividades.map(a => `<tr>
          <td style="color:var(--cinza-light)">${a.ordem}</td>
          <td><strong>${a.nome}</strong><div style="font-size:.75rem;color:var(--cinza-light)">${a.descricao||''}</div></td>
          <td><span class="badge badge-${a.perfil}">${PERFIL_LABELS[a.perfil]||a.perfil}</span></td>
          <td><span class="badge badge-${a.periodicidade}">${PERIODO_LABELS[a.periodicidade]}</span></td>
          <td>${a.obrigatoria ? 'Sim' : 'Não'}</td>
          <td style="font-size:.8rem;color:var(--cinza)">${a.tipo_evidencia||'—'}</td>
          <td style="display:flex;gap:.25rem">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="openAtividadeModal(${JSON.stringify(a).replace(/"/g,'&quot;')})" title="Editar">Editar</button>
            <button class="btn btn-ghost btn-sm btn-icon" onclick="deleteAtividade(${a.id})" title="Excluir">Excluir</button>
          </td>
        </tr>`).join('')}
      </tbody>
    </table></div></div></div>
    </div>`;
}

async function openAtividadeModal(a = null) {
  document.getElementById('at-modal-title').textContent = a ? 'Editar Atividade' : 'Nova Atividade';
  document.getElementById('at-modal-body').innerHTML = `
    <input type="hidden" id="atm-id" value="${a?.id||''}">
    <div class="form-group"><label class="form-label">Nome *</label>
      <input type="text" id="atm-nome" class="form-control" value="${a?.nome||''}"></div>
    <div class="form-group"><label class="form-label">Descrição</label>
      <textarea id="atm-descricao" class="form-control" rows="2">${a?.descricao||''}</textarea></div>
    <div class="form-grid cols-2">
      <div class="form-group"><label class="form-label">Perfil *</label>
        <select id="atm-perfil" class="form-control form-select">
          ${['sr','gv','cd','sp'].map(p => `<option value="${p}" ${a?.perfil===p?'selected':''}>${PERFIL_LABELS[p]}</option>`).join('')}
        </select></div>
      <div class="form-group"><label class="form-label">Periodicidade *</label>
        <select id="atm-periodicidade" class="form-control form-select">
          <option value="semanal" ${a?.periodicidade==='semanal'?'selected':''}>Semanal</option>
          <option value="quinzenal" ${a?.periodicidade==='quinzenal'?'selected':''}>Quinzenal</option>
          <option value="mensal" ${a?.periodicidade==='mensal'?'selected':''}>Mensal</option>
        </select></div>
      <div class="form-group"><label class="form-label">Obrigatória</label>
        <select id="atm-obrigatoria" class="form-control form-select">
          <option value="true" ${a?.obrigatoria!==false?'selected':''}>Sim</option>
          <option value="false" ${a?.obrigatoria===false?'selected':''}>Não</option>
        </select></div>
      <div class="form-group"><label class="form-label">Ordem</label>
        <input type="number" id="atm-ordem" class="form-control" value="${a?.ordem||0}"></div>
    </div>
    <div class="form-group"><label class="form-label">Tipo de Evidência</label>
      <input type="text" id="atm-evidencia" class="form-control" value="${a?.tipo_evidencia||''}" placeholder="Ex: Print do painel, Ata de reunião..."></div>
    <div class="form-group"><label class="form-label">Indicador Relacionado</label>
      <input type="text" id="atm-indicador" class="form-control" value="${a?.indicador||''}"></div>
  `;
  openModal('atividade-modal');
}

async function saveAtividade() {
  const id = document.getElementById('atm-id').value;
  const payload = {
    nome: document.getElementById('atm-nome').value,
    descricao: document.getElementById('atm-descricao').value,
    perfil: document.getElementById('atm-perfil').value,
    periodicidade: document.getElementById('atm-periodicidade').value,
    obrigatoria: document.getElementById('atm-obrigatoria').value === 'true',
    ordem: parseInt(document.getElementById('atm-ordem').value) || 0,
    tipo_evidencia: document.getElementById('atm-evidencia').value,
    indicador: document.getElementById('atm-indicador').value
  };

  const method = id ? 'PUT' : 'POST';
  const url = id ? `/api/atividades/${id}` : '/api/atividades/';
  const r = await apiFetch(url, { method, body: JSON.stringify(payload) });

  if (r && r.ok) {
    toast(id ? 'Atividade atualizada!' : 'Atividade criada!', 'success');
    closeModal('atividade-modal');
    loadAtividades();
  } else {
    toast(r?.data?.erro || 'Erro ao salvar', 'error');
  }
}

async function exportAtividades() {
  const perfil = document.getElementById('at-perfil')?.value || '';
  const periodo = document.getElementById('at-periodo')?.value || '';
  let url = '/api/atividades/?ativo=true';
  if (perfil) url += `&perfil=${perfil}`;
  if (periodo) url += `&periodicidade=${periodo}`;
  const r = await apiFetch(url);
  if (!r || !r.ok) {
    toast('Erro ao exportar atividades', 'error');
    return;
  }
  const rows = r.data.map(a => [
    a.ordem,
    a.nome,
    PERFIL_LABELS[a.perfil] || a.perfil,
    PERIODO_LABELS[a.periodicidade] || a.periodicidade,
    a.obrigatoria ? 'Sim' : 'Não',
    a.tipo_evidencia || '',
    a.indicador || ''
  ]);
  downloadCsvFromRows('catalogo_atividades.csv', ['Ordem', 'Nome', 'Perfil', 'Periodicidade', 'Obrigatória', 'Tipo Evidência', 'Indicador'], rows);
}

async function deleteAtividade(id) {
  if (!confirm('Deseja inativar esta atividade?')) return;
  const r = await apiFetch(`/api/atividades/${id}`, { method: 'DELETE' });
  if (r && r.ok) {
    toast('Atividade inativada!', 'success');
    loadAtividades();
  } else {
    toast(r?.data?.erro || 'Erro ao excluir atividade', 'error');
  }
}

// ══════════════════════════════════════
// ── MODAL HELPERS ──
// ══════════════════════════════════════
function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ── PAGE LOADERS MAP ──
const PAGE_LOADERS = {
  dashboard: loadDashboard,
  rotinas: loadRotinas,
  acompanhamento: loadAcompanhamento,
  pendencias: loadPendencias,
  usuarios: loadUsuarios,
  regionais: loadRegionais,
  atividades: loadAtividades,
  perfil: loadPerfil,
  auditoria: loadAuditoria
};

async function loadPerfil() {
  const wrap = document.getElementById('perfil-content');
  if (!currentUser) return;
  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="card" style="max-width:500px">
      <div class="card-header"><div class="card-title">Meu Perfil</div></div>
      <div class="card-body">
        <div style="display:flex;align-items:center;gap:1rem;margin-bottom:1.5rem">
          <div class="user-avatar" style="width:56px;height:56px;font-size:1.4rem;border-radius:14px">
            ${currentUser.nome.charAt(0)}
          </div>
          <div>
            <div style="font-weight:700;font-size:1.1rem">${currentUser.nome}</div>
            <div style="color:var(--cinza-light);font-size:.85rem">${currentUser.email}</div>
            <span class="badge badge-${currentUser.perfil}" style="margin-top:.25rem">${PERFIL_LABELS[currentUser.perfil]}</span>
          </div>
        </div>
        <div class="divider"></div>
        <h4 style="font-size:.9rem;font-weight:700;margin-bottom:1rem">Alterar Senha</h4>
        <div class="form-group"><label class="form-label">Senha Atual</label>
          <input type="password" id="p-atual" class="form-control"></div>
        <div class="form-group"><label class="form-label">Nova Senha</label>
          <input type="password" id="p-nova" class="form-control"></div>
        <button class="btn btn-primary" onclick="trocarSenha()">Salvar Nova Senha</button>
      </div>
    </div>
    </div>`;
}

async function loadAuditoria() {
  const wrap = document.getElementById('auditoria-content');
  wrap.innerHTML = `<div class="spinner"></div>`;
  const r = await apiFetch('/api/rotinas/audit-log?limit=200');
  if (!r || !r.ok) {
    wrap.innerHTML = '<p class="text-muted">Erro ao carregar auditoria.</p>';
    return;
  }

  const logs = r.data;
  wrap.innerHTML = `
    <div class="analytics-page">
    <div class="card">
      <div class="card-header">
        <div class="card-title">Log de Auditoria</div>
      </div>
      <div class="card-body" style="padding:0">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Quando</th>
                <th>Usuário</th>
                <th>Entidade</th>
                <th>Ação</th>
                <th>Detalhes</th>
              </tr>
            </thead>
            <tbody>
              ${logs.length === 0 ? `<tr><td colspan="5" class="text-center text-muted" style="padding:2rem">Nenhum log encontrado</td></tr>` :
                logs.map(log => `
                  <tr>
                    <td style="font-size:.8rem;color:var(--cinza-light)">${fmtDatetime(log.criado_em)}</td>
                    <td>${log.usuario_nome || 'Sistema'}</td>
                    <td>${log.entidade} #${log.entidade_id || '—'}</td>
                    <td><span class="badge badge-admin">${log.acao}</span></td>
                    <td style="font-size:.8rem;color:var(--cinza)">${formatAuditDetails(log.detalhes)}</td>
                  </tr>
                `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    </div>`;
}

async function trocarSenha() {
  const r = await apiFetch('/api/auth/trocar-senha', {
    method: 'POST',
    body: JSON.stringify({
      senha_atual: document.getElementById('p-atual').value,
      nova_senha: document.getElementById('p-nova').value
    })
  });
  if (r && r.ok) toast('Senha alterada com sucesso!', 'success');
  else toast(r?.data?.erro || 'Erro ao alterar senha', 'error');
}

// ── DATE HELPERS ──
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d + (d.includes('T') ? '' : 'T00:00:00')).toLocaleDateString('pt-BR');
}

function fmtDatetime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatAuditDetails(details) {
  if (!details) return '—';
  try {
    const parsed = typeof details === 'string' ? JSON.parse(details) : details;
    return Object.entries(parsed).map(([key, value]) => {
      if (value && typeof value === 'object' && 'antes' in value && 'depois' in value) {
        return `${key}: ${value.antes ?? '—'} -> ${value.depois ?? '—'}`;
      }
      return `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`;
    }).join(' | ');
  } catch {
    return String(details);
  }
}

// ── INIT ──
document.addEventListener('DOMContentLoaded', async () => {
  const saved = localStorage.getItem('gc_user');
  if (token && saved) {
    currentUser = JSON.parse(saved);
    const r = await apiFetch('/api/auth/me');
    if (r && r.ok) {
      currentUser = r.data;
      localStorage.setItem('gc_user', JSON.stringify(currentUser));
      showApp();
    } else {
      showLogin();
    }
  } else {
    showLogin();
  }

  // Login form
  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const senha = document.getElementById('login-senha').value;
    document.getElementById('login-error').style.display = 'none';
    document.getElementById('login-btn').textContent = 'Entrando...';

    const result = await login(email, senha);
    if (result === true) {
      showApp();
    } else {
      document.getElementById('login-error').textContent = result;
      document.getElementById('login-error').style.display = 'block';
      document.getElementById('login-btn').textContent = 'Entrar';
    }
  });

  // Modal close on overlay click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) overlay.classList.remove('open');
    });
  });
});
