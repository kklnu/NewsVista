# NewsVista: how it works (study sheet for the presentation)

## The one-sentence pitch
NewsVista collects news from 5 publishers every hour, groups articles about the **same event** into
one story, and shows each story with its original sources, background links, and an AI analysis
that every reader shares.

## The parts (what each tool is and why we use it)

| Part | Tool | What it does | Why this tool |
|---|---|---|---|
| Phone app | **Flutter** (Dart language) | The screens you see: story list, story page, AI analysis, Ask AI chat | Required by the assignment; one codebase for Android (and web for testing) |
| Server / API | **Python + FastAPI** | Collects news, groups it, stores it, and answers the app's requests (`/stories`, `/stories/{id}`) | Python is simple to read; FastAPI makes a web API with automatic docs at `/docs` |
| Database | **Supabase** (PostgreSQL) | Permanently stores articles, stories, AI analyses, background links, and run logs | Free hosted PostgreSQL; data survives server restarts |
| Hosting | **Render** | Runs our Python server on the internet 24/7 at a public URL | Free tier, deploys directly from GitHub |
| Scheduler | **GitHub Actions** | Calls our server's protected `/admin/collect` every hour | Free; runs even when nobody has the app open |
| AI model | **Google Gemini** (`gemini-3.6-flash`) | Writes the story summaries, perspectives, and Ask AI answers | Free tier; called **only by the server** with a secret key |
| News sources | **RSS feeds**: BBC, NPR, Fox News, The Guardian, CBS | The raw articles (headline, short excerpt, link, time) | Free, official feeds that publishers provide |
| Background | **Wikipedia API** | Finds reference pages for people/places in a story | Free and reliable |
| Code storage | **GitHub** | Holds all the code; Render and the scheduler use it | Standard for sharing/submitting code |

## How data flows (draw this on a slide)
```
Every hour:  GitHub Actions ──► our server (Render) ──► reads RSS feeds from 5 publishers
                                      │
                                      ├─ removes duplicates & news older than 7 days
                                      ├─ groups articles about the same event into stories
                                      ├─ asks Gemini to write an analysis (only if the story changed)
                                      ├─ finds Wikipedia background links
                                      └─ saves everything in Supabase (database)

Any time:    Phone app ──► asks our server for stories ──► server reads the database ──► app shows them
```
**Key idea:** the phone **never** talks to the news sites or to the AI. It only reads results the
server already stored. So 1 AI summary is reused by every reader, which is cheap and consistent.

## The 6 ideas the grader cares about (and how we did each)
1. **No duplicates:** each article's web address is cleaned up and turned into an ID. Fetching it
   again updates the same row instead of adding a copy.
2. **7-day window:** articles older than 168 hours (by *publication* time) are hidden from the app
   immediately and deleted on the next hourly run, along with summaries that used them.
3. **Grouping:** two articles join the same story only if they share specific names (people, places),
   use similar words (TF-IDF similarity), and were published within 72 hours. One shared keyword
   is not enough. Known mistake: digest headlines that mention two events.
4. **Honest AI:** every AI text says "AI-generated" and when. Each claim cites the articles it came
   from. The server automatically removes quotes or numbers that aren't in the articles. If there
   aren't two real viewpoints, it says "Insufficient evidence for distinct perspectives."
5. **Shared AI results:** the summary is generated once on the server and saved. Opening the app or
   the AI tab never creates a new summary. It's regenerated only when the story's articles change.
6. **Failures:** if one news feed or the AI is down, the rest keeps working and the app shows a clear
   message (for example "AI analysis unavailable"), never fake text. Offline, the app shows saved
   stories with an "Offline" banner.

## Extra feature: Ask AI
A chat on each story ("Ask AI" button) and a general "Ask AI" tab. Your question goes to **our
server**, which answers using only the stored articles and cites them. Any general background from the
AI's own knowledge is labelled separately. Limits stop it from using up the free AI quota.

## How AI was used to build it (for the reflection, be honest)
The app was built with **Claude Code** (an AI coding assistant) from a detailed prompt. My role was
to define the requirements, review the results, test the app on the emulator, phone and browser,
and check the AI summaries against the real articles. AI-made mistakes that testing caught are in
the README defect log (e.g. the first run crashed on every feed; grouping merged two different
Ebola stories; Wikipedia links went to the wrong pages; the AI model was retired by Google).

## Numbers to mention
- 5 publishers, 11 RSS feeds, ~280 articles per run, ~250 stories in 7 days
- 36 backend tests + 11 app tests, all passing
- AI limited to 6 new analyses per hour (free tier), and Ask AI to 150 questions/day
- Cost: $0/month on free tiers
