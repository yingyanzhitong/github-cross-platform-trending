const state = {
  manifest: null,
  currentDate: null,
};

const elements = {
  rail: document.querySelector("#date-rail"),
  railOpen: document.querySelector("#rail-open"),
  railClose: document.querySelector("#rail-close"),
  search: document.querySelector("#report-search"),
  reportList: document.querySelector("#report-list"),
  breadcrumbDate: document.querySelector("#breadcrumb-date"),
  title: document.querySelector("#page-title"),
  summary: document.querySelector("#hero-summary"),
  software: document.querySelector("#metric-software"),
  discovered: document.querySelector("#metric-discovered"),
  analyzed: document.querySelector("#metric-analyzed"),
  newCount: document.querySelector("#metric-new"),
  dailyTrending: document.querySelector("#daily-trending"),
  newer: document.querySelector("#newer-report"),
  older: document.querySelector("#older-report"),
  raw: document.querySelector("#raw-report"),
  copy: document.querySelector("#copy-link"),
  loadState: document.querySelector("#load-state"),
  content: document.querySelector("#report-content"),
  backToTop: document.querySelector("#back-to-top"),
};

function reportUrl(date) {
  const url = new URL(window.location.href);
  url.searchParams.set("date", date);
  url.hash = "";
  return url;
}

