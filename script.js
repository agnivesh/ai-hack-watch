let allArticles = [];
let siteTaxonomy = null;
let activeFilter = { type: "all", value: "All" };

const FALLBACK_ROLES = ["Autonomous","AI-assisted","AI-targeted","AI security research","Unclear"];

async function loadArticles() {
  const response = await fetch("incidents.json", { cache: "no-cache" });
  if (!response.ok) throw new Error("Could not load incidents.json");
  const data = await response.json();
  // Single source of truth for taxonomy lives in incidents.json
  // (generated from scripts/datamd.py); fall back for old datasets.
  siteTaxonomy = data.taxonomy ?? null;
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
  return new Intl.DateTimeFormat("en-GB", { day:"2-digit", month:"short", year:"numeric", timeZone:"UTC" })
    .format(new Date(dateString + "T00:00:00Z"));
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
  const dates = articles.map(a => new Date(a.date + "T00:00:00Z"));
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
  const roles = siteTaxonomy?.roles ?? FALLBACK_ROLES;
  const taxonomyCats = siteTaxonomy?.categories ?? null;
  // Show every category present in data (plus every taxonomy category
  // even at 0, so the breakdown never silently hides a category).
  const dataCats = [...new Set(allArticles.map(a => a.category).filter(Boolean))];
  const cats = taxonomyCats
    ? [...taxonomyCats, ...dataCats.filter(c => !taxonomyCats.includes(c))]
    : [...dataCats].sort();
  const values = roles.map(role => ({ type: "role", label: role, count: allArticles.filter(a => a.role === role).length }));
  const catValues = cats.map(cat => ({ type: "category", label: cat, count: allArticles.filter(a => a.category === cat).length }));
  const cards = [...values, ...catValues];
  document.getElementById("breakdown").innerHTML = cards.map(({ type, label, count }) =>
    `<button type="button" class="breakdown-card" data-filter-type="${escapeHtml(type)}" data-filter="${escapeHtml(label)}" aria-pressed="false"><strong>${count}</strong><span>${escapeHtml(label)}</span></button>`
  ).join("");
  bindFilterButtons(".breakdown-card");
}

function buildFilters() {
  const roles = [...new Set(allArticles.map(a => a.role).filter(Boolean))];
  const cats = [...new Set(allArticles.map(a => a.category).filter(Boolean))];
  const buttons = [`<button class="filter" data-filter-type="all" data-filter="All" aria-pressed="false">All</button>`];
  for (const role of roles) {
    buttons.push(`<button class="filter" data-filter-type="role" data-filter="${escapeHtml(role)}" aria-pressed="false">${escapeHtml(role)}</button>`);
  }
  for (const cat of cats) {
    // Even if a label also exists as a role, the type keeps them distinct.
    buttons.push(`<button class="filter" data-filter-type="category" data-filter="${escapeHtml(cat)}" aria-pressed="false">${escapeHtml(cat)}</button>`);
  }
  document.getElementById("filters").innerHTML = buttons.join("");
  bindFilterButtons(".filter");
}

function bindFilterButtons(selector) {
  document.querySelectorAll(selector).forEach(button => {
    // Avoid double-binding when hydration re-runs.
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      activeFilter = { type: button.dataset.filterType || "all", value: button.dataset.filter };
      if (activeFilter.value === "All") activeFilter.type = "all";
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
  const role = article.role ? `<button type="button" class="tag tag-filter" data-filter-type="role" data-filter="${escapeHtml(article.role)}" aria-pressed="false">${escapeHtml(article.role)}</button>` : "";
  const category = article.category ? `<button type="button" class="tag tag-filter" data-filter-type="category" data-filter="${escapeHtml(article.category)}" aria-pressed="false">${escapeHtml(article.category)}</button>` : "";
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
  const wanted = allArticles.map(a => slugify(a.slug || a.title));
  const existing = [...timeline.querySelectorAll("article.item")].map(el => el.id);
  const matches = existing.length > 0
    && wanted.slice(0, existing.length).every((slug, i) => slug === existing[i]);
  if (!timeline.dataset.built && !matches) {
    // Full rebuild only when prerendered HTML doesn't match fresh data.
    // Otherwise hydrate in place so first paint is preserved.
    timeline.innerHTML = allArticles.map(renderArticle).join("");
    timeline.dataset.built = "true";
  } else {
    // Hydrate prerendered nodes: ensure filter dimensions exist for
    // progressive enhancement before/without a rebuild.
    const bySlug = new Map(allArticles.map(a => [slugify(a.slug || a.title), a]));
    timeline.querySelectorAll("article.item").forEach(el => {
      const article = bySlug.get(el.id);
      if (article) {
        el.dataset.role = article.role ?? "";
        el.dataset.category = article.category ?? "";
      }
    });
    // Ensure tag buttons carry namespaced filter types (old prerender
    // only had data-filter).
    timeline.querySelectorAll(".tag-filter").forEach(btn => {
      if (!btn.dataset.filterType) {
        const parent = btn.closest("article.item");
        if (parent && parent.dataset.role === btn.dataset.filter) btn.dataset.filterType = "role";
        else btn.dataset.filterType = "category";
      }
    });
    timeline.dataset.built = timeline.dataset.built || "true";
  }
  bindFilterButtons(".tag-filter");
  applyFilter();
}

function articleMatches(article) {
  if (activeFilter.type === "all" || activeFilter.value === "All") return true;
  if (activeFilter.type === "role") return article.dataset.role === activeFilter.value;
  if (activeFilter.type === "category") return article.dataset.category === activeFilter.value;
  return article.dataset.role === activeFilter.value
    || article.dataset.category === activeFilter.value;
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
    let isActive;
    if (button.dataset.filterType) {
      isActive = button.dataset.filter === activeFilter.value
        && button.dataset.filterType === activeFilter.type;
    } else {
      // Legacy button without a type: match by value only.
      isActive = button.dataset.filter === activeFilter.value;
    }
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
