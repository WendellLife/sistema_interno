# 01 — Stack e arquitetura

## 1. Dependências

```toml
# pyproject.toml (gerenciado com uv)
[project]
requires-python = ">=3.12"
dependencies = [
  "django==5.1.*",
  "djangorestframework==3.15.*",
  "djangorestframework-simplejwt==5.3.*",
  "django-filter==24.*",
  "psycopg[binary]==3.2.*",
  "celery[redis]==5.4.*",
  "django-celery-beat==2.7.*",
  "django-storages[s3]==1.14.*",
  "python-decouple==3.8",
  "structlog==24.*",
  "sentry-sdk==2.*",
  "django-prometheus==2.3.*",
  "openpyxl==3.1.*",        # export XLSX
  "weasyprint==62.*",       # export PDF
  "workalendar==17.*",      # feriados BR para SLA em horas úteis
]

[dependency-groups]
dev = ["pytest-django", "pytest-cov", "factory-boy", "ruff", "mypy",
       "django-debug-toolbar", "django-extensions"]
```

Front-end (se HTMX): `htmx 2.x` + `alpinejs 3.x` via CDN ou `django-htmx`. Sem build step.

## 2. Estrutura de pastas

```
sistema_interno/
├── config/
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py · asgi.py · wsgi.py · celery.py
├── core/                 # base de tudo
│   ├── models.py         # TimeStampedModel, Setor, CentroCusto, Auditoria
│   ├── permissions.py    # classes DRF por papel
│   ├── calendario.py     # horas úteis + feriados
│   └── mixins.py         # SetorScopedQuerysetMixin
├── chamados/
├── apontamentos/
├── documentacao/
├── almoxarifado/
├── projetos/
├── integracoes/
│   ├── sankhya/{client.py,tasks.py,mapeamento.py}
│   ├── whatsapp/{webhook.py,tasks.py}
│   └── ia/{classificador.py,tasks.py}
├── relatorios/
├── templates/            # se HTMX
├── static/
│   └── css/tokens/       # copiar de referencias/_ds/tokens/
└── manage.py
```

**Regra de camadas (não negociável):**

- `models.py` — estrutura, constraints, `@property` puras. Sem regra de fluxo.
- `services.py` — **toda** a regra de negócio, sempre em função explícita e transacional. Views e tasks só chamam serviços.
- `selectors.py` — consultas de leitura/agregação usadas por relatórios e dashboards.
- `views.py` / `viewsets.py` — validação de entrada, permissão, chamada de serviço, resposta.
- `signals.py` — só efeitos colaterais assíncronos (enfileirar alerta). Nunca regra de saldo.

## 3. Apps e responsabilidades

| App | Responsabilidade | Depende de |
| --- | --- | --- |
| `core` | Usuário, setor, centro de custo, calendário útil, auditoria, permissões | — |
| `chamados` | Chamado, categoria, prioridade, SLA, comentários, anexos, histórico | `core` |
| `apontamentos` | Tipo de trabalho, apontamento, cronômetro, motivo de retrabalho, aprovação | `core`, `chamados`, `projetos` |
| `documentacao` | Documento, versão, requisito documental por categoria, cobertura | `core`, `chamados`, `projetos` |
| `almoxarifado` | Item, estoque, movimento, solicitação, nota fiscal, transferência, inventário, cotação | `core` |
| `projetos` | Projeto, fase (kanban 8 colunas), marco, alocação | `core` |
| `integracoes` | Sankhya, WhatsApp, IA — clients e tasks | todos |
| `relatorios` | Indicadores do painel e exportações CSV/XLSX/PDF | todos (via selectors) |

## 4. Usuário

`core.User` custom (`AbstractUser`) desde a primeira migration — **não usar o `auth.User` padrão**:

```python
class User(AbstractUser):
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="usuarios")
    matricula = models.CharField(max_length=20, unique=True)
    capacidade_diaria_min = models.PositiveIntegerField(default=480)  # 8h
    ativo_para_apontamento = models.BooleanField(default=True)
```

`AUTH_USER_MODEL = "core.User"`. Papéis = `Group` do Django, nomes exatos: `Colaborador`, `Responsavel`, `GerenteSetor`, `GerenteTI`, `Compras`, `Administrador` (criados por data migration).

## 5. Settings relevantes

```python
# base.py
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",
                                "rest_framework.filters.OrderingFilter"),
}

CELERY_BEAT_SCHEDULE = {
    "sla-vencimentos":   {"task": "chamados.verificar_sla",       "schedule": crontab(minute="*/15")},
    "estoque-resumo":    {"task": "almoxarifado.resumo_diario",   "schedule": crontab(hour=7, minute=0)},
    "sankhya-sync":      {"task": "integracoes.sankhya_sync",     "schedule": crontab(hour=2, minute=30)},
}
```

## 6. Ambiente local

```yaml
# docker-compose.yml — serviços
web:     python:3.12-slim, uv sync, runserver 0.0.0.0:8000
db:      postgres:16, volume persistente, POSTGRES_DB=sistema_interno
redis:   redis:7-alpine
worker:  celery -A config worker -l info
beat:    celery -A config beat -l info
```

Seed obrigatório (`python manage.py seed_demo`): 11 setores, 6 papéis, ~40 usuários, 8 tipos de trabalho, 5 motivos de retrabalho, ~120 itens de estoque com saldo, 34 chamados abertos, 17 projetos ativos, 23 encerrados — replicando os números do protótipo para conferência visual.

## 7. Qualidade e CI

```
ruff check . && ruff format --check .
mypy sistema_interno
pytest --cov --cov-fail-under=80        # 80% obrigatório em services.py
python manage.py makemigrations --check --dry-run
```

GitHub Actions: lint → testes → `migrate --check` → build da imagem → deploy manual aprovado em produção.

## 8. Deploy

| Ambiente | Infra | Notas |
| --- | --- | --- |
| Dev | docker-compose | `uv sync`, seed com factory_boy |
| Homologação | VM Linux, Gunicorn + Nginx | dump semanal anonimizado da produção |
| Produção | Gunicorn (UvicornWorker) + Nginx + PostgreSQL gerenciado | backup PITR diário, retenção 30 dias; migrations rodam no pipeline |
