# GC Comercial — Sistema de Gestão de Rotinas Comerciais

Sistema interno para gestão de rotinas operacionais e táticas da estrutura comercial regional de uma imobiliária.

---

## 🚀 Deploy no Railway

### 1. Pré-requisitos
- Conta no [Railway](https://railway.app)
- Git instalado na sua máquina

### 2. Criar Projeto no Railway

1. Acesse [railway.app](https://railway.app) e clique em **New Project**
2. Selecione **Deploy from GitHub repo** (ou faça upload do código)
3. Conecte este repositório

### 3. Adicionar Banco de Dados PostgreSQL

1. No projeto Railway, clique em **+ New Service**
2. Selecione **Database → PostgreSQL**
3. O Railway vai gerar automaticamente a variável `DATABASE_URL`

### 4. Configurar Variáveis de Ambiente

No painel do Railway, vá em **Variables** e adicione:

```
DATABASE_URL=postgresql://... (gerado automaticamente pelo Railway PostgreSQL)
JWT_SECRET_KEY=sua-chave-secreta-super-segura-mude-isto
SECRET_KEY=outra-chave-secreta-flask-mude-isto
```

> ⚠️ **IMPORTANTE**: Troque as chaves secretas por valores únicos e aleatórios em produção!

### 5. Deploy

O Railway detecta automaticamente o `Procfile` e faz o deploy.

Aguarde o build completar. A URL pública será gerada automaticamente.

---

## 🔐 Acesso Inicial

O admin inicial não vem mais fixo no código. Defina no serviço (Railway → Variables)
antes do primeiro deploy:

```
SEED_ADMIN_EMAIL=seu-email@dominio.com
SEED_ADMIN_PASSWORD=uma-senha-forte
SEED_ADMIN_NAME=Seu Nome
```

Sem essas variáveis, nenhum usuário admin é criado automaticamente — nesse caso,
promova um usuário existente a admin diretamente no banco.

> ⚠️ Depois do primeiro acesso, troque a senha pela tela de perfil e remova
> `SEED_ADMIN_PASSWORD` das variáveis de ambiente.

---

## 👥 Perfis do Sistema

| Perfil | Descrição | Visibilidade |
|--------|-----------|--------------|
| `admin` | Administrador total | Tudo |
| `sr` | Superintendente | Regional completa |
| `gv` | Gerente de Vendas | Próprias atividades + time |
| `cd` | Coordenador de Produto | Próprias atividades |
| `sp` | Supervisor de Parceria | Próprias atividades |

---

## 📋 Funcionalidades

- ✅ **Dashboard** com % de execução, ranking de aderência e visão por perfil
- ✅ **Rotinas automáticas** semanais, quinzenais e mensais por cargo
- ✅ **Catálogo de atividades** pré-configurado para SR, GV, CD e SP
- ✅ **Acompanhamento hierárquico** por regional e perfil
- ✅ **Gestão de pendências** com plano de ação obrigatório
- ✅ **Histórico e auditoria** de alterações
- ✅ **CRUD completo** de usuários, regionais e catálogo
- ✅ **Controle de acesso** por perfil

---

## 🏗️ Estrutura do Projeto

```
gestao-comercial/
├── backend/
│   ├── app.py              # Flask app principal
│   ├── extensions.py       # SQLAlchemy, JWT, Migrate
│   ├── models.py           # Modelos do banco de dados
│   ├── seed_data.py        # Dados iniciais do catálogo
│   └── routes/
│       ├── auth.py         # Login, logout, trocar senha
│       ├── usuarios.py     # CRUD usuários
│       ├── regionais.py    # CRUD regionais
│       ├── atividades.py   # CRUD catálogo de atividades
│       └── rotinas.py      # Geração e execução de rotinas
├── frontend/
│   ├── index.html          # SPA principal
│   └── static/
│       ├── css/style.css   # Estilos (paleta vinho/vermelho/preto/branco)
│       └── js/app.js       # Lógica frontend
├── requirements.txt
├── Procfile
├── railway.toml
└── README.md
```

---

## 🗄️ Banco de Dados

O sistema usa **PostgreSQL** no Railway (criado automaticamente).

Tabelas criadas automaticamente no primeiro boot:
- `regionais`
- `usuarios`
- `atividades_catalogo`
- `rotinas`
- `evidencias`
- `historico_rotinas`

---

## ⚙️ Executar Localmente

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas configurações

# 3. Rodar o servidor
python -m backend.app
```

Acesse: http://localhost:5000

---

## 📊 Como Usar

### Fluxo Recomendado para Administrador:

1. **Criar Regionais** → Menu Regionais
2. **Criar Usuários** → Menu Usuários (associar perfil e regional)
3. **Gerar Rotinas** → Dashboard → botão "⚡ Gerar Agora"
4. **Acompanhar** → Menu Acompanhamento ou Dashboard

### Fluxo para Gestores (GV, SR, CD, SP):

1. Acessar **Minhas Rotinas**
2. Clicar em cada atividade
3. Atualizar o status (Concluída / Em Andamento / Não Realizada)
4. Adicionar comentário ou justificativa
5. Verificar **Pendências** regularmente

---

## 📐 Regra de Execução

```
% de Execução = (Atividades Concluídas / Total Previstas no Período) × 100
```

- Apenas status `concluida` conta no numerador
- `nao_realizada`, `em_andamento` e `nao_iniciada` **não** contam como concluídas
- Atividades obrigatórias não concluídas no prazo entram na tela de **Pendências**
