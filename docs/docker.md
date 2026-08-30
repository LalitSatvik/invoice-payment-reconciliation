# Docker setup

`backend/Dockerfile`, `frontend/Dockerfile`, and the root `docker-compose.yml`
bring up the full stack: Postgres, the FastAPI backend (with `alembic upgrade
head` on start), and the Next.js frontend.

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Postgres: `localhost:5432`

## Why `NEXT_PUBLIC_API_URL` is a host URL, not `http://backend:8000`

`NEXT_PUBLIC_*` values are inlined into the frontend bundle at build time and
run in the **browser**, which resolves names against the host, not the compose
network. So the frontend must be given a URL the browser can reach
(`http://localhost:8000` in local dev, or the deployed API's public URL),
never the compose service name.

## Dependency notes

`pandas` is pinned to `2.0.3` with `numpy<2` alongside it — `pandas` 2.0.x
predates NumPy 2's ABI change, so an unpinned `numpy` resolves to 2.x and
breaks the build. `reportlab` and `pdfplumber` are the other pins most likely
to need a bump on a newer base image.
