import React, { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react'
import { api, jobPayloadChapters } from './api'
import { DEFAULT_ANSWERS, DEFAULT_CONFIG, DEFAULT_LAYOUT, SAMPLE_CHAPTERS } from './defaults'

const initial = {
  step: 1,
  projectName: 'Untitled project',
  chapters: [], nextId: 1, importInfo: null, selectedChapter: 0,
  issues: [], ready: true, validating: false,
  validateOpts: { checkCross: false, maxLen: '' },
  wordsPerChapter: 20,          // every chapter must hold exactly this many words (null = no fixed count)
  config: DEFAULT_CONFIG, layout: DEFAULT_LAYOUT, baseSeed: 1,
  answers: DEFAULT_ANSWERS,
  chapterSeeds: {}, job: null, jobError: null,
  setup: {
    started: false, step: 1, projectType: 'word_search',
    sizeId: '8.5x11', custom: { w: 8.5, h: 11, unit: 'in' },
  },
}

const mk = (state, text, source = null) => ({ id: state.nextId, raw: text, text: text.trim(), source })

export function copyPuzzleToSolution(L) {
  return {
    ...L,
    solution_font: L.grid_font,
    solution_font_weight: L.grid_font_weight,
    solution_font_style: L.grid_font_style,
    solution_letter_size_ratio: L.letter_size_ratio,
    solution_letter_color: L.letter_color,
    solution_uppercase: L.uppercase_letters,
    solution_line_width: L.grid_line_width,
    solution_line_color: L.grid_line_color,
    solution_cell_color: L.cell_color,
    solution_border_width: L.border_width,
    solution_border_color: L.border_color,
    solution_align: L.puzzle_align,
    solution_title_font: L.title_font,
    solution_title_weight: L.title_weight,
    solution_title_style: L.title_style,
    solution_title_color: L.title_color,
  }
}

function toggleTitleOnChapters(chapters, titleEnabled, nextId) {
  let id = nextId
  const out = chapters.map((ch, idx) => {
    if (titleEnabled) {
      if (ch.title_entry) return ch
      if (ch.words.length > 0) {
        const [first, ...rest] = ch.words
        return { ...ch, title: first.text, title_entry: first, words: rest }
      }
      return ch
    } else {
      if (!ch.title_entry) return ch
      const restored = { ...ch.title_entry, text: ch.title || ch.title_entry.text, id: ch.title_entry.id || id++ }
      return { ...ch, title: `Chapter ${idx + 1}`, title_entry: null, words: [restored, ...ch.words] }
    }
  })
  return { chapters: out, nextId: id }
}

function reducer(s, a) {
  switch (a.type) {
    case 'patch': return { ...s, ...a.patch }
    case 'step': return { ...s, step: a.step, setup: { ...s.setup, step: a.step, started: a.step >= 3 } }
    case 'setup': {
      const nextSetup = { ...s.setup, ...a.patch }
      const nextStep = a.patch.step ?? (a.patch.started ? 3 : s.step)
      return { ...s, step: nextStep, setup: nextSetup }
    }
    case 'setTitleEnabled': {
      const enabled = !!a.enabled
      const layout = { ...s.layout, title_enabled: enabled }
      if (!s.chapters.length) return { ...s, layout }
      const { chapters, nextId } = toggleTitleOnChapters(s.chapters, enabled, s.nextId)
      return { ...s, layout, chapters, nextId, job: null }
    }
    case 'resetSettings':
      return {
        ...s,
        wordsPerChapter: 20,
        config: DEFAULT_CONFIG,
        layout: { ...DEFAULT_LAYOUT, page_width: s.layout.page_width, page_height: s.layout.page_height },
        answers: DEFAULT_ANSWERS,
      }
    case 'copyAppearanceToSolution':
      return { ...s, layout: copyPuzzleToSolution(s.layout) }
    case 'loadProject':
      return {
        ...initial,
        ...a.project,
        config: { ...DEFAULT_CONFIG, ...(a.project.config || {}) },
        layout: { ...DEFAULT_LAYOUT, ...(a.project.layout || {}) },
        answers: { ...DEFAULT_ANSWERS, ...(a.project.answers || {}) },
        setup: { ...initial.setup, ...(a.project.setup || {}), started: true },
        job: null, jobError: null,
      }
    case 'loadImport': {
      const top = Math.max(0, ...a.chapters.flatMap((c) => c.words.map((w) => w.id)))
      return {
        ...s, chapters: a.chapters, nextId: top + 1, importInfo: a.info, issues: a.issues,
        selectedChapter: 0, job: null, chapterSeeds: {}
      }
    }
    case 'sample': {
      let n = s.nextId
      const chapters = SAMPLE_CHAPTERS.map(([title, words]) => ({
        title, words: words.split(' ').map((w) => ({ id: n++, raw: w, text: w, source: 'sample' }))
      }))
      return {
        ...s, chapters, nextId: n, importInfo: { filename: 'Sample chapters (built-in)' },
        selectedChapter: 0, job: null, chapterSeeds: {}
      }
    }
    case 'newProject':
      return {
        ...initial, projectName: a.name || 'Untitled project',
        config: s.config, layout: s.layout, answers: s.answers,
        setup: { ...s.setup, started: false, step: 1 }
      }
    case 'setChapters': return { ...s, chapters: a.chapters }
    case 'editWord':
      return {
        ...s, chapters: s.chapters.map((c, i) => i !== a.ci ? c : {
          ...c,
          words: c.words.map((w) => w.id === a.id ? { ...w, text: a.text.trim() } : w)
        })
      }
    case 'deleteWord':
      return {
        ...s, chapters: s.chapters.map((c, i) => i !== a.ci ? c : {
          ...c,
          words: c.words.filter((w) => w.id !== a.id)
        })
      }
    case 'addWord':
      return {
        ...s, nextId: s.nextId + 1, chapters: s.chapters.map((c, i) => i !== a.ci ? c : {
          ...c,
          words: [...c.words, mk(s, a.text, 'added in app')]
        })
      }
    case 'addChapter':
      return {
        ...s, chapters: [...s.chapters, { title: a.title, words: [] }],
        selectedChapter: s.chapters.length
      }
    case 'removeChapter': {
      const chapters = s.chapters.filter((_, i) => i !== a.ci)
      return {
        ...s, chapters, selectedChapter: Math.min(s.selectedChapter, Math.max(0, chapters.length - 1)),
        job: null, chapterSeeds: {}
      }
    }
    case 'renameChapter':
      return {
        ...s, chapters: s.chapters.map((c, i) => i !== a.ci ? c : {
          ...c, title: a.title,
          title_entry: c.title_entry ? { ...c.title_entry, text: a.title } : null,
        })
      }
    case 'pinSeed': return { ...s, chapterSeeds: { ...s.chapterSeeds, [a.ci]: a.seed } }
    case 'unpinSeed': {
      const { [a.ci]: _, ...rest } = s.chapterSeeds
      return { ...s, chapterSeeds: rest }
    }
    default: return s
  }
}

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initial)
  const ref = useRef(state)
  ref.current = state

  const patch = useCallback((p) => dispatch({ type: 'patch', patch: p }), [])

  // Live validation of the word bank (debounced).
  useEffect(() => {
    if (!state.chapters.length) { patch({ issues: [], ready: true }); return }
    const ctl = new AbortController()
    const t = setTimeout(async () => {
      patch({ validating: true })
      try {
        const r = await api.post('/api/bank/validate', {
          chapters: state.chapters, rules: state.config.normalize,
          check_cross_chapter: state.validateOpts.checkCross,
          max_word_length: state.validateOpts.maxLen ? Number(state.validateOpts.maxLen) : null,
          expected_words: state.wordsPerChapter || null,
        }, ctl.signal)
        patch({ issues: r.issues, ready: r.ready, validating: false })
      } catch (e) { if (e.name !== 'AbortError') patch({ validating: false }) }
    }, 400)
    return () => { clearTimeout(t); ctl.abort() }
  }, [state.chapters, state.validateOpts, state.wordsPerChapter, state.config.normalize, patch])

  // Poll running jobs / exports.
  const jobId = state.job?.id
  const busy = state.job?.status === 'running' || state.job?.export?.state === 'running'
  useEffect(() => {
    if (!jobId || !busy) return
    const t = setInterval(async () => {
      try { patch({ job: await api.get(`/api/jobs/${jobId}`) }) } catch { /* retry next tick */ }
    }, 700)
    return () => clearInterval(t)
  }, [jobId, busy, patch])

  const actions = useMemo(() => ({
    patch,
    goStep: (step) => dispatch({ type: 'step', step }),
    dispatch,
    async startJob() {
      const s = ref.current
      patch({ jobError: null })
      try {
        const job = await api.post('/api/jobs', {
          chapters: jobPayloadChapters(s.chapters), config: s.config, layout: s.layout,
          base_seed: s.baseSeed, seed_overrides: s.chapterSeeds,
          expected_words: s.wordsPerChapter || null,
        })
        patch({ job })
        return job
      } catch (e) { patch({ jobError: e.message }); return null }
    },
    async retryFailed() {
      const j = ref.current.job
      try { patch({ job: await api.post(`/api/jobs/${j.id}/retry-failed`), jobError: null }) }
      catch (e) { patch({ jobError: e.message }) }
    },
    async startExport(opts) {
      const j = ref.current.job
      try { patch({ job: await api.post(`/api/jobs/${j.id}/export`, opts), jobError: null }) }
      catch (e) { patch({ jobError: e.message }) }
    },
  }), [patch])

  const value = useMemo(() => ({ state, ...actions }), [state, actions])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
