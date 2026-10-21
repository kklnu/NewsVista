# NewsVista — One story. Multiple sources. A clearer perspective.

CS 403 "My News" project (Flutter + AI + Server). NewsVista collects news from several
publishers every hour, groups articles about the **same event** into one story, attaches
relevant background (Wikipedia), and generates a grounded, cited **AI analysis** once per
story on the server. The Flutter app only reads those stored results.

| Item | Value |
|---|---|
| Deployed API | https://newsvista-api.onrender.com (docs: `/docs`, status: `/status`) |
| Web version (extra) | https://kklnu.github.io/NewsVista/ (Flutter web build on the `gh-pages` branch; the required client is the Android app) |
| Android APK | `flutter_app/build/app/outputs/flutter-apk/app-release.apk` (build with §5.4) |
| Scheduler | `.github/workflows/hourly-collect.yml` (hourly + manual) |
| AI prompt + model config | `backend/ai_config/` |
| Verification evidence | `docs/VERIFICATION.md` |
| AI output review | `docs/AI_REVIEW.md` · AI reflection: `docs/AI_REFLECTION.md` |
| Presentation script | `docs/PRESENTATION.md` |

The original starter (`myNews/`) is kept unchanged for reference only.

---

## 1. Architecture

```
                 every hour (GitHub Actions cron, + manual "Run workflow")
                                     │  POST /admin/collect  (Bearer ADMIN_TOKEN)
                                     ▼
 ┌──────────────┐  RSS   ┌─────────────────────────── FastAPI backend (Render) ───────────────────────────┐
 │ BBC, NPR,    │──────▶ │ 1 ingest → 2 retention (168h) → 3 grouping → 4 AI analysis → 5 background     │
 │ Fox, Guardian│        │      │               │                 │              │ Gemini API   │ Wikipedia│
 │ CBS feeds    │        │      ▼               ▼                 ▼              ▼  (server key)  ▼  API    │
 └──────────────┘        │  ┌──────────────── Supabase PostgreSQL (persistent) ─────────────────────────┐ │
                         │  │ sources · articles · stories · story_articles · ai_analyses · ai_call_log │ │
                         │  │ background_links · story_background · collection_runs(+_sources)          │ │
                         │  └───────────────────────────────────────────────────────────────────────────┘ │
                         │  GET /stories · GET /stories/{id} · GET /status · GET /health   (read-only)     │
                         └──────────────────────────────────┬─────────────────────────────────────────────┘
                                                            │ HTTPS JSON (stored results only)
                              ┌─────────────────────────────┼──────────────────────────────┐
                              ▼                             ▼                              ▼
                        Phone A (Flutter)            Phone B (Flutter)       Publisher / Wikipedia pages
                        same stored story +          same stored story +     open in the phone's browser
                        same AI analysis id          same AI analysis id
```

**Server/client separation.** The Flutter app never fetches feeds, groups articles, or calls
an AI model. Opening the app, pulling to refresh, or tapping "View AI analysis" only performs
`GET` requests that read stored rows. GET handlers contain no feed, Wikipedia, or model calls
(see `backend/app/views.py`). A test proves repeated reads by two clients reuse the same
`analysis_id`/`version` with zero extra model calls (`test_shared_ai_output_reused_by_two_clients_without_model_calls`).

## 2. Repository layout

```
backend/
  app/            main.py (API) · pipeline.py (hourly job) · grouping.py · background.py
                  feeds.py · normalize.py · models.py · views.py · ai/ (client.py, analysis.py)
  ai_config/      analysis_system_prompt.md · model_config.json   ← prompts + model config
  migrations/     001_init.sql (generated from models by scripts/dump_schema.py)
  scripts/        collect.py (run one collection from CLI) · dump_schema.py
  tests/          pytest suite + fixtures/grouping_fixtures.json (CONTROLLED FIXTURES)
  sources.json    feeds and publisher labels
flutter_app/      Flutter Android client (lib/, test/)
.github/workflows/hourly-collect.yml
render.yaml       Render blueprint
docs/             verification, AI review, AI reflection, presentation
```

