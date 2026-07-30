import {
  BadgeCheckIcon,
  CalendarDaysIcon,
  ExternalLinkIcon,
  GitBranchIcon,
  LaptopIcon,
  SearchIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInput,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar"
import { reportMatches, reportUrl } from "@/lib/report"
import type { ReportSummary } from "@/types"

type AppSidebarProps = {
  reports: ReportSummary[]
  currentDate: string
  query: string
  onQueryChange: (query: string) => void
  onSelectDate: (date: string) => void
}

export function AppSidebar({
  reports,
  currentDate,
  query,
  onQueryChange,
  onSelectDate,
}: AppSidebarProps) {
  const { setOpenMobile } = useSidebar()
  const filteredReports = reports.filter((report) => reportMatches(report, query))

  const selectDate = (date: string) => {
    onSelectDate(date)
    setOpenMobile(false)
  }

  return (
    <Sidebar variant="inset" collapsible="offcanvas">
      <SidebarHeader className="gap-3 p-4">
        <a
          href="./"
          className="group flex items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-sidebar-ring/50"
          aria-label="返回最新日报"
        >
          <span className="flex size-10 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground shadow-sm">
            <LaptopIcon className="size-5" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <strong className="block truncate font-heading text-base leading-tight">
              跨平台软件日报
            </strong>
            <span className="font-data text-[0.64rem] tracking-[0.16em] text-sidebar-foreground/55">
              MACOS ↔ WINDOWS
            </span>
          </span>
        </a>

        <Badge
          variant="outline"
          className="h-auto justify-start gap-2 rounded-lg border-success/30 bg-success/10 px-2.5 py-2 text-success-foreground"
        >
          <BadgeCheckIcon data-icon="inline-start" />
          Latest Release 双端安装包验证
        </Badge>

        <label className="relative block">
          <span className="sr-only">筛选日期或项目</span>
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <SidebarInput
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            className="h-9 pl-8"
            type="search"
            placeholder="筛选日期或项目"
            autoComplete="off"
          />
        </label>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="gap-2">
            <CalendarDaysIcon className="size-3.5" aria-hidden="true" />
            日报归档
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu aria-label="日报日期">
              {filteredReports.map((report) => (
                <SidebarMenuItem key={report.date}>
                  <SidebarMenuButton
                    asChild
                    size="lg"
                    isActive={report.date === currentDate}
                    tooltip={report.date}
                    className="h-auto min-h-12 py-2"
                  >
                    <a
                      href={reportUrl(report.date).toString()}
                      onClick={(event) => {
                        event.preventDefault()
                        selectDate(report.date)
                      }}
                    >
                      <span
                        className="size-2 rounded-full bg-border data-[active=true]:bg-primary"
                        data-active={report.date === currentDate}
                        aria-hidden="true"
                      />
                      <span className="grid min-w-0 flex-1 gap-0.5">
                        <span className="font-data text-xs font-semibold">
                          {report.date}
                        </span>
                        <span className="truncate text-[0.7rem] text-muted-foreground">
                          {report.new_projects.length} 个新增 ·{" "}
                          {report.warnings_count} 个警告
                        </span>
                      </span>
                    </a>
                  </SidebarMenuButton>
                  <SidebarMenuBadge>{report.software_count}</SidebarMenuBadge>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
            {filteredReports.length === 0 && (
              <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                没有匹配的日报或项目
              </p>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarSeparator />

      <SidebarFooter className="gap-3 p-4">
        <Button asChild variant="outline" className="w-full justify-between">
          <a
            href="https://github.com/yingyanzhitong/github-cross-platform-trending"
            target="_blank"
            rel="noreferrer"
          >
            <span className="inline-flex items-center gap-2">
              <GitBranchIcon aria-hidden="true" />
              GitHub 源码仓库
            </span>
            <ExternalLinkIcon aria-hidden="true" />
          </a>
        </Button>
        <p className="text-xs leading-relaxed text-muted-foreground">
          只收录 Latest Release 同时提供 macOS 与 Windows 安装程序的软件。
        </p>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
