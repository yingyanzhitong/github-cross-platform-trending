export type DailyTrendingProject = {
  rank: number
  name: string
  trending_rank: number
  stars_today: number
}

export type NewProject = {
  rank: number
  name: string
}

export type ReportSummary = {
  report_type: ReportType
  date: string
  generated_at: string | null
  discovered_count: number
  candidate_count: number
  item_count: number
  analysis_count: number
  daily_trending: DailyTrendingProject[]
  weekly_trending: DailyTrendingProject[]
  new_projects: NewProject[]
  warnings_count: number
  item_names: string[]
  report_path: string
}

export type ReportType = "cross-platform" | "hot-rising"

export type ReportCatalog = {
  id: ReportType
  name: string
  latest: string
  reports: ReportSummary[]
}

export type ReportManifest = {
  default_type: ReportType
  catalogs: ReportCatalog[]
  latest: string
  reports: ReportSummary[]
}

export type ReportSection = {
  id: string
  markdown: string
}
