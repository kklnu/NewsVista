const STORE_KEY = "myNewsStore";
const SELECTED_DAYS_KEY = "myNewsSelectedDays";
const SELECTED_SOURCES_KEY = "myNewsSelectedSources";
const STORE_VERSION = 8;
const MAX_AGE_DAYS = 7;
const FEED_TIMEOUT_MS = 10000;
const RSS_LOADERS = [
  {
    name: "AllOrigins",
    url: (sourceUrl) => `https://api.allorigins.win/raw?url=${encodeURIComponent(sourceUrl)}`,
    type: "xml"
  },
  {
    name: "CodeTabs",
    url: (sourceUrl) => `https://api.codetabs.com/v1/proxy/?quest=${encodeURIComponent(sourceUrl)}`,
    type: "xml"
  },
  {
    name: "RSS2JSON",
    url: (sourceUrl) => `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(sourceUrl)}`,
    type: "json"
  }
];

const defaultSources = [
  { name: "Fox News", url: "https://moxie.foxnews.com/google-publisher/latest.xml?format=xml" },
  { name: "NPR News", url: "https://feeds.npr.org/1001/rss.xml" },
  { name: "BBC World", url: "https://feeds.bbci.co.uk/news/world/rss.xml" }
];

let newsStore = loadStore();
let activeKeyword = "ALL";
let selectedSourceCodes = [];
let selectedDayKeys = loadSelectedDayKeys();

const headlines = document.querySelector("#headlines");
const statusLine = document.querySelector("#status");
const keywordsPanel = document.querySelector("#keywordsPanel");
const keywordList = document.querySelector("#keywordList");
const dayButtons = document.querySelector("#dayButtons");
const sourceFilterButtons = document.querySelector("#sourceFilterButtons");
const sourceCodes = {
  "bbc world": "BBC",
  "fox news": "FOX",
  "npr news": "NPR"
};

selectedSourceCodes = loadSelectedSourceCodes();

document.querySelector("#keywordsButton").addEventListener("click", () => {
  keywordsPanel.hidden = !keywordsPanel.hidden;
  renderKeywords();
});

document.querySelector("#refreshButton").addEventListener("click", refreshAllData);
document.querySelector("#clearAllButton").addEventListener("click", clearAllData);

dayButtons.addEventListener("click", (event) => {
  const dayKey = event.target.dataset.day;

  if (dayKey) {
    toggleSelectedDay(dayKey);
  }
});

pruneOldArticles();
render();

function loadStore() {
  const fallback = {
    version: STORE_VERSION,
    sources: defaultSources,
    articles: [],
    lastUpdated: null
  };

  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY));
    if (!saved || !Array.isArray(saved.articles)) {
      return fallback;
    }

    return {
      ...fallback,
      ...saved,
      sources: defaultSources,
      articles: saved.articles.map(normalizeArticleKeywords)
    };
  } catch {
    return fallback;
  }
}

function saveStore() {
  localStorage.setItem(STORE_KEY, JSON.stringify(newsStore));
}

function freshStore() {
  return {
    version: STORE_VERSION,
    sources: defaultSources,
    articles: [],
    lastUpdated: null
  };
}

function clearAllData() {
  newsStore = freshStore();
  activeKeyword = "ALL";
  selectedSourceCodes = defaultSelectedSourceCodes();
  selectedDayKeys = defaultSelectedDayKeys();
  saveStore();
  saveSelectedDayKeys();
  saveSelectedSourceCodes();
  render();
  setStatus("Cleared all stored news data.");
}

function refreshAllData() {
  activeKeyword = "ALL";
  selectedSourceCodes = defaultSelectedSourceCodes();
  newsStore.sources = defaultSources;
  saveSelectedSourceCodes();
  saveStore();
  render();
  updateNews({ sources: defaultSources });
}

