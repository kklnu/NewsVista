# Manual review of three AI-generated analyses

**Status: NOT DONE YET.** No live AI analyses exist yet. The Gemini API key had not been
configured on 2026-10-20, so the server correctly reports `pending` and shows no AI text.

## How to do the review (≈ 20 min, after the key is set and one collection has run)
1. Pick three multi-publisher stories with `ai_status: current`. Use
   `GET /stories?min_publishers=2` or the app's "Multi-source" filter. Prefer stories with perspectives.
2. For each story, open `GET /stories/{id}`. Then compare every overview sentence, agreement,
   disagreement and perspective claim against the cited articles' **feed excerpts** (in the same JSON)
   and the publisher pages.
3. Fill in the table below. For an unsupported claim, note it and fix it via the release process:
   tighten the prompt in `backend/ai_config/analysis_system_prompt.md`, bump `prompt_version` in
   `model_config.json` (this regenerates every analysis), and re-check.

## Review template (copy three times)

### Story N: <headline> — `<story id>` · analysis v<version> · generated <time> · model <model>
| Item | AI text | Supported by cited input? | Notes / correction |
|---|---|---|---|
| Overview | | Yes / Partly / No | |
| Agreement 1 | | | |
| Disagreement 1 | | | |
| Perspective "<name>" claim 1 | | | |
| Perspective "<name>" claim 2 | | | |

- **Unsupported claims found:**
- **Missing context (important facts in the inputs that the AI left out):**
- **Perspective quality** (truly distinct groups? named after people, not publishers?):
- **Automated fact checks (`review_notes`)** and whether they were right:
- **Correction applied and re-check result:**
