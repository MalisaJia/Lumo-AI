// Markdown 渲染：GFM + 数学公式 + 代码高亮，代码块带语言标签与复制按钮
import { Fragment, memo, useState, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github-dark.css'
import { toast } from '../../stores/toastStore'

function extractText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return extractText((node as { props: { children?: ReactNode } }).props.children)
  }
  return ''
}

function CodeBlock({ className, children }: { className?: string; children?: ReactNode }) {
  const [copied, setCopied] = useState(false)
  const lang = /language-(\w+)/.exec(className ?? '')?.[1] ?? 'text'

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(extractText(children).replace(/\n$/, ''))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('复制失败')
    }
  }

  return (
    <div className="group/code my-3 overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-700">
      <div className="flex items-center justify-between bg-neutral-100 px-3 py-1.5 text-xs text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400">
        <span className="font-mono">{lang}</span>
        <button
          onClick={handleCopy}
          className="rounded px-1.5 py-0.5 transition-colors hover:bg-neutral-200 hover:text-neutral-700 dark:hover:bg-neutral-700 dark:hover:text-neutral-200"
        >
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="!m-0 overflow-x-auto bg-[#0d1117] p-3 text-sm leading-relaxed">
        <code className={className}>{children}</code>
      </pre>
    </div>
  )
}

interface MarkdownRendererProps {
  content: string
  // 开启后把正文纯文本中的 [数字] 渲染为高亮上标角标（不影响代码块）
  citations?: boolean
}

// 只处理字符串子节点；嵌套元素（含行内代码）保持原样，避免误伤
function renderCitations(node: ReactNode): ReactNode {
  if (typeof node === 'string') {
    const parts = node.split(/(\[\d{1,2}\])/g)
    if (parts.length === 1) return node
    return parts.map((part, i) => {
      const m = /^\[(\d{1,2})\]$/.exec(part)
      if (!m) return <Fragment key={i}>{part}</Fragment>
      return (
        <sup
          key={i}
          className="mx-0.5 rounded bg-violet-100 px-1 py-px text-[0.7em] font-medium text-violet-600 dark:bg-violet-500/20 dark:text-violet-300"
        >
          {m[1]}
        </sup>
      )
    })
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => <Fragment key={i}>{renderCitations(child)}</Fragment>)
  }
  return node
}

function MarkdownRendererInner({ content, citations = false }: MarkdownRendererProps) {
  const withCitations = (children: ReactNode) =>
    citations ? renderCitations(children) : children

  return (
    <div className="markdown-body max-w-none text-[15px] leading-7 text-neutral-800 dark:text-neutral-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { ignoreMissing: true, detect: false }]]}
        components={{
          pre({ children }) {
            // 交由 code 组件渲染完整代码块外壳
            return <>{children}</>
          },
          code({ className, children, ...props }) {
            const isBlock = /language-/.test(className ?? '') || extractText(children).includes('\n')
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>
            }
            return (
              <code
                className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[0.9em] text-violet-600 dark:bg-neutral-800 dark:text-violet-300"
                {...props}
              >
                {children}
              </code>
            )
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto rounded-xl border border-neutral-200 dark:border-neutral-700">
                <table className="w-full border-collapse text-sm">{children}</table>
              </div>
            )
          },
          th({ children }) {
            return (
              <th className="border-b border-neutral-200 bg-neutral-50 px-3 py-2 text-left font-semibold dark:border-neutral-700 dark:bg-neutral-800">
                {children}
              </th>
            )
          },
          td({ children }) {
            return (
              <td className="border-b border-neutral-100 px-3 py-2 dark:border-neutral-800">
                {children}
              </td>
            )
          },
          a({ children, href }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-violet-600 underline underline-offset-2 hover:text-violet-500 dark:text-violet-400"
              >
                {children}
              </a>
            )
          },
          ul({ children }) {
            return <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>
          },
          ol({ children }) {
            return <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>
          },
          li({ children }) {
            return <li>{withCitations(children)}</li>
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-3 border-l-4 border-violet-300 pl-4 text-neutral-600 dark:border-violet-700 dark:text-neutral-400">
                {children}
              </blockquote>
            )
          },
          h1({ children }) {
            return <h1 className="mt-5 mb-3 text-2xl font-bold">{children}</h1>
          },
          h2({ children }) {
            return <h2 className="mt-4 mb-2 text-xl font-bold">{children}</h2>
          },
          h3({ children }) {
            return <h3 className="mt-3 mb-2 text-lg font-semibold">{children}</h3>
          },
          p({ children }) {
            return <p className="my-2">{withCitations(children)}</p>
          },
          hr() {
            return <hr className="my-4 border-neutral-200 dark:border-neutral-700" />
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export const MarkdownRenderer = memo(MarkdownRendererInner)
