# Sample Tenant App

This app exposes a discovery endpoint and two service task APIs:
- Sync: `/api/sync-task`
- Async: `/api/async-task` (calls back to the workflow service)

Discovery endpoint:
- `/.well-known/workflow-discovery`

Env vars:
- `TENANT_API_KEY` (used to sign callback)
- `APP_PORT` (default 9000)
- `INTERNAL_BASE_URL` (URL used inside discovery payload)
