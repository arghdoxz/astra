# ASTRA deployment guide

Backend: FastAPI in Docker on Render. Frontend: Next.js on Vercel. Demo bundles are static files in `frontend/public/demo/` and work even when the backend is down.

## 1. Local development
Backend (Python 3.13, managed by `uv`):
```
cd backend
uv sync
cp ../.env.example .env        # then edit; put GEMINI_API_KEY only in backend/.env (git-ignored)
uv run uvicorn app.main:app --reload --port 8000
```
Check: http://localhost:8000/api/health

Frontend:
```
cd frontend
npm i
echo NEXT_PUBLIC_API_BASE=http://localhost:8000 > .env.local
npm run dev
```
Open http://localhost:3000.

## 2. Environment variables
| Variable | Where | Default / example | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | backend | (empty) | Secret. Without it AI falls back to templates. |
| `GEMINI_MODEL` | backend | `gemini-flash-latest` | |
| `GEMINI_FALLBACK_MODEL` | backend | `gemini-2.5-flash` | |
| `SPHEREX_COLLECTIONS` | backend | `spherex_dr1,spherex_qr3` | Never add QR2. |
| `MAX_EXPOSURES` | backend | `240` local, `160` on Render | Cap per investigation. |
| `CUTOUT_CONCURRENCY` | backend | `8` local, `6` on Render | Parallel IRSA cutout downloads. |
| `CUTOUT_MODE` | backend | `stream` | `stream` stops at the EPSF HDU (ZODI is kept; EPSF/WCS-WAVE come from a per-detector calib cache); `full` downloads every HDU. |
| `CACHE_DIR` | backend | `./cache`; `/app/cache` in Docker | Disk cache and rendered PNGs. |
| `DB_PATH` | backend | `./data/astra.sqlite3`; `/app/data/astra.sqlite3` in Docker | Annotations, history, AI cache. |
| `ALLOWED_ORIGINS` | backend | `http://localhost:3000,https://*.vercel.app` | Comma list. `*.vercel.app` previews are also allowed by regex. |
| `SIMBAD_TAP_URLS`, `GAIA_TAP_URL` | backend | see `.env.example` | Optional overrides. |
| `PORT` | backend | set by Render | Docker CMD uses `${PORT:-8000}`. |
| `NEXT_PUBLIC_API_BASE` | frontend | `http://localhost:8000` | No trailing slash. Set in Vercel project env. |

## 3. Render (backend)
1. Push the repo to GitHub (the local repo has no commits or remote yet):
   ```
   git add -A
   git grep --cached -nE "AIza[0-9A-Za-z_-]{30}"; git diff --cached --name-only | grep -E "(^|/)\.env$"   # both must print nothing
   git commit -m "ASTRA: Space Apps 2026"
   git branch -M main
   git remote add origin https://github.com/<you>/astra.git && git push -u origin main
   ```
   The Docker image has **not** been built locally (no Docker on the dev machine); Render's first build is its first test.
2. Render dashboard: New > Blueprint > pick the repo. It reads `render.yaml` (service `astra-api`, Docker, root `backend`, health check `/api/health`, plan Starter; the free 512 MB tier may OOM during reprojection).
3. When prompted, set the secret `GEMINI_API_KEY` (marked `sync: false`, so Render asks for it).
4. Wait for the first deploy, then open `https://<service>.onrender.com/api/health`.
5. The disk is **ephemeral**: the cache, history and annotations reset on every redeploy. Demo bundles cover the five targets. To persist, uncomment the `disk:` block in `render.yaml` (paid plan) and set `CACHE_DIR=/app/data/cache`.

## 4. Vercel (frontend)
1. New Project > import the repo > **Root Directory: `frontend`**. Framework preset: Next.js.
2. Environment variable: `NEXT_PUBLIC_API_BASE=https://<service>.onrender.com`.
3. Deploy and note the production URL (for example `https://astra-xyz.vercel.app`).
4. Back in Render, set `ALLOWED_ORIGINS=http://localhost:3000,https://astra-xyz.vercel.app` (edit the value in `render.yaml` or the dashboard) and redeploy. Vercel preview URLs (`*.vercel.app`) are already allowed by regex.

## 5. Warm-up before judging
Render sleeps idle services and the cache is cold after each deploy.
1. `curl https://<service>.onrender.com/api/health` (repeat until it returns 200).
2. Run one investigation per demo target from the UI (or `POST /api/investigations`) so frames and results are cached: Barnard's Star, Eps Ind B, WISE 0855-0714, RW Aur, R Dra. Each takes up to a few minutes cold.
3. Confirm the demo fallback: stop or break `NEXT_PUBLIC_API_BASE` locally and check the five target cards still open from `/demo/{slug}/`.

## 6. Regenerating demo bundles
Run locally with network access (IRSA, Gaia, SIMBAD) and a working `backend/.env`:
```
cd backend
uv run python -m scripts.precompute_targets                  # all five
uv run python -m scripts.precompute_targets --only eps-ind-b # one target
uv run python -m scripts.precompute_targets --fov 3 --max-exposures 160
```
Output: `frontend/public/demo/{slug}/investigation.json`, `frontend/public/demo/{slug}/frames/*.png`, and the merged `frontend/public/demo/index.json`. Failed investigations write no bundle. At most 120 single-exposure frames are kept per bundle (a warning is added to `warnings`). Commit the results and redeploy Vercel.

## 7. Secret hygiene
- `GEMINI_API_KEY` lives only in `backend/.env` (git-ignored) and the Render dashboard.
- Before every push: `git grep -nE "AIza[0-9A-Za-z_-]{30}"` must print nothing; also check `git status` does not list `.env`.
- The key was shared in chat during development: **rotate it after the hackathon**.
