# Workflow Shared Service

## Backend (Django)

Create and use the Python virtual environment, then install dependencies.

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

Run migrations and start the server (SQLite for local dev):

```bash
USE_SQLITE=1 python backend/manage.py migrate
USE_SQLITE=1 python backend/manage.py runserver 0.0.0.0:8000
```

Health check:

```bash
curl -s http://localhost:8000/api/health
```

## Frontend (Angular)

```bash
cd frontend
npm install
npm start
```

Open: `http://localhost:4200`

## Notes

- Django framework imports use `from django...` and require Django installed in the backend venv.
- App code uses `from core...` and `from config...`.
- Backend API base URL can be set in `frontend/src/environments/environment.development.ts` for dev, or via `API_BASE_URL` in the frontend Docker container (runtime `app-config.js`).
