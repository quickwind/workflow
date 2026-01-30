# Workflow Shared Service

Multi-tenant workflow orchestration service:
- Backend: Django + Postgres + SpiffWorkflow
- Frontend: Angular + bpmn-js + form-js

## Quick Start (Docker Compose)

Prereqs:
- Docker Desktop (or Docker Engine) with the `docker compose` plugin

Bring everything up (Postgres + backend + frontend):

```bash
docker compose up --build
```

What this starts:
- `postgres` (Bitnami Postgres) on `localhost:5432` (data persisted in a named volume)
- `backend` on `localhost:8000` (runs `manage.py migrate` then gunicorn)
- `frontend` on `localhost:4200`
- `tenant-stub` on `localhost:8080`

Optional: use the sample env file (recommended):

```bash
cp backend/.env.example .env
docker compose up --build
```

URLs:
- Frontend: http://localhost:4200
- Backend health: http://localhost:8000/api/health

Stop:

```bash
docker compose down
```

Stop + wipe Postgres data:

```bash
docker compose down -v
```

### Create a Local Tenant + API Key (required)

Most backend endpoints require `X-Tenant-Api-Key`. Create a tenant + key in the running backend container:

```bash
TENANT_SLUG=tenant-a
TENANT_NAME="Tenant A"
TENANT_API_KEY=tenant-a-test-key

docker compose exec -T backend python manage.py shell -c "
from core.models import Tenant, TenantApiKey
tenant, _ = Tenant.objects.get_or_create(slug='$TENANT_SLUG', defaults={'name': '$TENANT_NAME'})
TenantApiKey.objects.get_or_create(
  tenant=tenant,
  key_hash=TenantApiKey.hash_key('$TENANT_API_KEY'),
  defaults={'name': 'dev'}
)
print('tenant_id=%s slug=%s' % (tenant.id, tenant.slug))
" 
```

Now you can call APIs with:

```bash
curl -s http://localhost:8000/api/workflows/list \
  -H "X-Tenant-Api-Key: tenant-a-test-key"
```

Note: the Angular UI does not automatically attach `X-Tenant-Api-Key` yet. For now, use curl for API testing, or use a browser header-injection tool for local dev.

If you want the frontend to work end-to-end without manually injecting headers, the next step is to implement designer login and/or a dev-only API key injector.

### Run an End-to-End API Smoke Test

This script will:
- Create a tenant + API key
- Seed discovery data (catalog + RBAC + directory)
- Upload a BPMN and start an instance
- Complete a UserTask and simulate a ServiceTask callback

It expects the sample tenant app to be running on port 9000 (Docker Compose includes it by default):

```bash
docker compose up --build
```

```bash
bash scripts/verify_e2e.sh
```

## Run From Source (Debugging)

### Backend (Django)

Create and use the Python virtual environment, then install dependencies:

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

Backend defaults are production-safe (`DJANGO_DEBUG` defaults to false). For local debugging, explicitly set dev env vars:

```bash
export DJANGO_DEBUG=true
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export DJANGO_SECRET_KEY=dev-secret
export CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
```

Run with breakpoints:
- Use `runserver` (not gunicorn) for step-through debugging
- If you use VSCode, configure a Python debug launch to run `backend/manage.py runserver`

Option A: SQLite (fastest local dev)

```bash
USE_SQLITE=1 python backend/manage.py migrate
USE_SQLITE=1 python backend/manage.py runserver 0.0.0.0:8000
```

Option B: Postgres (run Postgres via Docker, run Django from source)

```bash
docker compose up -d postgres

export USE_SQLITE=false
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=workflow
export POSTGRES_USER=workflow
export POSTGRES_PASSWORD=workflow

python backend/manage.py migrate
python backend/manage.py runserver 0.0.0.0:8000
```

Create a tenant + API key (SQLite or Postgres):

```bash
python backend/manage.py shell -c "
from core.models import Tenant, TenantApiKey
tenant, _ = Tenant.objects.get_or_create(slug='tenant-a', defaults={'name': 'Tenant A'})
TenantApiKey.objects.get_or_create(tenant=tenant, key_hash=TenantApiKey.hash_key('tenant-a-test-key'), defaults={'name': 'dev'})
print('OK')
" 
```

### Frontend (Angular)

```bash
cd frontend
npm install
npm start
```

Open: http://localhost:4200

VSCode debugging:
- Frontend has VSCode launch configs under `frontend/.vscode/launch.json`
- Recommended flow: run `npm start` then start the "Chrome" debug config

## Common Troubleshooting

- Backend refuses to start in production mode:
  - `DJANGO_DEBUG` defaults to `false`; when false, you must set `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`
- 401 responses from API:
  - Most endpoints require `X-Tenant-Api-Key`
- CORS errors when running backend+frontend separately:
  - Set `DJANGO_DEBUG=true` and `CORS_ALLOWED_ORIGINS=http://localhost:4200,...`

Frontend backend URL configuration:
- Dev default is `http://localhost:8000` in `frontend/src/environments/environment.development.ts`
- Docker runtime uses `API_BASE_URL` to generate `app-config.js`

## Useful Scripts

API + workflow smoke flow:

```bash
bash scripts/verify_e2e.sh
```

## Discovery Sync

- Discovery schema example: `docs/discovery_schema.json`
- Management command: `python backend/manage.py sync_discovery --tenant <tenant-slug>`

Sample tenant app discovery URL (when running via Compose):
- `http://sample-tenant-app:9000/.well-known/workflow-discovery`

## Notes

- Django framework imports use `from django...` and require Django installed in the backend venv.
- App code uses `from core...` and `from config...`.
- Backend APIs are tenant-scoped via `X-Tenant-Api-Key`.
