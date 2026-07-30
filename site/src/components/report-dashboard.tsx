import { lazy, Suspense } from "react"
import {
  ArrowLeftRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CircleAlertIcon,
  CopyIcon,
  FileTextIcon,
  MonitorCheckIcon,
  PackageCheckIcon,
  TrendingUpIcon,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { formatReportDate } from "@/lib/report"
import type { ReportSummary } from "@/types"

const ReportMarkdown = lazy(() =>
  import("@/components/report-markdown").then((module) => ({
    default: module.ReportMarkdown,
  })),
)

type ReportDashboardProps = {
  report: ReportSummary
  markdown: string
  loading: boolean
  error: string | null
  hasNewer: boolean
  hasOlder: boolean
  copied: boolean
  onNewer: () => void
  onOlder: () => void
  onCopy: () => void
}

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  return (
    <Card size="sm" className="metric-card">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="font-data text-2xl font-semibold tabular-nums">
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  )
}

function LoadingReport() {
  return (
    <Card aria-label="正在装载日报">
      <CardHeader>
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </CardHeader>
      <CardContent className="grid gap-3">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </CardContent>
    </Card>
  )
}

export function ReportDashboard({
  report,
  markdown,
  loading,
  error,
  hasNewer,
  hasOlder,
  copied,
  onNewer,
  onOlder,
  onCopy,
}: ReportDashboardProps) {
  const trendingText = report.daily_trending.length
    ? report.daily_trending
        .map((item) => `${item.name} +${item.stars_today}`)
        .join(" · ")
    : "当日无入榜项目"

  return (
    <>
      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/92 px-4 backdrop-blur md:px-6">
        <Tooltip>
          <TooltipTrigger asChild>
            <SidebarTrigger aria-label="打开或收起日报导航" />
          </TooltipTrigger>
          <TooltipContent>日报导航（⌘B）</TooltipContent>
        </Tooltip>
        <Separator orientation="vertical" className="h-4" />
        <Breadcrumb className="min-w-0 flex-1">
          <BreadcrumbList className="flex-nowrap">
            <BreadcrumbItem className="hidden sm:inline-flex">日报归档</BreadcrumbItem>
            <BreadcrumbSeparator className="hidden sm:list-item" />
            <BreadcrumbItem className="min-w-0">
              <BreadcrumbPage className="truncate font-data text-xs font-semibold">
                {report.date}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={onCopy}>
            {copied ? (
              <CheckIcon data-icon="inline-start" />
            ) : (
              <CopyIcon data-icon="inline-start" />
            )}
            <span className="hidden sm:inline">{copied ? "已复制" : "复制链接"}</span>
          </Button>
          <Button asChild variant="outline" size="sm">
            <a href={`reports/${report.date}.md`}>
              <FileTextIcon data-icon="inline-start" />
              <span className="hidden sm:inline">Markdown</span>
            </a>
          </Button>
        </div>
      </header>

      <div className="mx-auto grid w-full min-w-0 max-w-[1600px] gap-5 p-4 md:p-6 lg:p-8">
        <Card className="hero-card overflow-hidden">
          <CardHeader className="gap-4 border-b">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>DAILY TOP 100</Badge>
              <Badge
                variant="outline"
                className="border-success/35 bg-success/10 text-success-foreground"
              >
                <PackageCheckIcon data-icon="inline-start" />
                安装包已核验
              </Badge>
              {report.warnings_count > 0 && (
                <Badge variant="destructive">
                  <CircleAlertIcon data-icon="inline-start" />
                  {report.warnings_count} 个采集警告
                </Badge>
              )}
            </div>
            <div className="max-w-3xl">
              <CardTitle className="text-balance font-heading text-3xl font-semibold tracking-[-0.025em] md:text-4xl">
                {formatReportDate(report.date)}日报
              </CardTitle>
              <CardDescription className="mt-3 max-w-2xl text-sm leading-6 md:text-base">
                从 {report.discovered_count.toLocaleString("zh-CN")} 个候选中分析{" "}
                {report.candidate_count.toLocaleString("zh-CN")} 个仓库，仅保留 Latest
                Release 同时提供 macOS 与 Windows 安装包的软件。
              </CardDescription>
            </div>
            <CardAction className="hidden lg:block">
              <span className="font-data text-xs tracking-[0.16em] text-muted-foreground">
                RELEASE LEDGER / {report.date}
              </span>
            </CardAction>
          </CardHeader>
          <CardContent>
            <div
              className="verification-rail grid items-center gap-3 rounded-lg border bg-muted/35 p-3 sm:grid-cols-[1fr_auto_1fr]"
              aria-label="macOS 与 Windows 安装包均已验证"
            >
              <div className="flex items-center gap-3 rounded-md bg-background px-3 py-2">
                <span className="flex size-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <MonitorCheckIcon aria-hidden="true" />
                </span>
                <span>
                  <strong className="block text-sm">macOS</strong>
                  <span className="font-data text-xs text-muted-foreground">
                    .dmg / macOS .pkg
                  </span>
                </span>
              </div>
              <ArrowLeftRightIcon
                className="mx-auto size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <div className="flex items-center gap-3 rounded-md bg-background px-3 py-2">
                <span className="flex size-8 items-center justify-center rounded-md bg-success/12 text-success-foreground">
                  <PackageCheckIcon aria-hidden="true" />
                </span>
                <span>
                  <strong className="block text-sm">Windows</strong>
                  <span className="font-data text-xs text-muted-foreground">
                    .exe / .msi / .msix
                  </span>
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="日报统计">
          <MetricCard
            label="入榜软件"
            value={report.software_count.toLocaleString("zh-CN")}
            hint="双平台安装包齐全"
          />
          <MetricCard
            label="发现候选"
            value={report.discovered_count.toLocaleString("zh-CN")}
            hint="GitHub 热门候选池"
          />
          <MetricCard
            label="已分析"
            value={report.candidate_count.toLocaleString("zh-CN")}
            hint="完成仓库与 Release 核验"
          />
          <MetricCard
            label="新增项目"
            value={report.new_projects.length.toLocaleString("zh-CN")}
            hint="最近 7 天未曾入榜"
          />
        </section>

        <Card size="sm">
          <CardContent className="grid gap-3 md:grid-cols-[auto_1fr_auto] md:items-center">
            <Button variant="outline" size="sm" disabled={!hasNewer} onClick={onNewer}>
              <ChevronLeftIcon data-icon="inline-start" />
              更新一日
            </Button>
            <div className="min-w-0 text-center">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary">
                <TrendingUpIcon className="size-3.5" aria-hidden="true" />
                DAILY TRENDING
              </span>
              <p className="mt-1 truncate font-data text-xs text-muted-foreground">
                {trendingText}
              </p>
            </div>
            <Button variant="outline" size="sm" disabled={!hasOlder} onClick={onOlder}>
              更早一日
              <ChevronRightIcon data-icon="inline-end" />
            </Button>
          </CardContent>
        </Card>

        {error && (
          <Alert variant="destructive">
            <CircleAlertIcon aria-hidden="true" />
            <AlertTitle>日报加载失败</AlertTitle>
            <AlertDescription>
              {error}。可以直接打开{" "}
              <a href={`reports/${report.date}.md`}>{report.date}.md</a>。
            </AlertDescription>
          </Alert>
        )}

        {loading ? (
          <LoadingReport />
        ) : (
          markdown && (
            <Suspense fallback={<LoadingReport />}>
              <ReportMarkdown markdown={markdown} />
            </Suspense>
          )
        )}

        <footer className="flex flex-col gap-2 border-t py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>GitHub Cross-Platform Trending</span>
          <span>报告数据按生成时间保留 · 页面遵循 shadcn/ui 组件规范</span>
        </footer>
      </div>
    </>
  )
}
