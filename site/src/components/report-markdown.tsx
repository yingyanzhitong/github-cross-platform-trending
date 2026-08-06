import type { ComponentProps } from "react"
import { Download } from "lucide-react"
import ReactMarkdown, { type Components } from "react-markdown"
import rehypeRaw from "rehype-raw"
import rehypeSanitize, { defaultSchema } from "rehype-sanitize"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { scrollToAnchor, splitReportMarkdown } from "@/lib/report"

const sanitizeSchema = {
  ...defaultSchema,
  clobberPrefix: "",
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), "id", "target", "rel"],
  },
}

function MarkdownLink({ href, children, ...props }: ComponentProps<"a">) {
  if (!href) {
    return <a {...props}>{children}</a>
  }

  if (href.startsWith("#")) {
    return (
      <Button asChild variant="outline" size="xs">
        <a
          href={href}
          {...props}
          onClick={(event) => {
            event.preventDefault()
            scrollToAnchor(href)
          }}
        >
          {children}
        </a>
      </Button>
    )
  }

  const external = href.startsWith("http")
  const releaseAsset = /^https:\/\/github\.com\/[^/]+\/[^/]+\/releases\/download\//.test(
    href,
  )
  return (
    <a
      href={href}
      {...props}
      className="inline-flex items-center gap-1 font-medium text-primary underline decoration-primary/25 underline-offset-4 transition-colors hover:decoration-primary"
      target={external && !releaseAsset ? "_blank" : undefined}
      rel={external ? "noreferrer" : undefined}
      title={releaseAsset ? "直接下载安装包" : undefined}
    >
      {children}
      {releaseAsset ? <Download aria-hidden="true" className="size-3 shrink-0" /> : null}
    </a>
  )
}

const markdownComponents = {
  a: ({ node: _node, ...props }) => <MarkdownLink {...props} />,
  table: ({ node: _node, ...props }) => (
    <Table className="report-table min-w-[100rem]" {...props} />
  ),
  thead: ({ node: _node, ...props }) => <TableHeader {...props} />,
  tbody: ({ node: _node, ...props }) => <TableBody {...props} />,
  tr: ({ node: _node, ...props }) => <TableRow {...props} />,
  th: ({ node: _node, ...props }) => <TableHead {...props} />,
  td: ({ node: _node, ...props }) => <TableCell {...props} />,
  h1: ({ node: _node, ...props }) => (
    <h1 className="font-heading text-2xl font-semibold tracking-tight" {...props} />
  ),
  h2: ({ node: _node, ...props }) => (
    <h2 className="font-heading text-xl font-semibold tracking-tight" {...props} />
  ),
  h3: ({ node: _node, ...props }) => (
    <h3
      className="font-heading text-xl font-semibold tracking-tight text-foreground"
      {...props}
    />
  ),
  h4: ({ node: _node, ...props }) => (
    <h4
      className="mt-6 border-b pb-2 font-heading text-sm font-semibold tracking-wide text-foreground"
      {...props}
    />
  ),
  p: ({ node: _node, ...props }) => (
    <p className="text-sm leading-7 text-foreground/80" {...props} />
  ),
  ul: ({ node: _node, ...props }) => (
    <ul className="grid list-disc gap-2 pl-5 text-sm leading-7 text-foreground/80" {...props} />
  ),
  ol: ({ node: _node, ...props }) => (
    <ol
      className="grid list-decimal gap-2 pl-5 text-sm leading-7 text-foreground/80"
      {...props}
    />
  ),
  blockquote: ({ node: _node, ...props }) => (
    <blockquote
      className="border-l-2 border-primary bg-primary/5 px-4 py-3 text-sm text-muted-foreground"
      {...props}
    />
  ),
  code: ({ node: _node, ...props }) => (
    <code
      className="rounded bg-muted px-1.5 py-0.5 font-data text-[0.82em] text-foreground"
      {...props}
    />
  ),
  pre: ({ node: _node, ...props }) => (
    <pre
      className="overflow-x-auto rounded-lg border bg-muted/60 p-4 font-data text-xs"
      {...props}
    />
  ),
  hr: ({ node: _node, ...props }) => <Separator className="my-8" {...props} />,
} satisfies Components

function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema]]}
      components={markdownComponents}
    >
      {children}
    </ReactMarkdown>
  )
}

export function ReportMarkdown({ markdown }: { markdown: string }) {
  const { overview, sections } = splitReportMarkdown(markdown)

  return (
    <div id="report-content" className="grid min-w-0 gap-5" aria-live="polite">
      <Card className="report-overview min-w-0 py-0">
        <CardContent className="min-w-0 px-0">
          <div className="report-markdown">
            <Markdown>{overview}</Markdown>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4">
        {sections.map((section) => (
          <Card
            key={section.id}
            id={section.id}
            className="report-detail scroll-mt-20 transition-shadow target:ring-2 target:ring-primary/45"
          >
            <CardContent className="report-markdown">
              <Markdown>{section.markdown}</Markdown>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
