import React, { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Copy, PanelRightClose, PanelRightOpen, RotateCcw } from 'lucide-react'
import { useApp } from '../store.jsx'
import {
  ALIGNMENTS, CLUE_SORTS, CLUE_TYPES, DIFFICULTY, FONT_CHOICES, FONT_STYLES,
  HIGHLIGHTS, VALIGNMENTS, WORD_COUNT_PRESETS, decodeFontStyle, encodeFontStyle,
  mmToPx, pxToMm,
} from '../defaults'
import { describeSize } from '../lib/units'
import { calcPages, effectiveMargins } from '../lib/pagePlan'
import ImportWords from './ImportWords.jsx'
import Preview from './Preview.jsx'
import {
  Badge, Button, Card, ColorInput, Field, Notice, NumberInput, PageHeader,
  Section, Select, TextInput, Toggle,
} from '../components/ui.jsx'

const MODES = [
  ['auto', 'Automatic', 'The engine estimates a size, tries placement and grows until every word fits.'],
  ['manual', 'Manual', 'Exact size. If words do not fit you get a clear failure, never a silent drop.'],
  ['manual_auto_adjust', 'Manual + auto-adjust', 'Start at your size, expand until success or the maximum.'],
]

export default function PuzzleSettings() {
  const { state: s, patch, dispatch, goStep } = useApp()
  const c = s.config
  const L = s.layout
  const A = s.answers
  const setC = (p) => patch({ config: { ...c, ...p } })
  const setL = (p) => patch({ layout: { ...L, ...p } })
  const setA = (p) => patch({ answers: { ...A, ...p } })

  const [lineUnit, setLineUnit] = useState('px')
  const [customWordCount, setCustomWordCount] = useState(
    s.wordsPerChapter != null && !WORD_COUNT_PRESETS.includes(s.wordsPerChapter)
  )
  const [solutionOpen, setSolutionOpen] = useState(true)
  const [titleOpen, setTitleOpen] = useState(true)
  const [copiedNotice, setCopiedNotice] = useState(false)
  const [showPreview, setShowPreview] = useState(true)
  const [splitPct, setSplitPct] = useState(56)
  const [dragging, setDragging] = useState(false)
  const splitRef = useRef(null)

  useEffect(() => {
    if (!dragging) return undefined
    const onMove = (e) => {
      const el = splitRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      if (!rect.width) return
      const pct = ((e.clientX - rect.left) / rect.width) * 100
      setSplitPct(Math.min(75, Math.max(30, pct)))
    }
    const onUp = () => setDragging(false)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [dragging])

  const currentDiff = Object.entries(DIFFICULTY).find(([, d]) =>
    d.horizontal === c.horizontal && d.vertical === c.vertical && d.diagonal === c.diagonal && d.reverse === c.reverse)?.[0]

  const expected = s.wordsPerChapter
  const wordCountSel = WORD_COUNT_PRESETS.includes(expected) && !customWordCount
    ? String(expected)
    : expected == null && !customWordCount ? 'none' : 'custom'

  const plan = calcPages({
    chapters: Math.max(1, s.chapters.length),
    puzzlesPerPage: L.puzzles_per_page || 1,
    solutionsPerPage: A.perPage || 1,
  })
  const eff = effectiveMargins(L, plan.total || 100, 1)
  const effectiveTop = eff.top
  const effectiveRight = eff.right
  const effectiveBottom = eff.bottom
  const effectiveLeft = eff.left

  const lineWidthDisplay = lineUnit === 'px' ? mmToPx(L.grid_line_width) : L.grid_line_width
  const borderWidthDisplay = lineUnit === 'px' ? mmToPx(L.border_width) : L.border_width
  const solLineWidthMm = L.solution_line_width ?? L.grid_line_width
  const solLineWidthDisplay = lineUnit === 'px' ? mmToPx(solLineWidthMm) : solLineWidthMm

  function handleCopyAppearance() {
    dispatch({ type: 'copyAppearanceToSolution' })
    setCopiedNotice(true)
    setTimeout(() => setCopiedNotice(false), 2500)
  }

  function insertPlaceholder(token) {
    const cur = L.title_text || ''
    const sep = cur && !cur.endsWith(' ') && !cur.endsWith('#') ? ' ' : ''
    setL({ title_mode: 'custom', title_text: `${cur}${sep}${token}` })
  }

  const blockingErrors = s.issues.filter((i) => i.severity === 'error').length
  const canContinue = s.chapters.length > 0 && blockingErrors === 0 && !s.validating

  return (
    <div className="space-y-5">
      <div className="fixed bottom-5 right-8 z-40">
        <Button
          type="button"
          variant="secondary"
          className="bg-white/95 shadow-lg ring-1 ring-slate-200 backdrop-blur"
          icon={showPreview ? PanelRightClose : PanelRightOpen}
          onClick={() => setShowPreview((v) => !v)}
        >
          {showPreview ? 'Hide Preview' : 'Show Preview'}
        </Button>
      </div>

      <PageHeader
        title="Puzzle Setup"
        subtitle={`Trim size: ${describeSize(L.page_width, L.page_height)} · Configure page, word, puzzle, clues, solution and title settings, then import your word list and preview on the right.`}
      >
        <Button variant="secondary" icon={RotateCcw} onClick={() => dispatch({ type: 'resetSettings' })}>
          Reset to Default
        </Button>
      </PageHeader>

      <div
        ref={splitRef}
        style={showPreview ? { '--split-left': `${splitPct}%` } : undefined}
        className={
          showPreview
            ? 'grid items-start gap-y-6 lg:grid-cols-[minmax(0,var(--split-left))_14px_minmax(0,1fr)]'
            : 'mx-auto max-w-5xl'
        }
      >
        <div className="min-w-0 space-y-5 lg:pr-1">
      {/* ==================== A. PAGE SETTINGS ==================== */}
      <Section
        testId="section-page-settings"
        title="Page Settings"
        subtitle="Margins, Amazon KDP guidelines or paper edges, and optional independent side adjustments."
        badge={<Badge tone="slate">{`${L.margin_mode === 'kdp' ? 'Amazon KDP · ' : ''}${effectiveTop}/${effectiveRight}/${effectiveBottom}/${effectiveLeft} mm`}</Badge>}
        defaultOpen
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Guideline Mode" hint="Choose Amazon KDP mirrored gutter minimums or direct paper edges.">
            <Select
              aria-label="Guideline Mode"
              value={L.margin_mode || 'edges'}
              onChange={(e) => setL({ margin_mode: e.target.value })}
              options={[
                ['edges', 'Paper edges (custom margins)'],
                ['kdp', 'Amazon KDP guidelines'],
              ]}
            />
          </Field>
          <Field label="Paper Edges (mm)" hint="Base margin applied from the paper edges.">
            <NumberInput aria-label="Paper Edges" min={0} max={80} step={0.5} value={L.margin}
              onChange={(v) => v !== '' && setL({ margin: Math.max(0, v) })} />
          </Field>
          {L.margin_mode !== 'kdp' ? (
            <div className="flex items-center pt-5">
              <Toggle
                label="Set Additional Margins"
                hint="Adjust top, left, bottom and right margins independently."
                checked={L.extra_margins}
                onChange={(v) => setL({ extra_margins: v })}
              />
            </div>
          ) : (
            <div className="rounded-lg bg-indigo-50/70 px-3.5 py-2.5 text-xs text-indigo-900">
              <div className="font-semibold">KDP Gutter Active</div>
              <div className="mt-0.5">Inside (binding): {eff.inside} mm · Outside: {eff.outside} mm (mirrored on even/odd pages)</div>
            </div>
          )}
          <div className="rounded-lg bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600">
            <div className="font-semibold text-slate-700">Printable area</div>
            <div className="mt-0.5">
              {Math.max(0, Math.round((L.page_width - effectiveLeft - effectiveRight) * 10) / 10)} ×{' '}
              {Math.max(0, Math.round((L.page_height - effectiveTop - effectiveBottom) * 10) / 10)} mm
            </div>
            <div className="text-slate-400">
              Top {effectiveTop} · Left {effectiveLeft} · Bottom {effectiveBottom} · Right {effectiveRight} mm
            </div>
          </div>
        </div>

        {L.margin_mode !== 'kdp' && L.extra_margins && (
          <div className="mt-4 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 sm:grid-cols-4">
            <Field label="Top Margin (mm)">
              <NumberInput aria-label="Top Margin" min={0} max={80} step={0.5} value={L.margin_top}
                onChange={(v) => setL({ margin_top: v === '' ? 0 : Math.max(0, v) })} />
            </Field>
            <Field label="Left Margin (mm)">
              <NumberInput aria-label="Left Margin" min={0} max={80} step={0.5} value={L.margin_left}
                onChange={(v) => setL({ margin_left: v === '' ? 0 : Math.max(0, v) })} />
            </Field>
            <Field label="Bottom Margin (mm)">
              <NumberInput aria-label="Bottom Margin" min={0} max={80} step={0.5} value={L.margin_bottom}
                onChange={(v) => setL({ margin_bottom: v === '' ? 0 : Math.max(0, v) })} />
            </Field>
            <Field label="Right Margin (mm)">
              <NumberInput aria-label="Right Margin" min={0} max={80} step={0.5} value={L.margin_right}
                onChange={(v) => setL({ margin_right: v === '' ? 0 : Math.max(0, v) })} />
            </Field>
          </div>
        )}
        <div className="mt-4 border-t border-slate-100 pt-3">
          <Toggle
            label="Print Page Numbers on Pages"
            hint="Draws the book page number at the bottom of puzzle and solution pages."
            checked={L.page_numbers}
            onChange={(v) => setL({ page_numbers: v })}
          />
        </div>
      </Section>

      {/* ==================== B. WORD SETTINGS ==================== */}
      <Section
        testId="section-word-settings"
        title="Word Settings"
        subtitle="Words per puzzle, allowed directions, difficulty presets and grid sizing."
        badge={<Badge tone="indigo">{expected ? `${expected} words / puzzle` : 'Flexible count'}</Badge>}
        defaultOpen
      >
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1">
                <Field label="Words Per Puzzle" hint="Every imported chapter is validated against this word count.">
                  <Select aria-label="Words Per Puzzle" value={wordCountSel} onChange={(e) => {
                    const v = e.target.value
                    if (v === 'custom') { setCustomWordCount(true); return }
                    setCustomWordCount(false)
                    patch({ wordsPerChapter: v === 'none' ? null : Number(v) })
                  }} options={[
                    ...WORD_COUNT_PRESETS.map((n) => [String(n), `${n} words`]),
                    ['custom', 'Custom count…'],
                    ['none', 'No fixed count'],
                  ]} />
                </Field>
              </div>
              {wordCountSel === 'custom' && (
                <div className="w-28">
                  <Field label="Custom">
                    <NumberInput aria-label="Custom Words Per Puzzle" min={1} max={500} value={expected ?? ''}
                      onChange={(v) => patch({ wordsPerChapter: v === '' ? null : Math.max(1, v) })} />
                  </Field>
                </div>
              )}
            </div>

            <div>
              <div className="mb-1.5 text-sm font-medium text-slate-700">Difficulty Preset</div>
              <div className="grid grid-cols-3 gap-2">
                {Object.keys(DIFFICULTY).map((k) => (
                  <button key={k} type="button" onClick={() => setC(DIFFICULTY[k])}
                    className={`rounded-lg border px-3 py-2 text-sm font-medium capitalize ${
                      currentDiff === k ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-300 hover:bg-slate-50'
                    }`}>{k}</button>
                ))}
              </div>
              <p className="mt-1 text-xs text-slate-500">{currentDiff ? `Preset: ${currentDiff}` : 'Custom direction combination'}</p>
            </div>

            <div className="space-y-2.5 pt-1">
              <Toggle label="Horizontal" checked={c.horizontal} onChange={(v) => setC({ horizontal: v })} />
              <Toggle label="Vertical" checked={c.vertical} onChange={(v) => setC({ vertical: v })} />
              <Toggle label="Diagonal Words" checked={c.diagonal} onChange={(v) => setC({ diagonal: v })} />
              <Toggle label="Reverse placement (Reverse Words)" checked={c.reverse} onChange={(v) => setC({ reverse: v })}
                hint="APPLE may appear as ELPPA; the clue list still shows APPLE." />
            </div>
            {!c.horizontal && !c.vertical && !c.diagonal && (
              <p className="text-sm text-red-600">Enable at least one direction.</p>
            )}
          </div>

          <div className="space-y-4">
            <div className="text-sm font-medium text-slate-700">Grid Size Mode</div>
            <div className="space-y-2">
              {MODES.map(([id, label, text]) => (
                <label key={id} className={`block cursor-pointer rounded-lg border p-2.5 ${
                  c.sizing_mode === id ? 'border-indigo-500 bg-indigo-50/50' : 'border-slate-200'
                }`}>
                  <input type="radio" name="mode" className="mr-2" checked={c.sizing_mode === id}
                    onChange={() => setC({ sizing_mode: id })} />
                  <span className="text-sm font-semibold">{label}</span>
                  <span className="mt-0.5 block pl-5 text-xs text-slate-500">{text}</span>
                </label>
              ))}
            </div>
            {c.sizing_mode !== 'auto' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Rows"><NumberInput min={1} max={100} value={c.rows} onChange={(v) => setC({ rows: v || 1 })} /></Field>
                <Field label="Columns"><NumberInput min={1} max={100} value={c.cols} onChange={(v) => setC({ cols: v || 1 })} /></Field>
              </div>
            )}
            {c.sizing_mode !== 'manual' && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Max rows"><NumberInput min={1} max={100} value={c.max_rows} onChange={(v) => setC({ max_rows: v || 1 })} /></Field>
                <Field label="Max columns"><NumberInput min={1} max={100} value={c.max_cols} onChange={(v) => setC({ max_cols: v || 1 })} /></Field>
              </div>
            )}

            <details className="rounded-lg border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-sm">
              <summary className="cursor-pointer font-medium text-slate-700">
                Word Normalisation &amp; Seed Options
              </summary>
              <div className="mt-3 space-y-3">
                <div className="grid grid-cols-3 gap-2">
                  <Field label="Book seed">
                    <NumberInput value={s.baseSeed} onChange={(v) => patch({ baseSeed: v === '' ? 0 : v })} />
                  </Field>
                  <Field label="Attempts/size">
                    <NumberInput min={1} max={1000} value={c.attempts_per_size} onChange={(v) => setC({ attempts_per_size: v || 1 })} />
                  </Field>
                  <Field label="Density">
                    <NumberInput step={0.1} min={1} max={10} value={c.density_factor} onChange={(v) => setC({ density_factor: v || 1 })} />
                  </Field>
                </div>
                <div className="space-y-2 pt-1">
                  {[
                    ['remove_spaces', 'Remove spaces', '“ICE CREAM” → ICECREAM'],
                    ['remove_hyphens', 'Remove hyphens', '“WELL-KNOWN” → WELLKNOWN'],
                    ['remove_apostrophes', 'Remove apostrophes', '“DON’T” → DONT'],
                    ['strip_accents', 'Strip accents', '“CAFÉ” → CAFE'],
                    ['allow_digits', 'Allow digits', 'Numbers can appear in words'],
                  ].map(([k, l, h]) => (
                    <Toggle key={k} label={l} hint={h} checked={c.normalize[k]}
                      onChange={(v) => setC({ normalize: { ...c.normalize, [k]: v } })} />
                  ))}
                </div>
              </div>
            </details>
          </div>
        </div>
      </Section>

      {/* ==================== C. PUZZLE SETTINGS ==================== */}
      <Section
        testId="section-puzzle-settings"
        title="Puzzle Settings"
        subtitle="Grid placement, letters typography, cell outlines, fills and outer border."
        badge={<Badge tone="slate">{`${L.grid_font} · ${Math.round(L.letter_size_ratio * 100)}%`}</Badge>}
        defaultOpen
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Puzzles Per Page" hint="Number of puzzle grids placed on each puzzle page.">
            <Select aria-label="Puzzles Per Page" value={L.puzzles_per_page}
              onChange={(e) => setL({ puzzles_per_page: Number(e.target.value) })}
              options={[[1, '1 puzzle per page'], [2, '2 puzzles per page'], [4, '4 puzzles per page']]} />
          </Field>

          <Field label="Puzzle Alignment on Page" hint="Horizontal position of the grid inside the printable area.">
            <Select aria-label="Puzzle Alignment on Page" value={L.puzzle_align}
              onChange={(e) => setL({ puzzle_align: e.target.value })}
              options={ALIGNMENTS} />
          </Field>

          <Field label="Vertical Alignment" hint="Vertical placement of the puzzle + clues block on the page.">
            <Select aria-label="Vertical Alignment" value={L.puzzle_valign}
              onChange={(e) => setL({ puzzle_valign: e.target.value })}
              options={VALIGNMENTS} />
          </Field>

          <Field label="Letters Font" hint="Font family for grid letters (Open Sans is bundled for PDF).">
            <Select aria-label="Letters Font" value={L.grid_font}
              onChange={(e) => setL({ grid_font: e.target.value })}
              options={FONT_CHOICES} />
          </Field>

          <Field label="Letters Font Style">
            <Select aria-label="Letters Font Style"
              value={encodeFontStyle(L.grid_font_weight, L.grid_font_style)}
              onChange={(e) => {
                const { weight, style } = decodeFontStyle(e.target.value)
                setL({ grid_font_weight: weight, grid_font_style: style })
              }}
              options={FONT_STYLES} />
          </Field>

          <Field label="Letters Text Size (% of cell)" hint="Default is 50% of the grid cell height.">
            <div className="flex items-center gap-2">
              <NumberInput aria-label="Letters Text Size" min={20} max={90} step={5}
                value={Math.round(L.letter_size_ratio * 100)}
                onChange={(v) => v !== '' && setL({ letter_size_ratio: Math.min(0.95, Math.max(0.15, v / 100)) })} />
              <Button variant="secondary" className="shrink-0 text-xs"
                onClick={() => setL({ letter_size_ratio: 0.5 })}>
                Default (50%)
              </Button>
            </div>
          </Field>

          <ColorInput
            label="Letters Color"
            ariaLabel="Letters Color"
            value={L.letter_color}
            onChange={(v) => setL({ letter_color: v || '#000000' })}
          />

          <div className="flex items-center pt-5">
            <Toggle
              label="Capital Letters"
              hint="Render all grid letters in uppercase (A–Z)."
              checked={L.uppercase_letters}
              onChange={(v) => setL({ uppercase_letters: v })}
            />
          </div>

          <div className="grid grid-cols-[1fr_5.5rem] gap-2">
            <Field label="Line Width" hint="Default: 4 px (0.25 mm). Set 0 to hide inner grid lines.">
              <NumberInput aria-label="Line Width" min={0} max={lineUnit === 'px' ? 40 : 3}
                step={lineUnit === 'px' ? 0.5 : 0.05}
                value={lineWidthDisplay}
                onChange={(v) => {
                  if (v === '') return
                  setL({ grid_line_width: lineUnit === 'px' ? pxToMm(v) : Number(v) })
                }} />
            </Field>
            <Field label="Line Unit">
              <Select aria-label="Line Width Unit" value={lineUnit}
                onChange={(e) => setLineUnit(e.target.value)}
                options={[['px', 'Px'], ['mm', 'mm']]} />
            </Field>
          </div>

          <ColorInput
            label="Cell Outline Color"
            ariaLabel="Cell Outline Color"
            value={L.grid_line_color}
            onChange={(v) => setL({ grid_line_color: v || '#222222' })}
          />

          <ColorInput
            label="Cell Color"
            ariaLabel="Cell Color"
            value={L.cell_color}
            allowNone
            noneLabel="Transparent"
            fallback="#ffffff"
            onChange={(v) => setL({ cell_color: v })}
          />

          <div className="grid grid-cols-2 gap-2">
            <Field label={`Border Width (${lineUnit.toUpperCase()})`} hint="Outer frame around grid.">
              <NumberInput aria-label="Border Width" min={0} max={lineUnit === 'px' ? 40 : 3}
                step={lineUnit === 'px' ? 1 : 0.1}
                value={borderWidthDisplay}
                onChange={(v) => {
                  if (v === '') return
                  setL({ border_width: lineUnit === 'px' ? pxToMm(v) : Number(v) })
                }} />
            </Field>
            <ColorInput
              label="Border Color"
              ariaLabel="Border Color"
              value={L.border_color}
              onChange={(v) => setL({ border_color: v || '#000000' })}
            />
          </div>
        </div>
      </Section>

      {/* ==================== D. CLUES SETTINGS ==================== */}
      <Section
        testId="section-clues-settings"
        title="Clues Settings"
        subtitle="Layout, sorting order, alignment and typography for the word clue list."
        badge={<Badge tone="slate">{`${L.clue_type} · ${L.clue_sort.replace('_', '→')}`}</Badge>}
        defaultOpen
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Type" hint="How word clues are arranged below the grid.">
            <Select aria-label="Clues Type" value={L.clue_type}
              onChange={(e) => setL({ clue_type: e.target.value })}
              options={CLUE_TYPES} />
          </Field>

          {L.clue_type !== 'inline' && (
            <Field label="Columns Count" hint="Number of columns (1–4).">
              <Select aria-label="Clue Columns" value={L.clue_columns}
                onChange={(e) => setL({ clue_columns: Number(e.target.value) })}
                options={[[1, '1 column'], [2, '2 columns'], [3, '3 columns'], [4, '4 columns']]} />
            </Field>
          )}

          <Field label="Words Sort" hint="Default: Short to Long.">
            <Select aria-label="Words Sort" value={L.clue_sort}
              onChange={(e) => setL({ clue_sort: e.target.value })}
              options={CLUE_SORTS} />
          </Field>

          <Field label="Text Alignment" hint="Alignment of words inside each column or line.">
            <Select aria-label="Clues Text Alignment" value={L.clue_align}
              onChange={(e) => setL({ clue_align: e.target.value })}
              options={ALIGNMENTS} />
          </Field>

          <Field label="Font Family">
            <Select aria-label="Clues Font Family" value={L.clue_font}
              onChange={(e) => setL({ clue_font: e.target.value })}
              options={FONT_CHOICES} />
          </Field>

          <Field label="Font Style">
            <Select aria-label="Clues Font Style"
              value={encodeFontStyle(L.clue_weight, L.clue_style)}
              onChange={(e) => {
                const { weight, style } = decodeFontStyle(e.target.value)
                setL({ clue_weight: weight, clue_style: style })
              }}
              options={FONT_STYLES} />
          </Field>

          <Field label="Text Size" hint="Default is 3% of minimum page side, or set a custom size in mm.">
            <div className="flex items-center gap-2">
              <Select aria-label="Clues Text Size Mode"
                value={L.clue_size_ratio != null ? 'auto' : 'custom'}
                onChange={(e) => {
                  if (e.target.value === 'auto') setL({ clue_size_ratio: 0.03 })
                  else setL({ clue_size_ratio: null })
                }}
                options={[
                  ['auto', 'Default (3% of min page side)'],
                  ['custom', 'Custom size (mm)'],
                ]} />
              {L.clue_size_ratio == null && (
                <div className="w-24 shrink-0">
                  <NumberInput aria-label="Clues Custom Font Size" min={2} max={16} step={0.2}
                    value={L.clue_font_size}
                    onChange={(v) => v !== '' && setL({ clue_font_size: v })} />
                </div>
              )}
            </div>
          </Field>

          <ColorInput
            label="Text Color"
            ariaLabel="Clues Text Color"
            value={L.clue_color ?? L.letter_color}
            onChange={(v) => setL({ clue_color: v || '#000000' })}
          />

          <div className="flex items-center pt-5">
            <Toggle
              label="Capitalize"
              hint="Display all clue words in capital letters."
              checked={L.clue_uppercase}
              onChange={(v) => setL({ clue_uppercase: v })}
            />
          </div>

          <Field label="Gap Above Clues (mm)" hint="Space between the puzzle grid and the clue list.">
            <NumberInput aria-label="Clue Gap" min={0} max={40} step={0.5} value={L.clue_gap}
              onChange={(v) => v !== '' && setL({ clue_gap: v })} />
          </Field>
        </div>
      </Section>

      {/* ==================== E. SOLUTION SETTINGS ==================== */}
      <Section
        testId="section-solution-settings"
        title="Solution"
        subtitle="Answer-key page layout, highlight style and independent solution appearance."
        badge={<Badge tone="indigo">{`${A.perPage} per page · ${A.style.replace('_', ' ')}`}</Badge>}
        open={solutionOpen}
        onToggle={setSolutionOpen}
        action={
          <Button type="button" variant="secondary" icon={Copy} onClick={handleCopyAppearance}>
            Copy Appearance from Puzzle
          </Button>
        }
      >
        {copiedNotice && (
          <div className="mb-4">
            <Notice tone="info" title="Copied appearance from puzzle">
              Solution font, size, colors, line width, border and alignment now match your puzzle settings.
            </Notice>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Solutions Per Page" hint="Number of solved grids packed onto each answer-key page.">
            <Select aria-label="Solutions Per Page" value={A.perPage}
              onChange={(e) => setA({ perPage: Number(e.target.value) })}
              options={[1, 2, 4, 6].map((n) => [n, `${n} per page`])} />
          </Field>

          <Field label="Highlight Style" hint="Vector shape drawn around each found word.">
            <Select aria-label="Solution Highlight Style" value={A.style}
              onChange={(e) => setA({ style: e.target.value })}
              options={HIGHLIGHTS} />
          </Field>

          <ColorInput
            label="Highlight Color"
            ariaLabel="Highlight Color"
            value={L.highlight_color}
            onChange={(v) => setL({ highlight_color: v || '#d62839' })}
          />

          <Field label="Solution Alignment">
            <Select aria-label="Solution Alignment" value={L.solution_align}
              onChange={(e) => setL({ solution_align: e.target.value })}
              options={ALIGNMENTS} />
          </Field>

          <Field label="Solution Layout Order" hint="How multi-solution tiles fill each answer-key page.">
            <Select aria-label="Solution Layout" value={L.solution_flow}
              onChange={(e) => setL({ solution_flow: e.target.value })}
              options={[['row', 'Row by row (left to right)'], ['column', 'Column by column (top to bottom)']]} />
          </Field>

          <Field label="Solution Font">
            <Select aria-label="Solution Font" value={L.solution_font ?? L.grid_font}
              onChange={(e) => setL({ solution_font: e.target.value })}
              options={FONT_CHOICES} />
          </Field>

          <Field label="Solution Font Style">
            <Select aria-label="Solution Font Style"
              value={encodeFontStyle(L.solution_font_weight ?? L.grid_font_weight, L.solution_font_style ?? L.grid_font_style)}
              onChange={(e) => {
                const { weight, style } = decodeFontStyle(e.target.value)
                setL({ solution_font_weight: weight, solution_font_style: style })
              }}
              options={FONT_STYLES} />
          </Field>

          <Field label="Solution Font Size (% of cell)">
            <NumberInput aria-label="Solution Font Size" min={20} max={90} step={5}
              value={Math.round((L.solution_letter_size_ratio ?? L.letter_size_ratio) * 100)}
              onChange={(v) => v !== '' && setL({ solution_letter_size_ratio: Math.min(0.95, Math.max(0.15, v / 100)) })} />
          </Field>

          <ColorInput
            label="Solution Font Color"
            ariaLabel="Solution Font Color"
            value={L.solution_letter_color ?? L.letter_color}
            onChange={(v) => setL({ solution_letter_color: v || '#000000' })}
          />

          <Field label={`Solution Line Width (${lineUnit.toUpperCase()})`}>
            <NumberInput aria-label="Solution Line Width" min={0} max={lineUnit === 'px' ? 40 : 3}
              step={lineUnit === 'px' ? 0.5 : 0.05}
              value={solLineWidthDisplay}
              onChange={(v) => {
                if (v === '') return
                setL({ solution_line_width: lineUnit === 'px' ? pxToMm(v) : Number(v) })
              }} />
          </Field>

          <ColorInput
            label="Solution Outline Color"
            ariaLabel="Solution Outline Color"
            value={L.solution_line_color ?? L.grid_line_color}
            onChange={(v) => setL({ solution_line_color: v || '#222222' })}
          />

          <ColorInput
            label="Solution Cell Color"
            ariaLabel="Solution Cell Color"
            value={L.solution_cell_color ?? L.cell_color}
            allowNone
            noneLabel="Transparent"
            fallback="#ffffff"
            onChange={(v) => setL({ solution_cell_color: v })}
          />

          <div className="sm:col-span-2 lg:col-span-3 border-t border-slate-100 pt-3">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div className="flex items-center pt-4">
                <Toggle
                  label="Show Solution Labels"
                  hint="Display a title above each answer key tile."
                  checked={L.solution_title_enabled}
                  onChange={(v) => setL({ solution_title_enabled: v })}
                />
              </div>
              {L.solution_title_enabled && (
                <div className="sm:col-span-2">
                  <Field label="Solution Label Template" hint="Supports TITLE, PUZZLE_NUMBER and CHAPTER_TITLE.">
                    <TextInput aria-label="Solution Title Template" value={L.solution_title_text}
                      onChange={(e) => setL({ solution_title_text: e.target.value })} />
                  </Field>
                </div>
              )}
            </div>
          </div>
        </div>
      </Section>

      {/* ==================== E. TITLE SETTINGS ==================== */}
      <Section
        testId="section-title-settings"
        title="Title"
        subtitle="Enable or disable puzzle titles and configure PUZZLE_NUMBER placeholders."
        badge={<Badge tone={L.title_enabled ? 'green' : 'slate'}>{L.title_enabled ? 'Enabled' : 'Disabled'}</Badge>}
        open={titleOpen}
        onToggle={setTitleOpen}
      >
        <div className="space-y-4">
          <Toggle
            label="Enable Title"
            hint="When enabled, the first line of each imported chapter is its title (not a word). When disabled, every line is a word and no title is printed."
            checked={L.title_enabled}
            onChange={(v) => dispatch({ type: 'setTitleEnabled', enabled: v })}
          />

          {L.title_enabled && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Title Type" hint="Use a custom template or the imported chapter name.">
                <Select aria-label="Title Type" value={L.title_mode}
                  onChange={(e) => setL({ title_mode: e.target.value })}
                  options={[
                    ['custom', 'Custom Template (with PUZZLE_NUMBER)'],
                    ['chapter', 'Imported Chapter Title'],
                  ]} />
              </Field>

              {L.title_mode === 'custom' && (
                <div className="sm:col-span-2">
                  <Field
                    label="Custom Title Text"
                    hint={`Preview for first puzzle: “${(L.title_text || '').replace(/PUZZLE_NUMBER/g, String(L.title_start_number)).replace(/CHAPTER_TITLE|TITLE/g, 'Chapter 1')}”`}
                  >
                    <div className="flex gap-2">
                      <TextInput aria-label="Custom Title Text" value={L.title_text}
                        placeholder="Puzzle #PUZZLE_NUMBER"
                        onChange={(e) => setL({ title_text: e.target.value })} />
                      <Button type="button" variant="secondary" className="shrink-0 text-xs"
                        onClick={() => insertPlaceholder('PUZZLE_NUMBER')}>
                        + PUZZLE_NUMBER
                      </Button>
                      <Button type="button" variant="secondary" className="shrink-0 text-xs"
                        onClick={() => insertPlaceholder('CHAPTER_TITLE')}>
                        + CHAPTER_TITLE
                      </Button>
                    </div>
                  </Field>
                </div>
              )}

              <Field label="Start Number" hint="First puzzle number used for PUZZLE_NUMBER.">
                <NumberInput aria-label="Start Number" min={0} max={10000} value={L.title_start_number}
                  onChange={(v) => setL({ title_start_number: v === '' ? 1 : Math.max(0, v) })} />
              </Field>

              <Field label="Title Font Family">
                <Select aria-label="Title Font Family" value={L.title_font}
                  onChange={(e) => setL({ title_font: e.target.value })}
                  options={FONT_CHOICES} />
              </Field>

              <Field label="Title Font Style">
                <Select aria-label="Title Font Style"
                  value={encodeFontStyle(L.title_weight, L.title_style)}
                  onChange={(e) => {
                    const { weight, style } = decodeFontStyle(e.target.value)
                    setL({ title_weight: weight, title_style: style })
                  }}
                  options={FONT_STYLES} />
              </Field>

              <Field label="Title Font Size (mm)">
                <NumberInput aria-label="Title Font Size" min={3} max={25} step={0.5} value={L.title_size}
                  onChange={(v) => v !== '' && setL({ title_size: v })} />
              </Field>

              <ColorInput
                label="Title Text Color"
                ariaLabel="Title Text Color"
                value={L.title_color ?? L.letter_color}
                onChange={(v) => setL({ title_color: v || '#000000' })}
              />

              <Field label="Title Alignment">
                <Select aria-label="Title Alignment" value={L.title_align}
                  onChange={(e) => setL({ title_align: e.target.value })}
                  options={ALIGNMENTS} />
              </Field>

              <Field label="Gap Below Title (mm)" hint="Space between the title and the puzzle grid.">
                <NumberInput aria-label="Title Gap" min={0} max={40} step={0.5} value={L.title_gap}
                  onChange={(v) => v !== '' && setL({ title_gap: v })} />
              </Field>
            </div>
          )}
        </div>
      </Section>

      {/* ==================== F. IMPORT WORD LIST ==================== */}
      <Section
        testId="section-import-words"
        title="Import Word List"
        subtitle="Drag & drop or browse an .xlsx, .txt or .csv file. One line = one word; blank line = chapter ends here."
        badge={<Badge tone={s.chapters.length ? (blockingErrors ? 'red' : 'green') : 'slate'}>
          {s.chapters.length ? `${s.chapters.length} chapters` : 'No file yet'}
        </Badge>}
        defaultOpen
      >
        <ImportWords />
      </Section>

      {/* ==================== NAVIGATION ==================== */}
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <Button
            type="button"
            variant="secondary"
            icon={ArrowLeft}
            onClick={() => {
              dispatch({ type: 'setup', patch: { step: 2 } })
              goStep(2)
            }}
          >
            Back
          </Button>

          <div className="flex flex-wrap items-center gap-3">
            {!s.chapters.length && (
              <span className="text-xs text-slate-500">Import a word list (or load sample chapters) to continue.</span>
            )}
            {s.chapters.length > 0 && blockingErrors > 0 && (
              <span className="text-xs font-medium text-red-600">
                Fix the chapter word counts above to continue.
              </span>
            )}
            <Button
              type="button"
              icon={ArrowRight}
              disabled={!canContinue}
              onClick={() => goStep(4)}
            >
              Continue
            </Button>
          </div>
        </div>
      </Card>
        </div>

        {/* ==================== RESIZE HANDLE & G. LIVE PREVIEW (RHS) ==================== */}
        {showPreview && (
          <>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize preview sidebar"
              title="Drag to resize panels (double-click to reset)"
              onPointerDown={(e) => {
                e.preventDefault()
                setDragging(true)
              }}
              onDoubleClick={() => setSplitPct(56)}
              className="group sticky top-6 hidden h-[calc(100vh-3rem)] cursor-col-resize select-none items-center justify-center lg:flex"
            >
              <div
                className={`h-full rounded-full transition-colors ${
                  dragging ? 'w-1 bg-blue-600' : 'w-0.5 bg-slate-200 group-hover:w-1 group-hover:bg-blue-500'
                }`}
              />
            </div>

            <div className="min-w-0 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto lg:pl-1">
              <Section
                testId="section-live-preview"
                title="Live Preview"
                subtitle="Real puzzle page and solution page preview with previous/next chapter and zoom."
                badge={<Badge tone="indigo">Vector SVG</Badge>}
                defaultOpen
              >
                <Preview />
              </Section>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
