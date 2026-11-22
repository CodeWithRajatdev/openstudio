import React, { useEffect, useRef } from 'react'
import { ArrowLeft, Download, RefreshCcw, Sparkles } from 'lucide-react'
import { useApp } from '../store.jsx'
import { usePreview } from '../usePreview'
import { describeSize } from '../lib/units'
import { calcPages, effectiveMargins } from '../lib/pagePlan'
import { Badge, Button, Card, Notice, PageHeader, Progress, SvgPage } from '../components/ui.jsx'
import { PreviewError, extraPuzzlesFor, seedFor, solutionItemsFor } from '../components/Bits.jsx'

function slugifyName(text, fallback = 'book') {
  const raw = String(text || '').trim().replace(/\.pdf$/i, '')
  const slug = raw.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60)
  return `${slug || fallback}.pdf`
}

const Row = ({ label, value, note, strong }) => (
  <div className={`flex items-baseline justify-between py-2 text-sm ${strong ? 'border-t border-slate-200 pt-3 font-bold text-slate-900' : ''}`}>
    <span className="text-slate-600">
      {label}
      {note && <span className="block text-xs text-slate-400">{note}</span>}
    </span>
    <span className="tabular-nums font-medium">{value}</span>
  </div>
)

export default function ReviewProject() {
  const { state: s, goStep, startJob, retryFailed, startExport } = useApp()
  const L = s.layout
  const A = s.answers
  const ppp = L.puzzles_per_page || 1
  const spp = A.perPage || 1
  const nChapters = s.chapters.length
  const plan = calcPages({ chapters: nChapters, puzzlesPerPage: ppp, solutionsPerPage: spp })
  const eff = effectiveMargins(L, plan.total || 100, 1)

  const firstChapter = s.chapters[0]
  const firstWords = firstChapter?.words.map((w) => w.text) ?? []
  const prev = usePreview({
    words: firstWords,
    title: firstChapter?.title ?? '',
    index: 0,
    seed: seedFor(s, 0),
    config: s.config,
    layout: L,
    answer_style: A.style,
    solutions_per_page: spp,
    total_chapters: Math.max(1, nChapters),
    extra_puzzles: extraPuzzlesFor(s, 0),
    solution_items: solutionItemsFor(s, 0),
  }, !!firstChapter && firstWords.length > 0)

  const blockingErrors = s.issues.filter((i) => i.severity === 'error')
  const canGenerate = nChapters > 0 && blockingErrors.length === 0

  const job = s.job
  const ex = job?.export
  const running = job?.status === 'running' || ex?.state === 'running'
  const failed = (job?.chapters ?? []).filter((c) => !c.ok)
  const allSucceeded =
    !!job &&
    job.status === 'done' &&
    job.total > 0 &&
    job.succeeded === job.total &&
    job.failed === 0 &&
    failed.length === 0

  const autoExportedJobRef = useRef(null)
  const autoDownloadedJobRef = useRef(null)

  const projectName = s.projectName || 'book'
  const pdfFileName = ex?.name || slugifyName(projectName)

  // Automatically build the single vector PDF as soon as all chapters succeed.
  useEffect(() => {
    if (
      allSucceeded &&
      (!ex || ex.state === 'none') &&
      autoExportedJobRef.current !== job.id
    ) {
      autoExportedJobRef.current = job.id
      startExport({
        project_name: projectName,
        per_page_answers: s.answers.perPage,
        answer_style: s.answers.style,
        page_numbers: s.layout.page_numbers,
        include_answers: true,
      })
    }
  }, [allSucceeded, job, ex, projectName, s.answers.perPage, s.answers.style, s.layout.page_numbers, startExport])

  // Automatically trigger the single PDF download in the browser once the PDF is built.
  useEffect(() => {
    if (
      allSucceeded &&
      ex?.state === 'done' &&
      autoDownloadedJobRef.current !== job.id
    ) {
      autoDownloadedJobRef.current = job.id
      const isJsdom = typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent || '')
      if (!isJsdom && typeof document !== 'undefined') {
        const a = document.createElement('a')
        a.href = `/api/wordsearch/jobs/${job.id}/download`
        a.download = pdfFileName
        a.style.display = 'none'
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
      }
    }
  }, [allSucceeded, ex?.state, job?.id, pdfFileName])

  async function handleGenerateAndDownload() {
    if (!canGenerate || running) return
    autoExportedJobRef.current = null
    autoDownloadedJobRef.current = null
    await startJob()
  }

  function handleRetryFailed() {
    if (running) return
    autoExportedJobRef.current = null
    autoDownloadedJobRef.current = null
    retryFailed()
  }

  return (
    <div className="max-w-5xl space-y-6">
      <PageHeader
        title="Review the Whole Project"
        subtitle="Check your project summary, automatic page calculation, margins and first-page previews before generating."
      />

      {blockingErrors.length > 0 && (
        <Notice tone="error" title="Generation is blocked">
          <ul className="mt-1 list-disc pl-5">
            {blockingErrors.slice(0, 5).map((e, i) => (
              <li key={i}>{e.message}</li>
            ))}
          </ul>
        </Notice>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Project & Setup Summary">
          <div className="divide-y divide-slate-100">
            <Row label="Project name" value={s.projectName} />
            <Row label="Trim size" value={describeSize(L.page_width, L.page_height)} />
            <Row label="Chapters" value={nChapters} />
            <Row label="Words per chapter" value={s.wordsPerChapter != null ? `${s.wordsPerChapter} words` : 'Flexible'} />
            <Row label="Titles" value={L.title_enabled ? 'ON (Enabled)' : 'OFF (Disabled)'} />
            <Row
              label="Guideline mode"
              value={L.margin_mode === 'kdp' ? 'Amazon KDP guidelines' : 'Paper edges'}
              note={`Effective Page 1 margins: Top ${eff.top} · Right ${eff.right} · Bottom ${eff.bottom} · Left ${eff.left} mm`}
            />
          </div>
        </Card>

        <Card
          title="Automatic Page Calculation"
          action={<Badge tone="indigo">{`${plan.total} Total Pages`}</Badge>}
        >
          <div className="space-y-0.5">
            <Row
              label="Puzzle pages"
              value={plan.puzzlePages}
              note={`${nChapters} chapter(s) ÷ ${ppp} puzzle(s) per page`}
            />
            <Row
              label="Solution pages"
              value={plan.answerPages}
              note={`${nChapters} chapter(s) ÷ ${spp} solution(s) per page`}
            />
            <Row
              label="Blank page"
              value={plan.blankPages}
              note={plan.blankPages ? '+1 added because puzzle + solution pages is odd' : 'Even total — no extra blank page needed'}
            />
            <Row strong label="TOTAL PAGES" value={plan.total} />
          </div>
        </Card>
      </div>

      <Card title="Preview of First Puzzle Page & First Solution Page">
        <PreviewError error={prev.error} />
        {prev.loading && !prev.data && (
          <p className="py-12 text-center text-sm text-slate-500">Rendering first puzzle and solution pages…</p>
        )}
        {prev.data && (
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <div className="mb-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
                First Puzzle Page
              </div>
              <SvgPage svg={prev.data.puzzle_svg} zoom={100} layout={L} />
            </div>
            <div>
              <div className="mb-2 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
                First Solution Page
              </div>
              <SvgPage svg={prev.data.answer_svg} zoom={100} layout={L} />
            </div>
          </div>
        )}
      </Card>

      {s.jobError && <Notice tone="error" title="Could not generate">{s.jobError}</Notice>}

      {ex?.state === 'error' && (
        <Notice tone="error" title="PDF export failed">
          {ex.message}
        </Notice>
      )}

      {job && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold tabular-nums" data-testid="job-progress-text">
              {job.done} / {job.total} chapters
            </span>
          </div>
          <Progress
            value={job.done}
            max={job.total}
            tone={allSucceeded && ex?.state === 'done' ? 'green' : 'indigo'}
          />

          {failed.length > 0 && !running && (
            <div className="space-y-3 pt-2">
              <ul className="space-y-2 text-sm text-red-700" data-testid="failed-chapters-list">
                {failed.map((c) => (
                  <li key={c.index}>
                    Chapter {c.index + 1}{c.title ? ` (${c.title})` : ''}: {c.error}
                  </li>
                ))}
              </ul>
              <div>
                <Button variant="secondary" icon={RefreshCcw} onClick={handleRetryFailed}>
                  Retry failed chapters
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-4 pt-2">
        <Button variant="secondary" icon={ArrowLeft} disabled={running} onClick={() => goStep(3)}>
          Back to edit
        </Button>
        <div className="flex flex-wrap items-center gap-3">
          {allSucceeded && ex?.state === 'done' && (
            <a
              href={`/api/wordsearch/jobs/${job.id}/download`}
              download={pdfFileName}
              data-testid="download-pdf-link"
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
            >
              <Download size={16} />
              {pdfFileName}
            </a>
          )}
          <Button
            icon={Sparkles}
            loading={running}
            disabled={!canGenerate || running}
            onClick={handleGenerateAndDownload}
          >
            Generate and Download
          </Button>
        </div>
      </div>
    </div>
  )
}
