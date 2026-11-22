import React, { useState } from 'react'
import {
  ChevronLeft, ChevronRight, Dices, Pin, PinOff,
  RefreshCw, ZoomIn, ZoomOut,
} from 'lucide-react'
import { useApp } from '../store.jsx'
import { usePreview } from '../usePreview'
import { describeSize } from '../lib/units'
import { calcPages, effectiveMargins } from '../lib/pagePlan'
import { Badge, Button, Card, Field, NumberInput, SvgPage, Toggle } from '../components/ui.jsx'
import { ChapterSelect, NoWords, PreviewError, extraPuzzlesFor, seedFor, solutionItemsFor, useChapterWords } from '../components/Bits.jsx'

const ZOOMS = [50, 75, 100, 125, 150, 200]

export default function Preview() {
  const { state: s, patch, dispatch } = useApp()
  const { index, chapter, words } = useChapterWords(s)
  const [tab, setTab] = useState('puzzle')           // 'puzzle' | 'answer' | 'both'
  const [zoom, setZoom] = useState(100)
  const [showMargins, setShowMargins] = useState(false)
  const pinned = s.chapterSeeds[index] != null
  const seed = seedFor(s, index)
  const [trial, setTrial] = useState(null)           // un-pinned experimental seed
  const useSeed = trial ?? seed
  const L = s.layout
  const spp = s.answers.perPage || 1
  const ppp = L.puzzles_per_page || 1
  const totalChapters = Math.max(1, s.chapters.length)
  const plan = calcPages({ chapters: totalChapters, puzzlesPerPage: ppp, solutionsPerPage: spp })

  const prev = usePreview({
    words,
    title: chapter?.title ?? '',
    index,
    seed: useSeed,
    config: s.config,
    layout: L,
    answer_style: s.answers.style,
    solutions_per_page: spp,
    total_chapters: totalChapters,
    extra_puzzles: extraPuzzlesFor(s, index),
    solution_items: solutionItemsFor(s, index),
  }, !!chapter && words.length > 0)

  const stepChapter = (d) => {
    setTrial(null)
    patch({ selectedChapter: Math.max(0, Math.min(s.chapters.length - 1, index + d)) })
  }

  const stepZoom = (dir) => {
    const idx = ZOOMS.indexOf(zoom)
    if (dir < 0 && idx > 0) setZoom(ZOOMS[idx - 1])
    if (dir > 0 && idx < ZOOMS.length - 1) setZoom(ZOOMS[idx + 1])
  }

  const pageNumber = Math.floor(index / ppp) + 1
  const eff = effectiveMargins(L, plan.total || 100, pageNumber)

  return (
    <div>
      {!s.chapters.length ? <NoWords /> : (
        <div className="space-y-4">
          <div className="space-y-3">
            {/* Navigation & View Bar */}
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 shadow-sm">
              <Button variant="secondary" aria-label="Previous chapter" onClick={() => stepChapter(-1)} disabled={index === 0}>
                <ChevronLeft size={16} />
              </Button>
              <ChapterSelect />
              <Button variant="secondary" aria-label="Next chapter" onClick={() => stepChapter(1)} disabled={index >= s.chapters.length - 1}>
                <ChevronRight size={16} />
              </Button>

              <div className="flex items-center gap-1 rounded-lg border border-slate-200 px-1.5 py-1 text-xs text-slate-600">
                <button type="button" aria-label="Zoom out" disabled={zoom <= ZOOMS[0]}
                  onClick={() => stepZoom(-1)}
                  className="rounded p-1 hover:bg-slate-100 disabled:opacity-40">
                  <ZoomOut size={15} />
                </button>
                <button type="button" onClick={() => setZoom(100)} title="Reset zoom"
                  className="min-w-[3.2rem] text-center font-semibold tabular-nums">
                  {zoom}%
                </button>
                <button type="button" aria-label="Zoom in" disabled={zoom >= ZOOMS[ZOOMS.length - 1]}
                  onClick={() => stepZoom(1)}
                  className="rounded p-1 hover:bg-slate-100 disabled:opacity-40">
                  <ZoomIn size={15} />
                </button>
              </div>

              <Button variant="ghost" icon={RefreshCw} onClick={() => prev.refresh()} title="Regenerate preview">
                Refresh
              </Button>

              <div className="ml-auto flex rounded-lg border border-slate-300 p-0.5 text-sm">
                {[
                  ['puzzle', 'Puzzle page'],
                  ['answer', 'Solution page'],
                  ['both', 'Side by side'],
                ].map(([id, l]) => (
                  <button key={id} type="button" onClick={() => setTab(id)}
                    className={`rounded-md px-3 py-1 ${tab === id ? 'bg-indigo-600 text-white' : 'text-slate-600'}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>

            <PreviewError error={prev.error} />

            {prev.data && (
              tab === 'both' ? (
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="mb-1.5 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Puzzle Page
                    </div>
                    <SvgPage svg={prev.data.puzzle_svg} zoom={zoom} showMarginGuide={showMargins} layout={L} />
                  </div>
                  <div>
                    <div className="mb-1.5 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Solution Page
                    </div>
                    <SvgPage svg={prev.data.answer_svg} zoom={zoom} showMarginGuide={showMargins} layout={L} />
                  </div>
                </div>
              ) : (
                <div className="mx-auto max-w-xl">
                  <SvgPage
                    svg={tab === 'puzzle' ? prev.data.puzzle_svg : prev.data.answer_svg}
                    zoom={zoom}
                    showMarginGuide={showMargins}
                    layout={L}
                  />
                </div>
              )
            )}
            {prev.loading && !prev.data && (
              <p className="py-20 text-center text-sm text-slate-500">Rendering…</p>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Card title="This puzzle">
              {prev.data ? (
                <dl className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Chapter</dt>
                    <dd className="font-medium">{index + 1} of {s.chapters.length}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Title shown</dt>
                    <dd className="truncate pl-3 font-medium">{prev.data.resolved_title || '(Disabled)'}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Grid</dt>
                    <dd>{prev.data.rows} × {prev.data.cols}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Seed</dt>
                    <dd>{prev.data.seed} {pinned && !trial && <Badge tone="indigo">pinned</Badge>}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-slate-500">Words placed</dt>
                    <dd>{prev.data.key.length} / {words.length}</dd>
                  </div>
                </dl>
              ) : <p className="text-sm text-slate-500">No puzzle yet.</p>}

              <div className="mt-4 space-y-2">
                <Field label="Try a seed">
                  <NumberInput value={useSeed} onChange={(v) => setTrial(v === '' ? 0 : v)} />
                </Field>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" icon={Dices} onClick={() => setTrial(Math.floor(Math.random() * 1e9))}>
                    Random seed
                  </Button>
                  {(trial != null && trial !== seed) && (
                    <Button icon={Pin} onClick={() => { dispatch({ type: 'pinSeed', ci: index, seed: trial }); setTrial(null) }}>
                      Pin for this chapter
                    </Button>
                  )}
                  {pinned && (
                    <Button variant="ghost" icon={PinOff} onClick={() => { dispatch({ type: 'unpinSeed', ci: index }); setTrial(null) }}>
                      Unpin
                    </Button>
                  )}
                </div>
              </div>
            </Card>

            <Card title="Page layout summary">
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <dt className="text-slate-500">Trim size</dt>
                  <dd className="font-medium">{describeSize(L.page_width, L.page_height)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Margins (T/R/B/L)</dt>
                  <dd>{eff.top}/{eff.right}/{eff.bottom}/{eff.left} mm</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Grid font</dt>
                  <dd>{L.grid_font} ({L.grid_font_weight})</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Clues</dt>
                  <dd>{L.clue_columns} cols · {L.clue_sort.replace('_', '→')}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-500">Grid alignment</dt>
                  <dd className="capitalize">{L.puzzle_align} / {L.puzzle_valign}</dd>
                </div>
              </dl>
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                <Toggle label="Show margin guide" checked={showMargins} onChange={setShowMargins} />
              </div>
            </Card>

            {prev.data && (
              <div className="sm:col-span-2">
                <Card title="Answer coordinates">
                  <ul className="max-h-64 space-y-1 overflow-auto text-xs">
                    {prev.data.key.map((k) => (
                      <li key={k.word} className="flex justify-between gap-2">
                        <b>{k.word}</b>
                        <span className="text-slate-500">
                          R{k.start[0]}C{k.start[1]} → R{k.end[0]}C{k.end[1]} · {k.direction}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
