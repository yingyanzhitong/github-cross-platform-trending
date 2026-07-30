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
import type { ReportManifest } from "@/types"

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
        const requested = new URL(window.location.href).searchParams.get("date")
        const selected = payload.reports.some((report) => report.date === requested)
          ? requested!
          : payload.latest

        setManifest(payload)
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
      const requested = new URL(window.location.href).searchParams.get("date")
      const selected = manifest.reports.some((report) => report.date === requested)
        ? requested!
        : manifest.latest
      setCurrentDate(selected)
    }

    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [manifest])

  useEffect(() => {
    if (!currentDate) return

    const controller = new AbortController()
    const loadReport = async () => {
      setLoading(true)
      setReportError(null)
      setMarkdown("")

      try {
        const response = await fetch(`reports/${currentDate}.md`, {
          cache: "no-store",
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        setMarkdown(await response.text())
        document.title = `${currentDate} · 跨平台热门软件日报`
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
  }, [currentDate])

  useEffect(
    () => () => {
      if (copiedTimer.current) window.clearTimeout(copiedTimer.current)
    },
    [],
  )

  const currentReport = useMemo(
    () => manifest?.reports.find((report) => report.date === currentDate),
    [manifest, currentDate],
  )

  const currentIndex = manifest && currentReport
    ? manifest.reports.findIndex((report) => report.date === currentReport.date)
    : -1

  const selectDate = useCallback((date: string) => {
    history.pushState({ date }, "", reportUrl(date))
    setCurrentDate(date)
  }, [])

  const copyCurrentLink = useCallback(async () => {
    if (!currentDate) return
    await navigator.clipboard.writeText(reportUrl(currentDate).toString())
    setCopied(true)
    if (copiedTimer.current) window.clearTimeout(copiedTimer.current)
    copiedTimer.current = window.setTimeout(() => setCopied(false), 1600)
  }, [currentDate])

  if (manifestError) return <InitialError message={manifestError} />
  if (!manifest || !currentReport) return <InitialLoading />

  const newer = manifest.reports[currentIndex - 1]
  const older = manifest.reports[currentIndex + 1]

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
          reports={manifest.reports}
          currentDate={currentReport.date}
          query={query}
          onQueryChange={setQuery}
          onSelectDate={selectDate}
        />
        <SidebarInset className="min-w-0 overflow-x-hidden">
          <ReportDashboard
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
