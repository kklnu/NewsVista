# NewsVista — Progress log

_Last updated: 2026-10-20 (evening, UTC-4)_

## Done (verified locally)
- [x] Audited `My_News_Assignment.pdf` + starter (`myNews/`); starter left untouched.
- [x] Python 3.12.10 installed (user scope) for the backend.
- [x] Backend (FastAPI + SQLAlchemy): sources, articles, stories, story_articles, background, AI analyses, call log, collection runs + per-source results.
- [x] Live ingestion from 11 feeds / 5 publishers (BBC, NPR, Fox News, The Guardian, CBS) — all reachable 2026-10-20.
- [x] Duplicate prevention by normalized URL (repeat run: 0 new, 0 duplicate URLs).
- [x] 168-hour window enforced in queries **and** cleanup; missing/future dates excluded and counted.
- [x] Event grouping (TF-IDF + entities + time window); 15 live multi-publisher groups on 2026-10-20 sample.
- [x] Wikipedia background with conservative relevance checks.
- [x] AI pipeline (Gemini REST, prompt + config in `backend/ai_config/`), fingerprint cache, output validation.
- [x] API: `/health`, `/stories`, `/stories/{id}`, `/status`, protected `POST /admin/collect`.
- [x] 25 backend tests passing (fixtures, retention, expiration-in-group, shared AI reuse, failures).
- [x] GitHub Actions hourly workflow + `workflow_dispatch`; `render.yaml`; `.env.example`; SQL migration.
- [x] Flutter app: home, story detail, AI analysis, perspective, about/server log; `flutter analyze` clean; 6 widget tests passing.

## 2026-10-21 — UI redesign to match mockup
- [x] Dark mockup theme, category chips, hero card, thumbnails, bottom nav, Search, 4-tab story page, AI Key Details.
- [x] Web build runs in Chrome against the local API (CORS for localhost); emulator screenshots verified.
- [x] Backend 26 tests, Flutter 7 widget tests, analyzer clean.

## Blockers (need Kiranpreet)
1. **Gemini API key** → AI analysis cannot be generated or reviewed until provided (status shows "pending", never fake text).
2. **Supabase project** → `DATABASE_URL` (Session pooler string).
3. **GitHub repo** → push code; add Actions secrets `NEWSVISTA_API_URL`, `NEWSVISTA_ADMIN_TOKEN`.
4. **Render account** → deploy from repo (Blueprint `render.yaml`), set env vars.
5. **Phone** → USB debugging on, connected by cable; Phone Link paired.

## Next actions
- Deploy → run `workflow_dispatch` once → wait for 2 scheduled runs → record evidence in `docs/VERIFICATION.md`.
- With AI key: generate analyses, manually review 3 (`docs/AI_REVIEW.md`).
- Build release APK with deployed URL; install on phone; 3 core-workflow runs.
