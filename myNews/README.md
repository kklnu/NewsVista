# myNews

myNews is a small, beginner-friendly news reader made with plain HTML, CSS, and JavaScript.

It shows RSS headlines and summaries from FOX, NPR, and BBC with no ads, no images, and no account-based sources. Stories are saved in browser local storage, refreshed without duplicates, and automatically removed only after they are older than 7 days. `Clear all` empties stored stories. By default, the app displays articles from today and yesterday, with day buttons such as `Tue`, `Mon`, and `Sun` for choosing which days to show. Keywords are readable terms from article titles. Articles are shown newest first.

The app also includes a local Simple English toggle. It simplifies headlines and summaries in the browser without a server, paid API, or API key.

## Files

- `index.html` - page structure
- `style.css` - simple styling
- `app.js` - RSS loading, storage, filtering, and source management

## Run It

Open `index.html` in a browser.

For the most reliable RSS loading, run a small local web server from this folder and then open the local address in your browser:

```powershell
python -m http.server 8000
```

Then visit:

```text
http://localhost:8000
```

The app keeps a local backup in your browser, so previously loaded stories remain available even if a feed cannot be reached later.
