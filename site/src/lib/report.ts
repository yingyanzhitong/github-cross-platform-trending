import type { ReportSection, ReportSummary, ReportType } from "@/types"

const DETAIL_ANCHOR = /<a id="(project-detail-\d+)"><\/a>\s*/g

export function formatReportDate(date: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(new Date(`${date}T00:00:00+08:00`))
}

export function reportMatches(report: ReportSummary, query: string) {
  const normalized = query.trim().toLocaleLowerCase("zh-CN")
  if (!normalized) return true

  return (
    report.date.includes(normalized) ||
    report.item_names.some((name) =>
      name.toLocaleLowerCase("zh-CN").includes(normalized),
    )
  )
}

export function reportUrl(reportType: ReportType, date: string) {
  const url = new URL(window.location.href)
  url.searchParams.set("type", reportType)
  url.searchParams.set("date", date)
  url.hash = ""
  return url
}

export function splitReportMarkdown(markdown: string) {
  const matches = [...markdown.matchAll(DETAIL_ANCHOR)]
  const overviewEnd = matches[0]?.index ?? markdown.length
  const overviewSource = markdown.slice(0, overviewEnd)
  const tableStart = overviewSource.indexOf("| 详情 ↘️")
  const overview =
    tableStart >= 0 ? overviewSource.slice(tableStart).trim() : overviewSource.trim()

  const sections: ReportSection[] = matches.map((match, index) => {
    const start = (match.index ?? 0) + match[0].length
    const end = matches[index + 1]?.index ?? markdown.length
    return {
      id: match[1],
      markdown: markdown.slice(start, end).trim(),
    }
  })

  return { overview, sections }
}

export function scrollToAnchor(anchor: string, updateHistory = true) {
  const id = anchor.replace(/^#/, "")
  const target = document.getElementById(id)
  if (!target) return false

  if (updateHistory) {
    history.pushState(history.state, "", `#${id}`)
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" })
  return true
}
