# VIP99 Bot Control Service

This private service runs the Python Telegram bot as a supervised child process and exposes authenticated status/start/stop/restart endpoints for the dashboard.

Set `BOT_TOKEN`, `GITHUB_TOKEN`, `ADMIN_ID`, `REPO_OWNER`, `REPO_NAME`, and `CONTROL_API_TOKEN` as Render environment secrets. Never commit `.env` or token values.

Health: `GET /healthz`
Authenticated status: `GET /api/status`
Authenticated actions: `POST /api/start`, `POST /api/stop`, `POST /api/restart`

Use `Authorization: Bearer $CONTROL_API_TOKEN` for the authenticated endpoints.
