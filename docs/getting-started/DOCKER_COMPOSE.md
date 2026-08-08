# Docker Compose
`docker-compose.yml` provides local Postgres, Redis, API, and iMessage relay services.
## Start Everything
```bash
cp .env.example .env
docker compose up --build
```
## Start Dependencies Only
```bash
docker compose up -d postgres redis
```
This is the recommended local development setup when running the API and web app directly on the host.
## Services
| Service | Port | Purpose |
| --- | ---: | --- |
| `postgres` | 5432 | Main database |
| `redis` | 6379 | Celery broker and backend |
| `api` | 8000 | FastAPI backend |
| `imessage-relay` | 8787 | Self-hosted relay service |
## API Container
The API service builds from `Dockerfile.api` and overrides:
```text
DATABASE_URL=postgresql+psycopg://puregamma:puregamma@postgres:5432/puregamma
REDIS_URL=redis://redis:6379/0
```
Health:
```bash
curl http://localhost:8000/health
```
## iMessage Relay Container
The relay container is useful for HMAC/idempotency testing, but real iMessage sends require macOS and Messages.app. A Linux container returns `unsupported_os` for actual sends.
## Reset Local Data
This removes the Postgres volume:
```bash
docker compose down -v
docker compose up -d postgres redis
```
Do not run destructive reset commands against production infrastructure.
## Logs
```bash
docker compose logs -f api
docker compose logs -f postgres
docker compose logs -f redis
docker compose logs -f imessage-relay
```
## Common Issues
| Issue | Fix |
| --- | --- |
| API cannot connect to Postgres | Use the container URL only inside Compose; use `localhost` from host. |
| Port already in use | Stop the conflicting service or change the published port. |
| Relay exits on startup | Set `IMESSAGE_RELAY_SECRET` in `.env`. |
| Real iMessage fails in container | Use a Mac host relay instead; containers are not a production Messages.app runtime. |
