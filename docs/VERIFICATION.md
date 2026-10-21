# Verification evidence

Rule: only results actually observed are recorded. Anything not yet tested is **NOT VERIFIED**.
Environment for local results: Windows 11, Python 3.12.10, Flutter 3.47.2, SQLite (local DB),
live RSS feeds and live Wikipedia API, date 2026-10-20.

| # | Check (PDF §10) | Method | Result | Evidence |
|---|---|---|---|---|
| 1 | Repeated ingestion | Live: `scripts.collect` twice on same DB. Test: `test_repeated_ingestion_does_not_duplicate` | **PASS (local)** — run 2: `articles_new 0`, `articles_unchanged 277`, `articles_updated 1`; 263 articles / 238 stories before and after; 0 duplicate normalized URLs | Run JSON below; pytest |
| 2 | Same event, different publishers | Live grouping + fixture test (6 multi-publisher events) + emulator | **PASS (local)** — 15 live multi-publisher groups; fixture partition exact; emulator shows CBS + Guardian buttons on one story | §Grouping examples; `test_fixture_groups_match_expected_partition`; emulator screenshot of story detail |
| 3 | Similar topic, different events | Fixture pairs (4) + live calibration | **PASS (local)** — 4/4 fixture pairs separate; live Kenya vs Nigeria Ebola stories separate after threshold fix | `test_similar_topic_distinct_events_stay_separate`; README D2 |
| 4 | Hourly automation (2 consecutive scheduled runs) | GitHub Actions cron → deployed API | **NOT VERIFIED** — not deployed yet | Record Actions run URLs + `/status` runs with `trigger: schedule` here |
| 5 | Seven-day boundary | Controlled clock test | **PASS (test)** — item at 167 h listed; 2 h later hidden by API before cleanup; next run deletes it (`articles_expired 1`, `stories_deleted 1`) | `test_seven_day_boundary_api_filter_and_cleanup` |
| 6 | Source expiration inside a group | Controlled clock, 3-publisher story with AI | **PASS (test)** — expired publisher button disappears; analysis status `expired_inputs` (content hidden) between runs; next run invalidates + regenerates from 2 retained articles; citations only NPR/Fox | `test_expiration_inside_group_removes_source_and_regenerates_ai` |
| 7 | Shared AI output | Two API clients, repeated reads, call counter | **PASS (test)** — same `analysis_id`, `version`, `generated_at`; model calls stay 1; unchanged rerun = 0 calls | `test_shared_ai_output_reused_by_two_clients_without_model_calls`. Live: **NOT VERIFIED** (needs Gemini key) |
| 8 | Provider failure | Feed HTTP 503 / total outage; AI quota error | **PASS (test)** — run `partial`, failed feed recorded, stories kept; total outage keeps stories; AI failure → status `failed`, publisher excerpt shown, no fake text | `test_feed_failure_is_isolated_and_recorded`, `test_ai_failure_shows_honest_status_and_keeps_story` |
| 9 | Client connectivity failure | Widget test (HTTP 500) | **PASS (widget test)** — "Could not load stories" + Try again. On-phone airplane-mode test: **NOT VERIFIED** | `flutter test` |
| 10 | Physical-phone presentation | Release APK on phone + Phone Link | **NOT VERIFIED** — no phone connected yet | Fill in device, build, date |
| 11 | Beta regression (3 core-workflow runs) | On phone against deployed API | **NOT VERIFIED** | Table below |
| 12 | Source fidelity | Excerpts labelled "original wording"; AI validation (citations/quotes/numbers) | **PASS (test)** for validation rules; manual review of 3 live AI outputs **NOT VERIFIED** (needs Gemini key) | `test_ai_validation.py`; `docs/AI_REVIEW.md` |

Automated suites (2026-10-20): backend `pytest` → **25 passed**; Flutter `flutter analyze` → **No issues
found**; `flutter test` → **6 passed**. Emulator (Pixel_8, Android 16 image, debug build against local API):
home list and story detail rendered with live data.

## Live run record (local, 2026-10-20 ~23:22 UTC)
```
run 1: status success · fetched 280 · new 263 · unchanged 15 (same article in 2 feeds) · skipped_too_old 2
       stories_created 238 · background_links_added 35 · ai_deferred 238 (no GEMINI_API_KEY → AI honestly "pending")
run 2: status success · fetched 280 · new 0 · updated 1 · unchanged 277 · stories_created 0
```

## Grouping examples (LIVE data, 2026-10-20, local run)
Multi-publisher groups (≥ 2 publishers): Alberta independence referendum (NPR ×2, Guardian ×2, BBC);
attack on Australian MP Helen Haines (Guardian ×3, BBC); UK jets to defend Saudi Arabia from Houthis
(Fox, BBC, Guardian); Jalen Hurts blood clot (Guardian ×2, CBS); Ohio governor race ad / Amy Acton
(Guardian, CBS ×2); Pope Leo XIV returns after surgery (BBC, Fox); Limoges town hall fire (Fox, BBC);
Houthi strike on Yemen camp (Guardian, BBC); Las Vegas flamingo theft verdict (BBC, Guardian); World
Series Rays–Brewers (NPR, Fox); Russell Brand trial (BBC, Guardian); Italy protests/Meloni (Fox, Guardian).

Related topics kept separate (live): Kenya Ebola cases (Guardian) vs. Nigeria's first Ebola case (NPR);
the Houthi strike in Yemen vs. UK jets to Saudi Arabia (both Houthi-related, separate stories).
Known wrong merge (live): NPR digest "2026 midterms… And, Macron condemns protests" joined the France protests story.

Fixture examples (CONTROLLED, not live): see `backend/tests/fixtures/grouping_fixtures.json`.

## Phone runs (to fill in)
| Run | Date/time | Device / Android | APK build | API URL | Launch → list → story → publisher → background → AI → perspective → back | Defects |
|---|---|---|---|---|---|---|
| 1 | | | 1.0.0+1 | | NOT VERIFIED | |
| 2 | | | | | NOT VERIFIED | |
| 3 | | | | | NOT VERIFIED | |
