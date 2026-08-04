import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react"
import { CircleAlertIcon } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import { ReportDashboard } from "@/components/report-dashboard"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { TooltipProvider } from "@/components/ui/tooltip"
import { reportUrl, scrollToAnchor } from "@/lib/report"
import type { ReportManifest, ReportType } from "@/types"

function InitialLoading() {
  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-6">
      <Card className="w-full max-w-lg" aria-label="正在读取日报目录">
        <CardHeader className="gap-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </CardContent>
      </Card>
    </main>
  )
}

function InitialError({ message }: { message: string }) {
  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-6">
      <Alert variant="destructive" className="max-w-lg">
        <CircleAlertIcon aria-hidden="true" />
        <AlertTitle>日报目录加载失败</AlertTitle>
        <AlertDescription>{message}。请稍后刷新页面重试。</AlertDescription>
      </Alert>
    </main>
  )
}

export default function App() {
  const [manifest, setManifest] = useState<ReportManifest | null>(null)
  const [manifestError, setManifestError] = useState<string | null>(null)
  const [currentType, setCurrentType] = useState<ReportType>("cross-platform")
  const [currentDate, setCurrentDate] = useState("")
  const [markdown, setMarkdown] = useState("")
  const [reportError, setReportError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState("")
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef<number | null>(null)

  useEffect(() => {
    const loadManifest = async () => {
      try {
        const response = await fetch("reports/index.json", { cache: "no-store" })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const payload = (await response.json()) as ReportManifest
        const params = new URL(window.location.href).searchParams
        const requestedType = params.get("type") as ReportType | null
        const catalog =
          payload.catalogs.find((item) => item.id === requestedType) ??
          payload.catalogs.find((item) => item.id === payload.default_type) ??
          payload.catalogs[0]
        if (!catalog) throw new Error("日报目录中没有可用榜单")
        const requested = params.get("date")
        const selected = catalog.reports.some((report) => report.date === requested)
          ? requested!
          : catalog.latest

        setManifest(payload)
        setCurrentType(catalog.id)
        setCurrentDate(selected)
      } catch (error) {
        setManifestError(error instanceof Error ? error.message : "未知错误")
      }
    }

    void loadManifest()
  }, [])

  useEffect(() => {
    if (!manifest) return

    const handlePopState = () => {
      const params = new URL(window.location.href).searchParams
      const requestedType = params.get("type") as ReportType | null
      const catalog =
        manifest.catalogs.find((item) => item.id === requestedType) ??
        manifest.catalogs.find((item) => item.id === manifest.default_type) ??
        manifest.catalogs[0]
      if (!catalog) return
      const requested = params.get("date")
      const selected = catalog.reports.some((report) => report.date === requested)
        ? requested!
        : catalog.latest
      setCurrentType(catalog.id)
      setCurrentDate(selected)
    }

    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [manifest])

  useEffect(() => {
    if (!currentDate || !manifest) return

    const catalog = manifest.catalogs.find((item) => item.id === currentType)
    const report = catalog?.reports.find((item) => item.date === currentDate)
    if (!catalog || !report) return

    const controller = new AbortController()
    const loadReport = async () => {
      setLoading(true)
      setReportError(null)
      setMarkdown("")

      try {
        const response = await fetch(report.report_path, {
          cache: "no-store",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        setMarkdown(await response.text())
        document.title = `${currentDate} · ${catalog.name}日报`
        window.setTimeout(() => {
          if (window.location.hash) {
            scrollToAnchor(window.location.hash, false)
          } else {
            window.scrollTo({ top: 0, behavior: "smooth" })
          }
        }, 80)
      } catch (error) {
        if (controller.signal.aborted) return
        setReportError(error instanceof Error ? error.message : "未知错误")
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void loadReport()
    return () => controller.abort()
  }, [currentDate, currentType, manifest])

  useEffect(
    () => () => {
      if (copiedTimer.current) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  const currentCatalog = useMemo(
    () => manifest?.catalogs.find((catalog) => catalog.id === currentType),
    [manifest, currentType],
  )

  const currentReport = useMemo(
    () => currentCatalog?.reports.find((report) => report.date === currentDate),
    [currentCatalog, currentDate],
  )

  const currentIndex = currentCatalog && currentReport
      ? currentCatalog.reports.findIndex(
          (report) => report.date === currentReport.date,
        )
      : -1

  const selectDate = useCallback(
    (date: string) => {
      history.pushState(
        { date, reportType: currentType },
        "",
        reportUrl(currentType, date),
      )
      setCurrentDate(date)
    },
    [currentType],
  )

  const selectCatalog = useCallback(
    (reportType: ReportType) => {
      const catalog = manifest?.catalogs.find((item) => item.id === reportType)
      if (!catalog) return
      history.pushState(
        { date: catalog.latest, reportType },
        "",
        reportUrl(reportType, catalog.latest),
      )
      setCurrentType(reportType)
      setCurrentDate(catalog.latest)
      setQuery("")
    },
    [manifest],
  )

  const copyCurrentLink = useCallback(async () => {
    if (!currentDate) return
    await navigator.clipboard.writeText(
      reportUrl(currentType, currentDate).toString(),
    )
    setCopied(true)
    if (copiedTimer.current) window.clearTimeout(copiedTimer.current)
    copiedTimer.current = window.setTimeout(() => setCopied(false), 1600)
  }, [currentDate, currentType])

  if (manifestError) return <InitialError message={manifestError} />
  if (!manifest || !currentCatalog || !currentReport) return <InitialLoading />

  const newer = currentCatalog.reports[currentIndex - 1]
  const older = currentCatalog.reports[currentIndex + 1]

  return (
    <TooltipProvider delayDuration={250}>
      <SidebarProvider
        style={
          {
            "--sidebar-width": "18.5rem",
            "--sidebar-width-mobile": "19rem",
          } as CSSProperties
        }
      >
        <AppSidebar
          catalogs={manifest.catalogs}
          currentType={currentType}
          reports={currentCatalog.reports}
          currentDate={currentReport.date}
          query={query}
          onQueryChange={setQuery}
          onSelectCatalog={selectCatalog}
          onSelectDate={selectDate}
        />
        <SidebarInset className="min-w-0 overflow-x-hidden">
          <ReportDashboard
            catalog={currentCatalog}
            report={currentReport}
            markdown={markdown}
            loading={loading}
            error={reportError}
            hasNewer={Boolean(newer)}
            hasOlder={Boolean(older)}
            copied={copied}
            onNewer={() => newer && selectDate(newer.date)}
            onOlder={() => older && selectDate(older.date)}
            onCopy={() => void copyCurrentLink()}
          />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