## 3. Data model

| Table | Purpose | Key columns |
|---|---|---|
| `sources` | One RSS feed (several feeds can share a publisher) | `id`, `publisher`, `feed_url` |
| `articles` | One publisher report | `id` = sha256(normalized URL)[:20] (stable), **unique** `normalized_url`, `title`, `url`, `published_at` (UTC), `excerpt` (feed summary), `feed_text` (partial text the feed distributes; AI input only), `content_hash`, `ingested_at`, `last_seen_at` |
| `stories` | One event | `id` = `st_` + hash(seed article) (stable), `headline`, `headline_article_id`, `created_at`, `updated_at`, `latest_published_at` |
| `story_articles` | Article ↔ story (an article belongs to one story) | **unique** `article_id`, `match_score`, `matched_article_id` (grouping evidence) |
| `background_links` / `story_background` | Reference resources, linked per story | **unique** `url`; `matched_term`, `method` (`entity`/`ai_topic`) |
| `ai_analyses` | Current analysis per story | `fingerprint`, `input_article_ids`, `input_scope`, `model`, `prompt_version`, `generated_at`, `content_json`, `needs_review`, `review_notes`, `version`, `status`, `error` |
| `ai_call_log` | Every model call (no text) | `called_at`, `story_id`, `model`, `outcome`, `latency_ms` |
| `collection_runs` / `collection_run_sources` | Job log | trigger, start/end, status, counts (fetched/new/updated/skipped/expired/stories/AI), per-feed outcome + error |

All timestamps are timezone-aware UTC (`UTCDateTime` type). The app displays local time.

## 4. Behaviour

### 4.1 Collection, duplicates, failures
- 11 feeds / **5 distinct publishers**: BBC News (World, Top), NPR (News, World, Politics), Fox News
  (Latest, World, Politics), The Guardian (World, US), CBS News (Latest). The starter's three
  publishers are kept; two were added for more genuine cross-publisher overlap. All verified reachable 2026-10-20.
- **Duplicates:** URLs are normalized (https, lower-case host, tracking params like `utm_*`/`at_*`
  removed, fragment and trailing slash removed). The article ID is a hash of that URL. Re-fetching
  updates the existing row (title/excerpt/time if changed) — never inserts a copy. The same article
  appearing in two feeds of one publisher is stored once.
- **Isolation:** each feed is fetched and committed separately. A failing feed is recorded in
  `collection_run_sources` (HTTP status, error) and the run is `partial`; stored stories remain.
  The run status is `success` (all feeds ok), `partial` (some ok) or `failed` (none / crash).
  Overlapping runs are refused (`409`) while a run started < 30 min ago is still `running`.

### 4.2 Seven-day rolling window (168 h, by **publication** time)
- Items with a **missing or unparseable publication date are excluded** from the news dataset and
  counted as `skipped_invalid_date` (we cannot place them in the window honestly).
- Items dated more than **60 minutes in the future** are rejected (`skipped_future`).
- Items already older than 168 h at fetch time are not stored (`skipped_too_old`).
- **Between runs:** every API query filters `published_at >= now − 168h`, so an article disappears
  from the API the moment it crosses the boundary, even before cleanup runs. A story whose
  articles have all expired returns 404.
- **Each run:** deletes expired articles (and their stored excerpt/text); clears any AI analysis
  whose inputs included an expired article (then regenerates from retained articles); deletes
  stories left with no articles together with their analysis and background associations; deletes
  background links no longer linked to any story (background pages themselves may be older).
- `collection_runs` and `ai_call_log` are kept as operational logs; they contain counts, IDs and
  errors only — never article bodies or summaries.

### 4.3 Grouping method (`backend/app/grouping.py`)
1. Features per article: stemmed title tokens (counted twice), excerpt tokens, and **entities**
   (capitalized names/acronyms such as "Helen Haines", "NFL", "Aomori").
