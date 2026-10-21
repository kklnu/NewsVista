# NewsVista: 6-minute presentation script and checklist

## Links to have open (browser tabs, in this order)
1. **App (web version):** https://kklnu.github.io/NewsVista/  (also on your iPhone home screen)
2. **Server status / evidence:** https://newsvista-api.onrender.com/status
3. **Scheduled runs:** https://github.com/kklnu/NewsVista/actions
4. **API docs:** https://newsvista-api.onrender.com/docs
5. **Code:** https://github.com/kklnu/NewsVista
6. *(Backup)* Android emulator with the release APK, if asked about the native build

## 10 minutes before
- [ ] Open the app link once (wakes the free server; first load can take ~50 s).
- [ ] iPhone: Do Not Disturb ON, brightness up. Open NewsVista from the home screen.
- [ ] If showing the iPhone on the laptop: start the AirPlay receiver (e.g. LetsView) and mirror.
- [ ] Check `/status` shows a recent "Last successful collection".

## Script (~6 min)
**0:00 Problem (30 s).** "The same event is covered by many outlets. Readers jump between sites
to compare. NewsVista shows **one card per event**, with each publisher's original article,
background links, and an AI analysis that is clearly labelled."

**0:30 How it works (60 s).** Use the diagram in `docs/HOW_IT_WORKS.md`:
"Every hour GitHub Actions calls our Python server on Render. The server reads RSS feeds from BBC,
NPR, Fox News, The Guardian and CBS, removes duplicates and anything older than 7 days, groups
articles about the same event, asks Google Gemini for an analysis only when a story changed, finds
Wikipedia background, and saves everything in a Supabase database. The app only **reads** those
saved results. It never calls the news sites or the AI itself, so one AI summary is shared by
everyone."

**1:30 Live demo (2 min 30 s).**
1. Home: "Updated X min ago", 230+ stories, **TOP STORY** covered by 4 publishers, the publisher
   badges, the **Multi-source** filter.
2. Open the top story. **Overview:** Quick Summary labelled *AI-generated* (or *Publisher excerpt*),
   Key Details with citations.
3. **Sources tab:** one card per publisher that covered it. Tap one, the original article opens, go back.
4. **Background tab:** Wikipedia cards. Mention: "If nothing clearly matches, it says *No background
   resource available* instead of a random link."
5. **AI Analysis tab:** AI-generated label + time, citations [1][2], Agreement / Disagreement /
   Uncertainty, a **Viewpoint** (e.g. NFL vs. the players' union), and the input-scope note
   ("only RSS excerpts").
6. **Ask AI:** tap the purple button and ask "What led up to this?". Show the answer with citations.

**4:00 Proof it's a real server (60 s).** Show `/status`: the run log with times, article counts,
`trigger: schedule` runs (hourly, no app open), and AI call counts. Show GitHub Actions runs.

**5:00 Shared results + honesty (40 s).** "Two people opening the same story see the same stored
analysis (same id and time); opening it never calls the AI again. If the AI or a feed fails, the app
says so instead of showing made-up text. Old news (7+ days) disappears automatically."

**5:40 Limits + AI use (20 s).** "Grouping can merge digest headlines; AI only sees short excerpts.
I built this with an AI coding assistant (Claude Code), and then tested and verified it myself."

**6:00 Questions.**

## Likely questions (short answers)
- **Why web on the iPhone?** iPhone apps need a Mac to build, and Phone Link can't mirror iPhones.
  The same Flutter code is built as an Android APK (the required native client); the web version is
  an extra.
- **How do you stop duplicates?** Each article's link is cleaned and turned into an ID; fetching it
  again updates the same row.
- **How do you know two articles are the same event?** They must share specific names, have similar
  wording, and be published within 72 hours. One shared keyword isn't enough.
- **What if Gemini is down?** The status says "unavailable", the sources still work, and the next
  hourly run retries (with backup models).
- **Cost?** $0. Everything runs on free tiers.