async function updateNews(options = {}) {
  const sources = options.sources || newsStore.sources;
  const statusPrefix = sources.length === 1 ? sources[0].name : "headlines";
  const previousCount = newsStore.articles.length;

  if (sources.length === 0) {
    setStatus("No sources to refresh.");
    return;
  }

  setStatus(`Updating ${statusPrefix}...`);

  const results = await Promise.allSettled(sources.map(fetchSource));
  const newArticles = results
    .filter((result) => result.status === "fulfilled")
    .flatMap((result) => result.value)
    .filter(articleIsInLastSevenDays);
  const failedSources = results
    .map((result, index) => result.status === "rejected" ? sources[index].name : "")
    .filter(Boolean);

  newsStore.articles = mergeArticles(newsStore.articles, newArticles);
  newsStore.lastUpdated = new Date().toISOString();
  pruneOldArticles();
  saveStore();
  render();
  setStatus(refreshStatusText(statusPrefix, sources.length, previousCount, newArticles.length, failedSources));
}

function refreshStatusText(statusPrefix, sourceCount, previousCount, newArticleCount, failedSources) {
  if (failedSources.length === sourceCount) {
    return `Could not refresh ${statusPrefix}. The feed may be unavailable or blocked. ${statusText()}`;
  }

  if (newArticleCount === 0 && sourceCount === 1) {
    return `No recent articles found for ${statusPrefix}. ${statusText()}`;
  }

  const addedCount = Math.max(0, newsStore.articles.length - previousCount);
  const failedText = failedSources.length > 0 ? ` Failed: ${failedSources.join(", ")}.` : "";
  return `Refreshed ${statusPrefix}. ${addedCount} new article${addedCount === 1 ? "" : "s"}.${failedText} ${statusText()}`;
}

async function fetchSource(source) {
  const errors = [];

  for (const loader of RSS_LOADERS) {
    try {
      const feedText = await fetchFeedText(loader.url(source.url));
      return loader.type === "json"
        ? articlesFromJsonFeed(feedText, source)
        : articlesFromXmlFeed(feedText, source);
    } catch (error) {
      errors.push(`${loader.name}: ${error.message}`);
    }
  }

  throw new Error(`${source.name}: ${errors.join(" | ")}`);
}

async function fetchFeedText(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FEED_TIMEOUT_MS);
  let response;

  try {
    response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        Accept: "application/rss+xml, application/atom+xml, application/xml, application/json, text/xml, */*"
      }
    });
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.text();
}

function articlesFromXmlFeed(xmlText, source) {
  const xml = new DOMParser().parseFromString(xmlText, "application/xml");
  const parseError = xml.querySelector("parsererror");

  if (parseError) {
    throw new Error("XML parse failed");
  }

  return [...xml.querySelectorAll("item, entry")]
    .map((item) => articleFromFeedItem(item, source))
    .filter(Boolean);
}

function articlesFromJsonFeed(jsonText, source) {
  const feed = JSON.parse(jsonText);

  if (feed.status && feed.status !== "ok") {
    throw new Error(feed.message || "JSON feed failed");
  }

  if (!Array.isArray(feed.items)) {
    throw new Error("JSON feed had no items");
  }

  return feed.items
    .map((item) => articleFromJsonFeedItem(item, source))
    .filter(Boolean);
}

function articleFromFeedItem(item, source) {
  const title = textFrom(item, "title");
  const link = linkFrom(item);
  const dateText = textFrom(item, "pubDate") ||
    textFrom(item, "updated") ||
    textFrom(item, "published") ||
    textFrom(item, "date");
  const date = dateText ? new Date(dateText) : null;

  if (!title || !link || !date || Number.isNaN(date.getTime())) {
    return null;
  }

  const paragraphs = plainParagraphs(
    textFrom(item, "description") ||
    textFrom(item, "summary") ||
    textFrom(item, "content") ||
    textFrom(item, "encoded")
  );

  return {
    id: `${source.url}|${link}`,
    title,
    link,
    source: source.name,
    sourceUrl: source.url,
    date: date.toISOString(),
    keywords: keywordsFromTitle(title),
    paragraphs
  };
}

function articleFromJsonFeedItem(item, source) {
  const title = (item.title || "").trim();
  const link = (item.link || item.guid || "").trim();
  const dateText = item.pubDate || item.updated || item.published || item.isoDate || "";
  const date = dateText ? new Date(dateText) : null;

  if (!title || !link || !date || Number.isNaN(date.getTime())) {
    return null;
  }

  const paragraphs = plainParagraphs(item.description || item.content || "");

  return {
    id: `${source.url}|${link}`,
    title,
    link,
    source: source.name,
    sourceUrl: source.url,
    date: date.toISOString(),
    keywords: keywordsFromTitle(title),
    paragraphs
  };
}

