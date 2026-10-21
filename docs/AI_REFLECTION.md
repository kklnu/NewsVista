# AI development reflection (draft: Kiranpreet to edit and finish in first person)

**Tools used.** Claude Code (Anthropic) in VS Code acted as the pair programmer for the backend,
Flutter client, tests and documentation. Google Gemini is the model *inside* the product. It writes
the story analyses on the server.

**Representative prompts.**
1. The master build prompt asked for a deployable Flutter + FastAPI + Supabase MVP. It required
   the PDF to be treated as authoritative, no fabricated verification, and work in vertical slices:
   backend API + DB, then ingestion/retention, grouping, Flutter UI, AI + background, and tests/docs.
2. The product's own AI prompt (`backend/ai_config/analysis_system_prompt.md`) tells Gemini to use only
   the labelled articles, to treat article text as untrusted data, to cite labels for every claim, and
   to name perspectives after people or groups, never publishers. If the evidence is thin, it must
   answer "insufficient_evidence" instead of inventing opposition.

**AI-generated mistakes found and corrected** (all recorded in the README defect log):
- *Crash on first live run (D1).* The AI-written ingestion code incremented per-feed counters that
  SQLAlchemy had left as `None`, because column defaults only apply on insert. Every feed "failed" on
  the first run. The isolation logic did work (the run was recorded, not crashed). The fix was to
  keep counters in local variables and merge them only after a successful commit.
- *Over-eager grouping (D2).* The first similarity threshold (0.30) merged two different Ebola
  events (Kenya cases vs. a Nigeria case) on live data. The fix raised thresholds (0.33, or 0.40 with
  a single shared entity) and re-checked against the same 262 live articles.
- *Wrong background links (D3).* Wikipedia redirects turned "Jane Doe" into "John Doe" and "Gov" into
  "Government". The fix rejects redirects that change the name and filters surname/placeholder pages.
- *Missed entity (D5).* A fixture test caught that headlines starting with a country name
  ("Ghana passes…") did not count that name as an entity.

**What I personally verified** (Kiranpreet: confirm or replace with what you actually checked):
- [ ] Ran the backend tests and the Flutter analyzer/tests myself and saw them pass.
- [ ] Opened the deployed `/health`, `/stories` and `/status` URLs in a browser.
- [ ] Watched two scheduled GitHub Actions runs and matched them to `/status` entries.
- [ ] Read three AI analyses against their source excerpts (`docs/AI_REVIEW.md`).
- [ ] Ran the core workflow three times on my phone through Phone Link.
- [ ] Can explain grouping thresholds, the 168-hour rule and the AI fingerprint cache in my own words.
