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
  date: string
  generated_at: string | null
  discovered_count: number
  candidate_count: number
  software_count: number
  daily_trending: DailyTrendingProject[]
  new_projects: NewProject[]
  warnings_count: number
  software_names: string[]
}

export type ReportManifest = {
  latest: string
  reports: ReportSummary[]
}

export type ReportSection = {
  id: string
  markdown: string
}
