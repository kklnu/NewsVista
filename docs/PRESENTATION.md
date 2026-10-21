# NewsVista: 6-minute presentation script and checklist

## Before class (the night before + 15 min before)
- [ ] Phone: Do Not Disturb ON, notifications hidden, brightness up, font size normal, battery > 60%.
- [ ] Phone Link open on the laptop and mirroring the phone screen. Rehearse once.
- [ ] Open the app once 2–3 minutes before presenting, so the free Render server is awake.
- [ ] Browser tabs ready: GitHub Actions run list · `https://YOUR-API/status` · Render dashboard · Supabase table view.
- [ ] Backup: a screen recording of one full app run, in case the Wi-Fi fails.

## Script (≈ 6 min)
**0:00 Problem (30 s).** "Readers visit several sites to compare coverage of one event. NewsVista
shows one card per event, with each publisher's original article, background, and a labelled AI
analysis."

**0:30 Architecture (60 s).** Show the README diagram. "The hourly worker runs on our server, not in
the app: fetch 11 feeds from 5 publishers, drop anything older than 168 hours, group articles, call
Gemini only when a story's inputs change, then find Wikipedia background. Everything is stored in
Supabase. The Flutter app only reads `/stories`."

**1:30 Live app on phone via Phone Link (2 min 30 s).**
1. Home: point out "News collected X min ago", newest first, the publisher counts, and pull to refresh.
2. Switch to **Multi-source** and open a 3-publisher story.
3. Overview label (AI-generated vs. publisher excerpt). **Original coverage:** tap one publisher, the
   browser opens, press Back, and you return to the same story.
4. **Background:** tap a Wikipedia link, then Back. Show a story with "No background resource available".
5. **View AI analysis:** point out the AI-generated label and time, the citations [1][2], the
   agree/differ/uncertain sections, and the input-scope disclosure. Open a perspective, tap
   "Switch viewpoint", then Back.

**4:00 Evidence of the server (60 s).** GitHub Actions: two scheduled runs. `/status`: the same runs
with `trigger: schedule`, plus counts and per-feed results. In-app **About → Server collection log**.

**5:00 Shared results (30 s).** "Two phones opening this story get the same `analysis_id` and
`generated_at`. GET requests never call the model, and our test proves the call count stays at 1."

**5:30 Honesty & limits (30 s).** "Failed or outdated AI is labelled, never faked. Expired sources
disappear right away. A known grouping mistake: digest headlines. One AI mistake we fixed: ..."

**6:00 Questions.**

## Likely questions
- *How do you prevent duplicates?* Normalized URL → hash ID, plus a unique constraint, so a re-fetch updates the row.
- *Why not group by keyword?* One shared word isn't enough. We use TF-IDF similarity plus a shared specific name, at most 72 h apart.
- *What if Gemini is down?* The status shows "unavailable", original sources still work, and the next run retries.