function formatDate(date) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${date}T00:00:00+08:00`));
}

function reportMatches(report, query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return true;
  return (
    report.date.includes(normalized) ||
    report.software_names.some((name) => name.toLowerCase().includes(normalized))
  );
}

function renderReportList(query = "") {
  const reports = state.manifest.reports.filter((report) =>
    reportMatches(report, query),
  );
  elements.reportList.replaceChildren();

  if (!reports.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "没有匹配的日报或项目。";
    elements.reportList.append(empty);
    return;
  }

  for (const report of reports) {
    const link = document.createElement("a");
    link.href = reportUrl(report.date);
    link.className = "report-link";
    link.dataset.date = report.date;
    if (report.date === state.currentDate) {
      link.classList.add("is-active");
      link.setAttribute("aria-current", "page");
    }

    const date = document.createElement("strong");
    date.textContent = report.date;
    const meta = document.createElement("span");
    meta.textContent = `${report.software_count} 个软件 · ${report.new_projects.length} 个新增`;
    const marker = document.createElement("i");
    marker.setAttribute("aria-hidden", "true");
    link.append(marker, date, meta);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      loadReport(report.date, true);
      elements.rail.classList.remove("is-open");
    });
    elements.reportList.append(link);
  }
}

function updateNavigation(report) {
  const reports = state.manifest.reports;
  const index = reports.findIndex((item) => item.date === report.date);
  const newer = reports[index - 1];
  const older = reports[index + 1];

  elements.newer.disabled = !newer;
  elements.older.disabled = !older;
  elements.newer.onclick = newer ? () => loadReport(newer.date, true) : null;
  elements.older.onclick = older ? () => loadReport(older.date, true) : null;
}

function updateHeader(report) {
  elements.breadcrumbDate.textContent = report.date;
  elements.title.textContent = `${formatDate(report.date)}日报`;
  elements.summary.textContent =
    `从 ${report.discovered_count.toLocaleString("zh-CN")} 个候选中分析 ` +
    `${report.candidate_count.toLocaleString("zh-CN")} 个仓库，` +
    `仅保留 Latest Release 同时提供 macOS 与 Windows 安装包的软件。`;
  elements.software.textContent = report.software_count;
  elements.discovered.textContent = report.discovered_count.toLocaleString("zh-CN");
  elements.analyzed.textContent = report.candidate_count.toLocaleString("zh-CN");
  elements.newCount.textContent = report.new_projects.length;
  elements.raw.href = `reports/${report.date}.md`;

  elements.dailyTrending.replaceChildren();
  const label = document.createElement("span");
  label.textContent = "DAILY TRENDING";
  elements.dailyTrending.append(label);
  if (report.daily_trending.length) {
    const names = report.daily_trending
      .map((item) => `${item.name} (+${item.stars_today})`)
      .join(" · ");
    const text = document.createElement("strong");
    text.textContent = names;
    elements.dailyTrending.append(text);
  } else {
    const text = document.createElement("strong");
    text.textContent = "当日无入榜项目";
    elements.dailyTrending.append(text);
  }
}

function enhanceReportContent() {
  for (const table of elements.content.querySelectorAll("table")) {
    const wrapper = document.createElement("div");
    wrapper.className = "table-scroll";
    table.parentNode.insertBefore(wrapper, table);
    wrapper.append(table);
  }
  for (const link of elements.content.querySelectorAll("a[href]")) {
    const href = link.getAttribute("href");
    if (href?.startsWith("#")) {
      link.addEventListener("click", (event) => {
        const target = document.getElementById(href.slice(1));
        if (!target) return;
        event.preventDefault();
        history.pushState(null, "", href);
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } else if (link.href.startsWith("http") && link.origin !== window.location.origin) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
  }
}

async function loadReport(date, updateHistory = false) {
  const report =
    state.manifest.reports.find((item) => item.date === date) ||
    state.manifest.reports[0];
  state.currentDate = report.date;
  elements.loadState.hidden = false;
  elements.content.replaceChildren();
  elements.content.setAttribute("aria-busy", "true");
  updateHeader(report);
  updateNavigation(report);
  renderReportList(elements.search.value);

  if (updateHistory) {
    history.pushState({ date: report.date }, "", reportUrl(report.date));
  }

  try {
    const response = await fetch(`reports/${report.date}.md`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const markdown = await response.text();
    if (!window.marked || !window.DOMPurify) {
      throw new Error("Markdown 渲染器未加载");
    }
    const html = window.marked.parse(markdown, { gfm: true });
    elements.content.innerHTML = window.DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
    });
    enhanceReportContent();
    elements.loadState.hidden = true;
    elements.content.removeAttribute("aria-busy");
    document.title = `${report.date} · 跨平台热门软件日报`;
    const hashTarget = window.location.hash
      ? document.getElementById(window.location.hash.slice(1))
      : null;
    if (hashTarget) {
      hashTarget.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } catch (error) {
    elements.loadState.hidden = true;
    elements.content.removeAttribute("aria-busy");
    const errorBox = document.createElement("div");
    errorBox.className = "error-state";
    errorBox.innerHTML =
      `<strong>日报加载失败</strong>` +
      `<p>${error.message}。可以直接打开当天 Markdown 文件。</p>` +
      `<a href="reports/${report.date}.md">查看 ${report.date}.md</a>`;
    elements.content.append(errorBox);
  }
}

async function initialize() {
  try {
    const response = await fetch("reports/index.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.manifest = await response.json();
    const requested = new URL(window.location.href).searchParams.get("date");
    await loadReport(requested || state.manifest.latest);
  } catch (error) {
    elements.loadState.innerHTML =
      `<strong>日报目录加载失败</strong><p>${error.message}</p>`;
  }
}

elements.search.addEventListener("input", () => renderReportList(elements.search.value));
elements.railOpen.addEventListener("click", () => elements.rail.classList.add("is-open"));
elements.railClose.addEventListener("click", () => elements.rail.classList.remove("is-open"));
elements.copy.addEventListener("click", async () => {
  await navigator.clipboard.writeText(reportUrl(state.currentDate).toString());
  elements.copy.textContent = "已复制";
  window.setTimeout(() => {
    elements.copy.textContent = "复制链接";
  }, 1600);
});
elements.backToTop.addEventListener("click", () =>
  window.scrollTo({ top: 0, behavior: "smooth" }),
);
window.addEventListener("popstate", (event) => {
  const date =
    event.state?.date ||
    new URL(window.location.href).searchParams.get("date") ||
    state.manifest.latest;
  loadReport(date);
});

initialize();