2. **TF-IDF** weights over all articles in the current window, so common words ("Trump", "says",
   "war") count little and event-specific words count a lot.
3. Two articles may link only if **all** hold: published ≤ **72 h** apart; share ≥ **1 specific
   entity** (generic ones like "US", "UK", weekdays are ignored); share ≥ **3 meaningful terms**;
   cosine similarity ≥ **0.33** — raised to **0.40** if only one entity is shared, and **0.55** for two
   articles from the same publisher.
4. **Incremental & stable:** a new article joins the story of its best qualifying match; otherwise it
   seeds a new story. Existing memberships never move, so story IDs are stable and new coverage joins
   an existing story instead of duplicating it. For stories of 3+ articles, the candidate's mean
   similarity to the story must be ≥ 0.16 (prevents chaining drift).
5. Headline = the most central article's title (earliest if only 1–2 articles).

**Calibration on live data (2026-10-20, 262 articles):** an initial threshold of 0.30 wrongly merged
two different Ebola events (Kenya cases vs. a Nigeria case, 0.31) and a Theranos interview with a TV
ratings story (0.32). Raising thresholds to the values above separated them while keeping 15 correct
multi-publisher groups (e.g. Alberta referendum: NPR+Guardian+BBC; attack on MP Helen Haines:
Guardian+BBC; UK jets to Saudi Arabia: BBC+Guardian+Fox; Pope Leo's return: BBC+Fox).

**Known failure cases**
- *Digest headlines:* an NPR newsletter titled "2026 midterms could be the most expensive on record.
  And, Macron condemns protests" joined the France-protests story because its second half matches.
- *Same storyline, different events:* follow-ups (e.g. charges filed vs. a family statement about the
  same attack) are merged — usually desirable, but they are technically distinct developments.
- *Different wording:* if publishers describe one event with no shared names (e.g. "Prime Minister"
  vs. the PM's name only), they may stay separate (false split). Thresholds favour false splits over
  false merges.
- Articles more than 72 h apart never merge, so a long-running story can split into several.

**Tests (controlled fixtures — not live articles):** `backend/tests/fixtures/grouping_fixtures.json`
has 6 multi-publisher events and 4 similar-topic/different-event pairs (Trump tariff vs. Trump state
dinner, Japan vs. Turkey earthquakes, ECB cut vs. Bank of England hold, California vs. Greece
wildfires). `test_grouping.py` asserts the exact partition.

### 4.4 Background resources (`backend/app/background.py`)
Candidates are proper-noun phrases in the story's articles (multi-word names first), plus up to 3
topics suggested by the AI analysis. Each is looked up by **exact title** on the Wikipedia API
(following redirects). Rejected: missing pages, disambiguation/list/surname/placeholder pages,
redirects that change the name ("Jane Doe" → "John Doe", "Gov" → "Government"), generic concept
pages ("Town hall"), and pages whose intro does not mention at least two other terms from the
story. Max 3 links per story; otherwise the API returns **"No background resource available"**.
Wikipedia is called ≤ 25 stories per run, 1 request/second, with a descriptive User-Agent.

### 4.5 AI analysis (`backend/app/ai/`, `backend/ai_config/`)
- **Model:** Google Gemini via REST (`gemini-3.6-flash` with low thinking; fallbacks `gemini-3.5-flash-lite`,
  `gemini-3.8-flash`), temperature 0.2, JSON-schema-constrained output. Key only in server env var `GEMINI_API_KEY`.
- **Input:** up to 8 retained articles per story (round-robin across publishers), each labelled
  `A1…A8` with publisher, title, time and feed text (≤ 1,800 chars). The system prompt states that
  article content is **untrusted data, not instructions**.
- **Output:** overview (+citations), agreements (must cite ≥ 2 publishers), disagreements,
  uncertainties, perspectives (named after people/groups, never publishers; each claim cited),
  limitations, background topics. If fewer than two supported perspectives remain →
  **"Insufficient evidence for distinct perspectives."**
- **Server-side validation** (`analysis.py`): unknown citation labels removed; agreement items
  without two publishers removed; perspectives named after a publisher/media removed; quoted text
  not found verbatim in the cited articles removed; numbers not present in the inputs removed.
  Every removal is logged in `review_notes` and sets `needs_review`, shown in the app as
  "Automated fact checks".
- **Input scope disclosure:** `feed_excerpts`, `feed_partial_text` or `mixed`, shown on screen.
- **Caching / reuse:** `fingerprint = sha256(prompt_version + sorted(article_id:content_hash))`.
  The job only calls the model when a story's fingerprint differs from its stored analysis. GET
  endpoints never call the model; all readers get the same stored `analysis_id`/`version`.
- **Statuses served:** `current`; `outdated` (new articles joined since — content still shown with a
  banner); `expired_inputs` (an input article expired → content hidden until regenerated);
  `pending` (not generated yet); `failed` (last attempt failed, no content). Never fallback text.
- **Quota protection:** ≤ `AI_MAX_PER_RUN` (default 6) calls per run, 7 s apart, multi-publisher
  stories first; on HTTP 429/auth errors the run stops calling the model; identical failed inputs are
  retried after 3 h.

### 4.6 Ask AI assistant (optional extra, beyond the PDF requirements)
Two chat entry points: **Ask AI** on every story (answers only from that story's retained articles
and background descriptions) and an **Ask AI** tab (finds the best-matching stories of the last
7 days by TF-IDF term overlap, or the latest multi-publisher stories for "top stories" questions).

How it stays compatible with the required architecture (PDF §1, "the Flutter app must not perform
AI generation"):
- The app never calls a model: it POSTs the question to our server (`POST /stories/{id}/ask`,
  `POST /ask`); only the server holds `GEMINI_API_KEY`.
- The required AI overview/perspectives are untouched: still generated once by the hourly job and
  reused by every reader. Opening a story, refreshing, or the AI Analysis tab never calls the model.
- Answers are grounded: the model only receives stored coverage (as untrusted data), must cite labels;
  unknown labels are dropped; quotes/numbers missing from the inputs are flagged in the reply.
  Optional general knowledge is returned in a separate `general_context` field and shown with the
  label "General background from the AI model — not from the collected coverage".
- Reuse: a first question on unchanged inputs is cached (`ai_answers`), so identical questions from
  any reader return the stored answer (`"cached": true`) without a model call.
- Limits: 8 questions / 5 min per client and `ASK_DAILY_LIMIT` (150) per day, leaving free-tier quota
  for the hourly analyses. Questions with no matching coverage are answered without calling the model.
- Retention: cached answers are deleted when any of their story's articles expire, when the story is
  deleted, and after 24 h; global answers are cleared on every expiration run.
- Prompts: `backend/ai_config/ask_story_prompt.md`, `ask_global_prompt.md`.

## 5. Setup, build and deploy (Windows PowerShell)

### 5.1 Backend locally
```powershell
cd backend
py -3.12 -m venv .venv            # or: & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env            # optional; without DATABASE_URL a local SQLite file is used
.\.venv\Scripts\python.exe -m pytest -q                      # tests
.\.venv\Scripts\python.exe -m scripts.collect                # one live collection run
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000   # http://localhost:8000/docs
```

### 5.2 Database (Supabase)
Create a free project → **Project Settings → Database → Connection string → Session pooler**
(IPv4-compatible) → use it as `DATABASE_URL`. Tables are created automatically on API startup;
`backend/migrations/001_init.sql` contains the same DDL if you prefer the SQL editor.

### 5.3 API (Render) and scheduler (GitHub Actions)
1. Push this repository to GitHub.
2. Render → **New → Blueprint** → select the repo (uses `render.yaml`) → enter `DATABASE_URL`,
   `ADMIN_TOKEN`, `GEMINI_API_KEY`. Wait for `/health` to return `{"status":"ok"}`.
3. GitHub → Settings → Secrets and variables → Actions → add `NEWSVISTA_API_URL`
   (e.g. `https://newsvista-api.onrender.com`) and `NEWSVISTA_ADMIN_TOKEN`.
4. Actions → "Hourly news collection" → **Run workflow** once. After that it runs at minute 7 of
   every hour. Evidence: Actions run logs and `GET /status` (`trigger: "schedule"`).

### 5.4 Flutter app
```powershell
cd flutter_app
flutter pub get
flutter analyze
flutter test
flutter build apk --release --dart-define=API_BASE_URL=https://YOUR-API.onrender.com
adb install -r build\app\outputs\flutter-apk\app-release.apk
```
The release build is signed with the debug key (fine for side-loaded beta testing; not for Play Store).

## 6. API

Base URL: deployed Render URL. Interactive docs at `/docs` (OpenAPI).

| Method | Path | Description |
|---|---|---|
| GET | `/health` | `{"status":"ok","database":"ok","time":...}` |
| GET | `/stories?limit=50&offset=0&min_publishers=1&category=world&q=alberta` | Story list, newest first (by latest article time; the app shows the newest story covered by 2+ publishers as the "TOP STORY" card, then the rest newest first), only articles inside 168 h. `limit` ≤ 100. Optional `category` (`top`/`world`/`politics`/`us`, from feed sections) and `q` (words matched in titles/excerpts). Items include `summary` (lead publisher excerpt, labelled), `image_url`, `categories`. |
| GET | `/stories/{id}` | Full story: overview (AI or labelled publisher excerpt), publishers → articles (title, URL, time, excerpt), background, analysis. 404 if unknown or fully expired. |
| GET | `/status?runs=20` | Last runs (trigger, status, counts, per-feed results), last successful collection, AI call counts. |
| POST | `/stories/{id}/ask` | Ask AI about one story. Body `{"question": "...", "history": [{"role":"user|assistant","text":"..."}]}`. Returns `answer`, numbered `citations` (articles/background with URLs), `general_context` (+label), `follow_up_questions`, `flag`, `cached`, `model`, `generated_at`. 422 bad question, 404 story gone, 429 rate limit, 503 AI busy. |
| POST | `/ask` | Ask AI about recent news (same body/response; citations point to `story_id`s). |
| POST | `/admin/collect?max_ai=N` | **Protected** (`Authorization: Bearer <ADMIN_TOKEN>`). Runs one collection. Header `X-Trigger: schedule|workflow_dispatch|manual`. 401 bad token, 409 run in progress, 503 if no token configured. |

Example `GET /stories` item:
```json
{"id":"st_88f56af13df9","headline":"UK to deploy jets to defend Saudi Arabia from Houthi attacks",
 "latest_published_at":"2026-10-20T18:30:16Z","updated_at":"2026-10-20T23:22:59Z",
 "publisher_count":3,"article_count":3,"publishers":["BBC News","Fox News","The Guardian"],
 "ai_status":"pending"}
```
List envelope: `served_at`, `window_hours`, `ordering`, `last_successful_collection_at`, `total`, `limit`, `offset`, `items`.

Example `GET /stories/{id}` (abridged):
```json
{"id":"st_88f56af13df9","headline":"...","publisher_count":3,"article_count":3,
 "overview":{"kind":"publisher_excerpt","label":"Publisher excerpt — BBC News (original wording)","text":"...","generated_at":null},
 "publishers":[{"publisher":"BBC News","article_count":1,"articles":[{"id":"7cdddf9c33fb2ab02401","title":"...","url":"https://www.bbc.co.uk/news/articles/...","published_at":"2026-10-20T13:54:35Z","excerpt":"...","excerpt_label":"Excerpt from BBC News's RSS feed (original wording)"}]}],
 "background":{"status":"available","message":null,"links":[{"title":"Saudi Arabia","description":"Country in West Asia","url":"https://en.wikipedia.org/wiki/Saudi_Arabia","provider":"Wikipedia","matched_term":"Saudi Arabia","method":"entity"}]},
 "analysis":{"label":"AI-generated","status":"current","status_message":"...","analysis_id":12,"version":1,"generated_at":"...","model":"gemini-2.5-flash",
   "content":{"overview":{"text":"...","citations":[1,2]},"agreements":[{"text":"...","citations":[1,3]}],"disagreements":[],"uncertainties":[],
     "perspectives_status":"supported","perspectives":[{"id":"p1","name":"...","summary":"...","claims":[{"text":"...","citations":[2]}],"caveats":"..."}],
     "limitations":["..."],"input_scope":{"kind":"mixed","article_count":3,"publisher_count":3,"disclosure":"Input scope: ..."},
     "needs_review":false,"review_notes":[],"citations":[{"number":1,"article_id":"...","publisher":"BBC News","title":"...","url":"...","published_at":"..."}]}},
 "window_hours":168,"last_successful_collection_at":"...","served_at":"..."}
```
Errors: `{"detail": "..."}` (4xx) or `{"error":"database_unavailable"|"internal_error","message":...}` (5xx); no stack traces.
Timeouts: feeds 15 s, Wikipedia 10 s, Gemini 90 s. CORS is off by default (native app needs none).

## 7. Flutter app
**Design:** Inter typeface (bundled, OFL licence), custom launcher icon (`flutter_app/tool/make_icons.py`),
skeleton loading placeholders, image hero transition from list to story, headline appears in the
top bar when scrolled, and an offline copy of the last results (see below).
Dark editorial theme following the NewsVista mockup (palette #0F172A, #2563EB, #8B5CF6,
#10B981, #E2E8F0). Home: logo header, category chips (Top Stories · Multi-source · World · Politics ·
U.S. — taken from the real feed sections), "TOP STORY" hero card, thumbnail rows, bottom nav
(Home · Search · About). Story: hero image, publisher badges, tabs **Overview** (Quick Summary + Key
Details) · **Sources** (Original Coverage + "Why different coverage?") · **Background** (Wikipedia cards)
· **AI Analysis** (AI Overview, Agreement / Disagreement / Uncertainty, viewpoints, citations).
Deliberate differences from the mockup: "BREAKING" → "TOP STORY" (we cannot verify breaking news);
"Publisher Perspectives" → "Perspectives"/"Viewpoints" (viewpoints are never assigned by publisher);
no "Tech" chip (no tech feed); no Bookmarks (out of MVP scope). Images are the ones publishers put
in their RSS feeds (hot-linked, optional, with a placeholder when missing) and Wikipedia thumbnails.

**Test in a browser first** (same Dart code as the phone app):
```powershell
# terminal 1 — API with browser access allowed
cd backend; $env:CORS_ORIGINS="http://localhost:5050"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8077
# terminal 2 — app in Chrome with hot reload
cd flutter_app; flutter run -d chrome --web-port 5050 --dart-define=API_BASE_URL=http://localhost:8077
```

**OneDrive note:** Android (Gradle) builds inside a OneDrive folder can fail with "Cannot snapshot …
not a regular file". Build from a copy outside OneDrive:
`robocopy flutter_app C:\dev\newsvista\flutter_app /MIR /XD build .dart_tool` then build in `C:\dev\newsvista\flutter_app`.

Previous screen list: **Top stories** (collection time, refresh, pull-to-refresh, Top/Multi-source filter, one
card per story with headline, latest article time, distinct-publisher count; loading/empty/error/retry;
"server waking up" hint) → **Story** (overview labelled *AI-generated* or *Publisher excerpt*;
Original coverage: one button per covering publisher, chooser when a publisher has several articles;
Background buttons or "No background resource available"; AI analysis entry with status) →
**AI analysis** (AI-generated label + time + model, overview with tappable [n] citations,
agree/differ/uncertain, perspective buttons or "Insufficient evidence…", supporting articles,
input-scope disclosure, limitations, automated fact-check notes) → **Perspective** (claims with
citations, evidence & limits, supporting coverage, switch viewpoint, back). **About** shows version,
feedback route and the server collection log. Links open in the browser; Back returns to the same
screen.

**Offline mode (PDF §6, optional):** the last story lists and up to 40 opened stories are saved on the
phone (`shared_preferences`, server JSON only). When the server can't be reached the app shows them
with an "Offline · showing content saved N min ago" banner. The 168-hour window is still applied
while offline: expired stories/articles are hidden, and a saved AI analysis that relied on an expired
article is hidden (same rule as the server). Publisher pages need a connection.

## 8. Services, quotas and costs (as of Oct 2026 — check current pricing pages)
| Service | Use | Free-tier notes |
|---|---|---|
| Render (web service, free) | API | Sleeps after ~15 min idle; first request ~30–60 s (app shows a "waking up" hint and waits up to 75 s). 750 instance-hours/month. |
| Supabase (free) | PostgreSQL | 500 MB DB; projects pause after 7 days of inactivity (the hourly job keeps it active). |
| GitHub Actions | Hourly trigger | Free for public repos; private repos have 2,000 min/month (each run ≈ 1–3 min → ~1,500 min/month). Cron is best-effort and may be delayed or skipped. |
| Google Gemini API | AI analysis | Free tier has per-minute and per-day request limits that vary by model; we cap at 6 calls/run (≤ 144/day) and 7 s spacing. Paid usage would cost cents per day at this volume. |
| Wikipedia API | Background | Free; ≤ 25 requests/run at 1 req/s with a descriptive User-Agent. |
| RSS feeds | News | Free; we store headline, feed excerpt, link and limited feed text, and send readers to the publisher. |
Expected cost for the beta: **$0/month** on free tiers.

## 9. Known limitations
- Grouping is lexical; see failure cases in §4.3. Thresholds favour separate stories over wrong merges.
- AI input is RSS excerpts/partial feed text, not full articles — disclosed in the app on every analysis.
- AI output passes automated checks, but checks cannot prove every paraphrase is faithful; manual review results are in `docs/AI_REVIEW.md`.
- Only ≤ 6 analyses are generated per hour; less-covered single-publisher stories may show "not generated yet" for several hours.
- Background links come only from Wikipedia and are limited to exact-name matches; many stories show "No background resource available" by design.
- Free Render instance cold starts (~30–60 s) on the first request after idle.
- No offline cache: without a connection the app shows a retry state.
- GitHub cron timing is best-effort (runs can be minutes late or occasionally skipped).

## 10. Release notes — v1.0.0 (beta)
**Features:** hourly collection from 5 publishers; one card per event; per-publisher buttons with
article chooser; Wikipedia background with relevance checks; cached, cited AI overview with
agreement/disagreement/uncertainty and evidence-based perspectives; honest status for pending /
outdated / failed AI; 7-day window enforced on every request; server collection log in the app.
**Known minor issues:** see §9 and the defect log.
**Report problems:** open an issue in this GitHub repository (or email the address configured via
`--dart-define=FEEDBACK_EMAIL=...`) with the story headline, time, and a screenshot.

## 11. Defect log
| ID | Severity | Found | Steps to reproduce | Status / verification |
|---|---|---|---|---|
| D1 | Critical | 2026-10-20 local live run | Run `scripts.collect` on empty DB → every source "failed" with `TypeError` (per-source counters were `None` before insert) | Fixed (counters kept locally, merged after commit). Verified: live run `success`, 263 articles. |
| D2 | Major | 2026-10-20 live calibration | Group live feeds at threshold 0.30 → Kenya Ebola story merged with Nigeria Ebola case | Fixed (0.33 / 0.40 single-entity rule). Verified on same 262-article sample: no longer merged. |
| D3 | Major | 2026-10-20 background check | Background for live stories → "Fairbarn"→"Fairbairn (surname)", "Jane Doe"→"John Doe", "Gov"→"Government" | Fixed (redirect name check, surname/placeholder/generic filters). Verified on fresh live run. |
| D4 | Major | 2026-10-20 live run | Wikipedia returned HTTP 429 for all lookups (generic User-Agent + burst) | Fixed (descriptive UA, 1 req/s, stop on 429). Verified: 35 links added, 0×429. |
| D5 | Major | 2026-10-20 fixture test | "Ghana parliament approves…" + "Ghana passes…" not grouped: sentence-initial "Ghana" not detected as entity | Fixed (possessive / mid-sentence capital rule). Verified: `test_fixture_groups_match_expected_partition` passes; live grouping unchanged. |
| D6 | Minor | 2026-10-20 | NPR digest headline joins France-protests story | Open — documented limitation (§4.3). |
| D7 | Major | 2026-10-21 emulator | Story screen → AI Analysis tab → scroll: content slid under the pinned tab bar (NestedScrollView overlap) | Fixed (single CustomScrollView with pinned tab bar). Verified on Pixel_8 emulator screenshot. |
| D8 | Minor | 2026-10-21 widget test | Long tab heading ("Background Information") overflowed on narrow screens / large fonts | Fixed (heading wraps). Verified: `flutter test` 7/7 pass on a 412×915 test screen. |
| D9 | Major (build) | 2026-10-21 | `flutter build apk` inside OneDrive → "Cannot snapshot … not a regular file" | Workaround: build from `C:\dev` copy (README §7). Verified: debug APK builds there. |
| D10 | Minor | 2026-10-21 | Same Alberta referendum event split into separate stories when follow-up articles share few terms with earlier ones | Open — false split is preferred over false merge (§4.3). |
| D11 | Critical | 2026-10-21 first AI run | With a new API key, all 10 AI calls failed: `gemini-2.5-flash` returned 404 "no longer available to new users"; newer models returned 503 "high demand" | Fixed: model `gemini-3.6-flash` (low thinking) with fallbacks `gemini-3.5-flash-lite`, `gemini-3.8-flash`; 503/timeout now try the next model; failed attempts retried after 1 h. App showed honest "unavailable" status throughout. Verified: 10/10 analyses generated, 0 flagged by validation. |
| D12 | Minor | 2026-10-21 emulator | AI tab: citation chips stretched to full width and blue-on-blue text was hard to read | Fixed (chips size to content, lighter text). Verified on emulator screenshot. |
| D13 | Minor | 2026-10-21 emulator | Ask AI: long follow-up suggestions were cut off mid-word in single-line chips | Fixed (wrapping pills). Verified on emulator. |
| D14 | Minor | 2026-10-21 emulator | Ask AI tab: "Automated check: the number 1 was not found" on a correct answer; the checker read our own [1] citation markers as numbers | Fixed (markers ignored by the number check) + regression test `test_citation_markers_are_not_treated_as_numbers`. Verified live: same question returns no flag. |
| D15 | Major (rubric) | 2026-10-21 review | Only 1 of 10 live analyses had supported perspectives (PDF needs >= 3 demonstrable stories); the prompt's definition of a viewpoint was too narrow | Fixed: prompt `analysis-v3` defines a perspective as a position attributed to an identifiable actor (officials, critics, unions, families...), still forbidding invented opposition and publisher-based viewpoints. Verified: 3 of 12 regenerated analyses supported (Jalen Hurts: NFL vs NFLPA; Saudi/Houthis; Hubbard), others honestly "insufficient evidence". |
| D16 | Minor | 2026-10-21 emulator | TOP STORY card could be a single-source story without an image | Fixed: top story = newest story covered by 2+ publishers (documented ordering). Verified on emulator. |
| D17 | Major | 2026-10-21 release build on live data | Top story showed a placeholder: NPR feeds link 14 MB, 8116x5410 originals that are too large to load | Fixed: server requests NPR images at 1200px JPEG (~108 KB) and the app decodes images at display size. Regression test `test_npr_images_requested_at_phone_size`. |
