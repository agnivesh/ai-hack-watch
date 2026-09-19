let allArticles = [];
let activeFilter = "All";

async function loadArticles() {
  const response = await fetch("incidents.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("Could not load incidents.json");
  const data = await response.json();
  // Support both new schema (object with incidents array) and legacy flat array
  return data.incidents ?? data;
}

function daysBetween(startDate, endDate = new Date()) {
  // UTC calendar dates so all visitors see the same count
  const start = new Date(startDate + "T00:00:00Z");
  const today = Date.UTC(
    endDate.getUTCFullYear(),
    endDate.getUTCMonth(),
    endDate.getUTCDate()
  );
  return Math.max(0, Math.floor((today - start) / 86400000));
}

function formatDate(dateString) {
  return new Intl.DateTimeFormat("en-GB", { day:"2-digit", month:"short", year:"numeric" })
    .format(new Date(dateString + "T00:00:00"));
}

function slugify(value) { return String(value).toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-").replace(/-+/g, "-"); }

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function updateMeta(incident) {
  const days = incident ? daysBetween(incident.date) : 0;
  const title = "Days since AI hack";
  const description = incident ? `It has been ${days} days since the latest tracked incident: ${incident.title}.` : "A public timeline of notable AI hacking and AI-enabled cyber incidents.";
  document.title = title;
  document.querySelector('meta[name="description"]').setAttribute("content", description);
  document.querySelector('meta[property="og:title"]').setAttribute("content", title);
  document.querySelector('meta[property="og:description"]').setAttribute("content", description);
  document.querySelector('meta[property="og:url"]').setAttribute("content", window.location.href);
}

function uniqueTags(articles) {
  return [...new Set(articles.flatMap(a => [a.role, a.category].filter(Boolean)))];
}

function intervals(articles) {
  const dates = articles.map(a => new Date(a.date + "T00:00:00"));
  return dates.slice(1).map((d, i) => Math.round((dates[i] - d) / 86400000));
}

function longestGap(articles) {
  return Math.max(0, ...intervals(articles));
}

function setSubmitLinks() {
  const repo = window.SITE_CONFIG?.repositoryUrl || "";
  const repositoryUrl = safeHttpUrl(repo);
  const url = repositoryUrl && !repositoryUrl.includes("YOUR-USERNAME")
    ? `${repositoryUrl.replace(/\/$/, "")}/issues/new?template=story-submission.yml`
    : "#";
  for (const id of ["submit-link","submit-link-bottom"]) {
    const el = document.getElementById(id);
    el.href = url;
    if (url === "#") {
      el.addEventListener("click", e => {
        e.preventDefault();
        alert("Set repositoryUrl in config.js after creating the GitHub repository.");
      });
    }
  }
}

function renderStats() {
  const gaps = intervals(allArticles);
  const latest = allArticles[0];
  document.getElementById("days").textContent = daysBetween(latest.date);
  document.getElementById("last-update").textContent = `Last tracked: ${formatDate(latest.date)}`;
  document.getElementById("story-count").textContent = allArticles.length;
  document.getElementById("record-streak").textContent = `${longestGap(allArticles)}d`;
  document.getElementById("last-gap").textContent = gaps.length ? `${gaps[0]}d` : "—";
  const footerUpdated = document.getElementById("footer-last-tracked");
  if (footerUpdated) footerUpdated.textContent = formatDate(latest.date);
}

function renderBreakdown() {
  const roles = ["Autonomous","AI-assisted","AI-targeted","AI security research","Unclear"];
  const cats = [...new Set(allArticles.map(a => a.category).filter(Boolean))];
  const values = roles.map(role => [role, allArticles.filter(a => a.role === role).length]);
  const cards = [...values, ...cats.slice(0, 3).map(cat => [cat, allArticles.filter(a => a.category === cat).length])];
  document.getElementById("breakdown").innerHTML = cards.slice(0, 8).map(([label,count]) =>
    `<button type="button" class="breakdown-card" data-filter="${escapeHtml(label)}" aria-pressed="false"><strong>${count}</strong><span>${escapeHtml(label)}</span></button>`
  ).join("");
  bindFilterButtons(".breakdown-card");
}

function buildFilters() {
  const filters = ["All", ...uniqueTags(allArticles)];
  document.getElementById("filters").innerHTML = filters.map(filter =>
    `<button class="filter" data-filter="${escapeHtml(filter)}" aria-pressed="false">${escapeHtml(filter)}</button>`
  ).join("");
  bindFilterButtons(".filter");
}

function bindFilterButtons(selector) {
  document.querySelectorAll(selector).forEach(button => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      applyFilter();
    });
  });
}

