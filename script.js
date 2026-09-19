let allArticles = [];
let activeFilter = "All";

async function loadArticles() {
  const response = await fetch("incidents.json", { cache: "no-store" });
  if (!response.ok) throw new Error("Could not load incidents.json");
  return await response.json();
}

function daysBetween(startDate, endDate = new Date()) {
  const start = new Date(startDate + "T00:00:00");
  const today = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
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
}

function renderBreakdown() {
  const roles = ["Autonomous","AI-assisted","AI-targeted","AI security research","Unclear"];
  const cats = [...new Set(allArticles.map(a => a.category).filter(Boolean))];
  const values = roles.map(role => [role, allArticles.filter(a => a.role === role).length]);
  const cards = [...values, ...cats.slice(0, 3).map(cat => [cat, allArticles.filter(a => a.category === cat).length])];
  document.getElementById("breakdown").innerHTML = cards.slice(0, 8).map(([label,count]) =>
    `<div class="breakdown-card"><strong>${count}</strong><span>${escapeHtml(label)}</span></div>`
  ).join("");
}

function renderChart() {
  const gaps = intervals(allArticles).slice(0, 12).reverse();
  const max = Math.max(1, ...gaps);
  document.getElementById("gap-chart").innerHTML = gaps.map((gap, i) =>
    `<div class="bar" style="height:${Math.max(6, Math.round(gap/max*100))}%"><span class="bar-label">${gap}</span></div>`
  ).join("");
}

function renderFilters() {
  const filters = ["All", ...uniqueTags(allArticles)];
  document.getElementById("filters").innerHTML = filters.map(filter =>
    `<button class="filter ${filter === activeFilter ? "active" : ""}" data-filter="${escapeHtml(filter)}" aria-pressed="${filter === activeFilter}">${escapeHtml(filter)}</button>`
  ).join("");
  bindFilterButtons(".filter");
}

function bindFilterButtons(selector) {
  document.querySelectorAll(selector).forEach(button => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      renderFilters();
      renderTimeline();
    });
  });
}

function renderTimeline() {
  const visible = activeFilter === "All"
    ? allArticles
    : allArticles.filter(a => a.role === activeFilter || a.category === activeFilter);

  document.getElementById("filter-count").textContent = `${visible.length} of ${allArticles.length} stories`;
  document.getElementById("timeline").innerHTML = visible.map(article => {
    const slug = slugify(article.slug || article.title);
    const sourceUrl = safeHttpUrl(article.url);
    const archiveUrl = safeHttpUrl(article.archive);
    const title = escapeHtml(article.title || "Untitled incident");
    const source = escapeHtml(article.source || "Unknown source");
    const role = article.role ? `<button type="button" class="tag tag-filter ${activeFilter === article.role ? "active" : ""}" data-filter="${escapeHtml(article.role)}" aria-pressed="${activeFilter === article.role}">${escapeHtml(article.role)}</button>` : "";
    const category = article.category ? `<button type="button" class="tag tag-filter ${activeFilter === article.category ? "active" : ""}" data-filter="${escapeHtml(article.category)}" aria-pressed="${activeFilter === article.category}">${escapeHtml(article.category)}</button>` : "";
    const sourceLink = sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Read source ↗</a>` : "";
    const archiveLink = archiveUrl ? `<a href="${escapeHtml(archiveUrl)}" target="_blank" rel="noopener noreferrer">Archived copy ↗</a>` : "";

    return `
      <article class="item" id="${escapeHtml(slug)}">
        <div class="date">${formatDate(article.date)}</div>
        <div class="dot-wrap"><div class="dot"></div></div>
        <div class="card">
          <div class="source">${source}</div>
          <h3>${title} <a class="permalink" href="#${escapeHtml(slug)}">#</a></h3>
          <div class="tags">${role}${category}</div>
          <p>${escapeHtml(article.description)}</p>
          <div class="card-links">${sourceLink}${archiveLink}</div>
        </div>
      </article>
    `;
  }).join("");
  bindFilterButtons(".tag-filter");
}

async function render() {
  setSubmitLinks();
  allArticles = (await loadArticles()).sort((a,b) => b.date.localeCompare(a.date));
  if (!allArticles.length) throw new Error("No valid articles found");
  updateMeta(allArticles[0]);
  renderStats();
  renderBreakdown();
  renderChart();
  renderFilters();
  renderTimeline();
}

render().catch(error => {
  const timeline = document.getElementById("timeline");
  if (!timeline.children.length) {
    timeline.innerHTML = `<p>Could not load the timeline. Check the generated data.</p>`;
  }
  console.error(error);
});