function normalizeArticleKeywords(article) {
  return {
    ...article,
    keywords: keywordsFromTitle(article.title || article.source || "")
  };
}

function keywordsFromTitle(title) {
  const stopWords = new Set([
    "about", "after", "again", "against", "amid", "among", "and", "are", "around",
    "because", "before", "being", "between", "but", "can", "could", "during",
    "for", "from", "has", "have", "her", "his", "how", "into", "its", "may",
    "more", "new", "not", "now", "off", "one", "out", "over", "say", "says",
    "she", "that", "the", "their", "them", "they", "this", "through", "to",
    "under", "was", "who", "why", "will", "with", "you"
  ]);
  const cleanTitle = stripHtml(title)
    .replace(/['’]s\b/g, "")
    .replace(/[^A-Za-z0-9\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const keywords = [];

  cleanTitle.split(/\s+/).forEach((word) => {
    const cleaned = word.replace(/^-+|-+$/g, "");
    const lower = cleaned.toLowerCase();

    if (!cleaned || stopWords.has(lower) || /^\d+$/.test(cleaned) || cleaned.length < 3) {
      return;
    }

    const label = /^[A-Z]{2,}$/.test(cleaned)
      ? cleaned
      : lower.charAt(0).toUpperCase() + lower.slice(1);

    if (!keywords.includes(label)) {
      keywords.push(label);
    }
  });

  return keywords.slice(0, 4).length > 0 ? keywords.slice(0, 4) : ["News"];
}

function textFrom(parent, selector) {
  const directMatch = [...parent.children].find((child) => {
    return child.tagName.toLowerCase().split(":").pop() === selector.toLowerCase();
  });

  return directMatch ? directMatch.textContent.trim() : "";
}

function linkFrom(item) {
  const rssLink = textFrom(item, "link");
  if (rssLink) {
    return rssLink;
  }

  const atomLink = item.querySelector("link[href]");
  return atomLink ? atomLink.getAttribute("href") : "";
}

function plainParagraphs(html) {
  const text = stripHtml(html)
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();

  if (!text) {
    return [];
  }

  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
  const paragraphs = [];

  for (let index = 0; index < sentences.length && paragraphs.length < 3; index += 2) {
    paragraphs.push(sentences.slice(index, index + 2).join(" ").trim());
  }

  return paragraphs;
}

function stripHtml(html) {
  const element = document.createElement("div");
  element.innerHTML = html || "";
  element.querySelectorAll("script, style, img, picture, figure, iframe").forEach((node) => node.remove());
  return element.textContent || element.innerText || "";
}

function mergeArticles(oldArticles, newArticles) {
  const articlesById = new Map();

  [...oldArticles, ...newArticles].forEach((article) => {
    articlesById.set(article.id, article);
  });

  return [...articlesById.values()];
}

function pruneOldArticles() {
  newsStore.articles = newsStore.articles.filter(articleIsInLastSevenDays);
  saveStore();
}

function articleIsInLastSevenDays(article) {
  if (!article || !article.date) {
    return false;
  }

  const time = new Date(article.date).getTime();
  const oldestAllowed = Date.now() - MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
  const newestAllowed = Date.now() + 60 * 60 * 1000;
  return Number.isFinite(time) && time >= oldestAllowed && time <= newestAllowed;
}

function render() {
  normalizeFilterSelections();
  renderDayButtons();
  renderSourceFilterButtons();
  renderKeywords();
  renderHeadlines();
  setStatus(statusText());
}

function normalizeFilterSelections() {
  const dayKeys = recentDays().map((day) => day.key);
  selectedDayKeys = selectedDayKeys.filter((key) => dayKeys.includes(key));

  if (selectedDayKeys.length === 0) {
    selectedDayKeys = defaultSelectedDayKeys();
    saveSelectedDayKeys();
  }

  const sourceCodes = defaultSelectedSourceCodes();
  selectedSourceCodes = selectedSourceCodes.filter((code) => sourceCodes.includes(code));

  if (selectedSourceCodes.length === 0) {
    selectedSourceCodes = defaultSelectedSourceCodes();
    saveSelectedSourceCodes();
  }
}

function renderHeadlines() {
  const articles = sortedArticles().filter((article) => {
    return articleMatchesKeyword(article) && articleMatchesSource(article) && articleMatchesDateRange(article);
  });

  headlines.innerHTML = "";

  if (articles.length === 0) {
    headlines.textContent = "No headlines found for the selected days. Try Refresh, add a source, or choose different days.";
    return;
  }

  articles.forEach((article) => {
    const story = document.createElement("article");
    const row = document.createElement("button");
    const day = document.createElement("span");
    const source = document.createElement("span");
    const preview = document.createElement("span");
    const details = document.createElement("div");
    const title = document.createElement("h3");
    const meta = document.createElement("p");
    const link = document.createElement("a");

    row.type = "button";
    row.className = "articleRow";
    row.setAttribute("aria-expanded", "false");
    day.textContent = dayOfWeek(article.date);
    source.textContent = sourceCodeForArticle(article);
    preview.textContent = article.title;
    details.className = "articleDetails";
    details.hidden = true;
    title.textContent = article.title;
    meta.className = "meta";
    meta.textContent = `${keywordsForArticle(article).join(", ")} | ${article.source} | ${formatDate(article.date)}`;
    link.href = article.link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Read at original source";

    row.append(day, source, preview);
    row.addEventListener("click", () => {
      const expanded = row.getAttribute("aria-expanded") === "true";
      row.setAttribute("aria-expanded", String(!expanded));
      details.hidden = expanded;
    });

    story.append(row);
    details.append(title, meta);

    if (article.paragraphs.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No summary was included in the feed.";
      details.append(empty);
    } else {
      article.paragraphs.forEach((paragraphText) => {
        const paragraph = document.createElement("p");
        paragraph.textContent = paragraphText;
        details.append(paragraph);
      });
    }

    details.append(link);
    story.append(details);
    headlines.append(story);
  });
}

function dayOfWeek(dateText) {
  return new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(new Date(dateText));
}

function sourceCode(source) {
  const normalized = source.toLowerCase().trim();
  if (sourceCodes[normalized]) {
    return sourceCodes[normalized];
  }

  return source
    .replace(/[^A-Za-z]/g, "")
    .slice(0, 3)
    .toUpperCase()
    .padEnd(3, "-");
}

function sourceCodeForArticle(article) {
  const matchingSource = defaultSources.find((source) => {
    return article.sourceUrl === source.url || String(article.id || "").startsWith(`${source.url}|`);
  });

  return matchingSource ? sourceCode(matchingSource.name) : sourceCode(article.source || "");
}

function articleMatchesDateRange(article) {
  const date = new Date(article.date);

  if (Number.isNaN(date.getTime())) {
    return false;
  }

  return selectedDayKeys.includes(dateKey(date));
}

function articleMatchesKeyword(article) {
  return activeKeyword === "ALL" || keywordsForArticle(article).includes(activeKeyword);
}

function articleMatchesSource(article) {
  return selectedSourceCodes.includes(sourceCodeForArticle(article));
}

function startOfToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

function addDays(date, days) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function renderDayButtons() {
  const days = recentDays();
  dayButtons.innerHTML = "";
  days.forEach((day) => {
    const button = document.createElement("button");
    const count = newsStore.articles.filter((article) => {
      const date = new Date(article.date);
      return !Number.isNaN(date.getTime()) &&
        dateKey(date) === day.key &&
        articleMatchesKeyword(article) &&
        articleMatchesSource(article);
    }).length;

    button.type = "button";
    button.dataset.day = day.key;
    button.textContent = `${day.label} (${count})`;
    button.className = selectedDayKeys.includes(day.key) ? "active" : "";
    dayButtons.append(button);
  });
}

function toggleSelectedDay(dayKey) {
  if (selectedDayKeys.includes(dayKey)) {
    selectedDayKeys = selectedDayKeys.filter((key) => key !== dayKey);
  } else {
    selectedDayKeys.push(dayKey);
  }

  saveSelectedDayKeys();
  render();
}

function loadSelectedDayKeys() {
  try {
    const saved = JSON.parse(localStorage.getItem(SELECTED_DAYS_KEY));
    if (Array.isArray(saved)) {
      return saved.filter((key) => typeof key === "string");
    }
  } catch {
    return defaultSelectedDayKeys();
  }

  return defaultSelectedDayKeys();
}

function saveSelectedDayKeys() {
  localStorage.setItem(SELECTED_DAYS_KEY, JSON.stringify(selectedDayKeys));
}

function loadSelectedSourceCodes() {
  try {
    const saved = JSON.parse(localStorage.getItem(SELECTED_SOURCES_KEY));
    if (Array.isArray(saved)) {
      const allowedCodes = defaultSelectedSourceCodes();
      return saved.filter((code) => allowedCodes.includes(code));
    }
  } catch {
    return defaultSelectedSourceCodes();
  }

  return defaultSelectedSourceCodes();
}

function saveSelectedSourceCodes() {
  localStorage.setItem(SELECTED_SOURCES_KEY, JSON.stringify(selectedSourceCodes));
}

function defaultSelectedSourceCodes() {
  return defaultSources.map((source) => sourceCode(source.name));
}

function defaultSelectedDayKeys() {
  return recentDays().slice(0, 2).map((day) => day.key);
}

function recentDays() {
  const today = startOfToday();

  return Array.from({ length: MAX_AGE_DAYS }, (_, index) => {
    const date = addDays(today, -index);
    return {
      key: dateKey(date),
      label: dayOfWeek(date)
    };
  });
}

function dateKey(date) {
  const localDate = new Date(date);
  localDate.setHours(0, 0, 0, 0);
  return [
    localDate.getFullYear(),
    String(localDate.getMonth() + 1).padStart(2, "0"),
    String(localDate.getDate()).padStart(2, "0")
  ].join("-");
}

function renderSourceFilterButtons() {
  sourceFilterButtons.innerHTML = "";

  defaultSources.forEach((source) => {
    const button = document.createElement("button");
    const code = sourceCode(source.name);
    const count = newsStore.articles.filter((article) => {
      return sourceCodeForArticle(article) === code &&
        articleMatchesKeyword(article) &&
        articleMatchesDateRange(article);
    }).length;

    button.type = "button";
    button.textContent = `${code} (${count})`;
    button.title = `Show ${source.name}`;
    button.className = selectedSourceCodes.includes(code) ? "active" : "";
    button.addEventListener("click", () => {
      toggleSelectedSource(code);
      render();
    });
    sourceFilterButtons.append(button);
  });
}

function toggleSelectedSource(code) {
  if (selectedSourceCodes.includes(code)) {
    selectedSourceCodes = selectedSourceCodes.filter((selectedCode) => selectedCode !== code);
  } else {
    selectedSourceCodes.push(code);
  }

  saveSelectedSourceCodes();
}

function keywordsForArticle(article) {
  return Array.isArray(article.keywords) && article.keywords.length > 0
    ? article.keywords
    : keywordsFromTitle(article.title || article.source || "");
}

function renderKeywords() {
  const keywords = ["ALL", ...new Set(newsStore.articles.flatMap(keywordsForArticle))].sort((a, b) => {
    if (a === "ALL") return -1;
    if (b === "ALL") return 1;
    return a.localeCompare(b);
  });

  keywordList.innerHTML = "";

  keywords.forEach((keyword) => {
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = keyword;
    link.className = keyword === activeKeyword ? "keywordLink active" : "keywordLink";
    link.addEventListener("click", (event) => {
      event.preventDefault();
      activeKeyword = keyword;
      render();
    });
    keywordList.append(link);
  });
}

function sortedArticles() {
  return [...newsStore.articles].sort((a, b) => {
    const timeA = new Date(a.date).getTime();
    const timeB = new Date(b.date).getTime();
    return timeB - timeA || a.title.localeCompare(b.title);
  });
}

function formatDate(dateText) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(dateText));
}

function statusText() {
  return newsStore.lastUpdated ? `Updated ${formatDate(newsStore.lastUpdated)}` : "";
}

function setStatus(message) {
  statusLine.textContent = message;
}