function renderArticle(article) {
  const slug = slugify(article.slug || article.title);
  const sourceUrl = safeHttpUrl(article.url);
  const archiveUrl = safeHttpUrl(article.archive);
  const title = escapeHtml(article.title || "Untitled incident");
  const source = escapeHtml(article.source || "Unknown source");
  const role = article.role ? `<button type="button" class="tag tag-filter" data-filter="${escapeHtml(article.role)}" aria-pressed="false">${escapeHtml(article.role)}</button>` : "";
  const category = article.category ? `<button type="button" class="tag tag-filter" data-filter="${escapeHtml(article.category)}" aria-pressed="false">${escapeHtml(article.category)}</button>` : "";
  const sourceLink = sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Read source ↗</a>` : "";
  const archiveLink = archiveUrl ? `<a href="${escapeHtml(archiveUrl)}" target="_blank" rel="noopener noreferrer">Archived copy ↗</a>` : "";
  const extraLinks = (article.urls || []).slice(1).map(extraUrl => {
    const extra = safeHttpUrl(extraUrl);
    return extra ? `<a href="${escapeHtml(extra)}" target="_blank" rel="noopener noreferrer">Alternative source ↗</a>` : "";
  }).join("");

  return `
      <article class="item" id="${escapeHtml(slug)}" data-role="${escapeHtml(article.role ?? "")}" data-category="${escapeHtml(article.category ?? "")}">
        <div class="date">${formatDate(article.date)}</div>
        <div class="dot-wrap"><div class="dot"></div></div>
        <div class="card">
          <div class="source">${source}</div>
          <h3>${title} <a class="permalink" href="#${escapeHtml(slug)}">#</a></h3>
          <div class="tags">${role}${category}</div>
          <p>${escapeHtml(article.description)}</p>
          <div class="card-links">${sourceLink}${archiveLink}${extraLinks}</div>
        </div>
      </article>
    `;
}

function renderTimeline() {
  const timeline = document.getElementById("timeline");
  if (!timeline.dataset.built) {
    timeline.innerHTML = allArticles.map(renderArticle).join("");
    timeline.dataset.built = "true";
    bindFilterButtons(".tag-filter");
  }
  applyFilter();
}

function articleMatches(article) {
  return activeFilter === "All"
    || article.dataset.role === activeFilter
    || article.dataset.category === activeFilter;
}

function applyFilter() {
  const timeline = document.getElementById("timeline");
  let visibleCount = 0;
  timeline.querySelectorAll("article.item").forEach(article => {
    const matches = articleMatches(article);
    article.classList.toggle("hidden", !matches);
    if (matches) visibleCount += 1;
  });
  document.querySelectorAll(".filter, .tag-filter, .breakdown-card").forEach(button => {
    const isActive = button.dataset.filter === activeFilter;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  document.getElementById("filter-count").textContent = `${visibleCount} of ${allArticles.length} stories`;
}

function currentTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyThemeColor(theme) {
  const color = theme === "dark" ? "#121210" : "#f5f5f2";
  document.querySelectorAll('meta[name="theme-color"]')
    .forEach(meta => meta.setAttribute("content", color));
}

function initThemeToggle() {
  const button = document.getElementById("theme-toggle");
  if (!button) return;
  const sync = () => {
    const theme = currentTheme();
    const target = theme === "dark" ? "light" : "dark";
    button.textContent = target === "dark" ? "Dark" : "Light";
    button.setAttribute("aria-label", `Switch to ${target} theme`);
    button.setAttribute("aria-pressed", String(theme === "dark"));
    applyThemeColor(theme);
  };
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (error) {}
    sync();
  });
  // Keep the label correct if the OS switches while no explicit choice is stored
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!document.documentElement.hasAttribute("data-theme")) sync();
  });
  sync();
}

async function render() {
  setSubmitLinks();
  allArticles = (await loadArticles()).sort((a,b) => b.date.localeCompare(a.date));
  if (!allArticles.length) throw new Error("No valid articles found");
  updateMeta(allArticles[0]);
  renderStats();
  renderBreakdown();
  buildFilters();
  renderTimeline();
}

initThemeToggle();

render().catch(error => {
  const timeline = document.getElementById("timeline");
  if (!timeline.children.length) {
    timeline.innerHTML = `<p>Could not load the timeline. Check the generated data.</p>`;
  }
  console.error(error);
});
