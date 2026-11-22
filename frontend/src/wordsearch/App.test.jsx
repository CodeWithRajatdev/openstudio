import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { AppProvider } from './store.jsx'

const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><text>X</text></svg>'

function mockFetch(handlers = {}) {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const normalized = String(url).replace('/api/wordsearch/', '/api/')
    const h = Object.entries(handlers).find(([k]) => normalized.startsWith(k))
    const body = h ? h[1](opts) : {}
    const status = body.__status ?? 200
    return { ok: status < 400, status, json: async () => body }
  })
}

const renderApp = () => render(<AppProvider><App /></AppProvider>)
const click = (name) => userEvent.click(screen.getByRole('button', { name }))

async function goToStep3() {
  renderApp()
  await click('Continue')
  await click('Continue')
}

function mockUpload(handler) {
  const calls = []
  class FakeXHR {
    upload = {}
    open(method, url) { this.url = url }
    send(form) {
      calls.push(form)
      queueMicrotask(() => {
        const body = handler(form)
        this.status = body.__status ?? 200
        this.responseText = JSON.stringify(body)
        this.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 })
        this.onload()
      })
    }
  }
  global.XMLHttpRequest = FakeXHR
  return calls
}

const word = (id, text) => ({ id, raw: text, text, source: `row ${id}` })
const chap = (title, n, start = 1) => ({
  title,
  words: Array.from({ length: n }, (_, i) => word(start + i, 'ab' + 'cdefghijklmnopqrstuvwxyz'[i % 24])),
})
const wcIssue = (index, title, expected, actual) => ({
  severity: 'error',
  code: 'wrong_word_count',
  chapter: title,
  chapter_index: index,
  expected,
  actual,
  message: `${title} has ${actual} words. Expected ${expected}. ${expected > actual ? `Missing ${expected - actual}.` : `Extra ${actual - expected}.`}`,
})
const importBody = (over = {}) => ({
  filename: 'book.xlsx',
  sha256: 'abcdef1234567890',
  size_bytes: 1000,
  sheets: [],
  summary: { layout: 'lines' },
  chapters: [chap('Chapter 1', 20), chap('Chapter 2', 18, 100), chap('Chapter 3', 20, 200)],
  issues: [wcIssue(1, 'Chapter 2', 20, 18)],
  ...over,
})
const upload = (name = 'book.xlsx', opts = {}) =>
  userEvent.setup({ applyAccept: false }).upload(screen.getByTestId('file-input'), new File(['x'], name, opts))

beforeEach(() => mockFetch({
  '/api/bank/validate': () => ({ issues: [], ready: true, summary: {} }),
  '/api/preview': () => ({ puzzle_svg: svg, answer_svg: svg, rows: 10, cols: 10, seed: 1, key: [] }),
  '/api/jobs': () => ({
    id: 'job1',
    status: 'done',
    done: 2,
    total: 2,
    succeeded: 2,
    failed: 0,
    chapters: [
      { index: 0, title: 'Chapter 1', ok: true, rows: 10, cols: 10, seed: 1, failed_words: [], suggestions: [] },
      { index: 1, title: 'Chapter 2', ok: true, rows: 10, cols: 10, seed: 2, failed_words: [], suggestions: [] },
    ],
    export: { state: 'done', message: '', size: 120000, name: 'untitled-project.pdf' },
  }),
}))
afterEach(() => vi.restoreAllMocks())

describe('Linear studio flow (no sidebar, no dashboard, no separate bulk generator screen)', () => {
  it('starts on Step 1 of 4 with no sidebar or dashboard', () => {
    renderApp()
    expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 1 of 4')
    expect(screen.getByText('What are you creating?')).toBeInTheDocument()
    expect(screen.getByText('Word Search')).toBeInTheDocument()
    expect(screen.queryByLabelText('Main')).not.toBeInTheDocument()
    expect(screen.queryByText(/validate chapters/i)).not.toBeInTheDocument()
  })

  it('Step 2 of 4: standard sizes, custom size validation and unit conversion', async () => {
    renderApp()
    await click('Continue')
    expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 2 of 4')
    expect(screen.getByTestId('selected-size')).toHaveTextContent('8.5 × 11 in')
    await userEvent.click(screen.getByRole('button', { name: /6 × 9 in/ }))
    expect(screen.getByTestId('selected-size')).toHaveTextContent('6 × 9 in (152.4 × 228.6 mm)')
    const w = screen.getByLabelText('Custom width')
    await userEvent.clear(w); await userEvent.type(w, '1')
    expect(screen.getByText(/at least/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    await userEvent.clear(w); await userEvent.type(w, '8')
    await userEvent.selectOptions(screen.getByLabelText('Unit'), 'mm')
    expect(screen.getByLabelText('Custom width')).toHaveValue(203.2)
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
  })

  it('Step 3 of 4: one-page Puzzle Setup with sections A-G and Solutions Per Page only in Solution', async () => {
    await goToStep3()
    expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 3 of 4')
    expect(screen.getByRole('heading', { name: 'Puzzle Setup' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('Solutions Per Page')).toHaveLength(1)

    // A. Page Settings: KDP guidelines & custom margins
    expect(screen.getByLabelText('Guideline Mode')).toHaveValue('edges')
    await userEvent.selectOptions(screen.getByLabelText('Guideline Mode'), 'kdp')
    expect(screen.getByText(/KDP Gutter Active/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Guideline Mode'), 'edges')
    await userEvent.click(screen.getByLabelText(/Set Additional Margins/))
    const topMargin = screen.getByLabelText('Top Margin')
    await userEvent.clear(topMargin); await userEvent.type(topMargin, '8')
    expect(topMargin).toHaveValue(8)

    // B. Word Settings
    await userEvent.selectOptions(screen.getByLabelText('Words Per Puzzle'), '15')
    expect(screen.getByText('15 words / puzzle')).toBeInTheDocument()

    // C. Puzzle Settings & Clues
    await userEvent.selectOptions(screen.getByLabelText('Puzzle Alignment on Page'), 'left')
    await userEvent.selectOptions(screen.getByLabelText('Letters Font'), 'Georgia')
    expect(screen.getByLabelText('Line Width')).toHaveValue(4)

    // D. Solution: Copy Appearance from Puzzle
    await userEvent.click(screen.getByRole('button', { name: /Copy Appearance from Puzzle/ }))
    expect(screen.getByText(/Copied appearance from puzzle/)).toBeInTheDocument()
    expect(screen.getByLabelText('Solution Font')).toHaveValue('Georgia')
    expect(screen.getByLabelText('Solution Alignment')).toHaveValue('left')

    // E. Title
    expect(screen.getByLabelText('Custom Title Text')).toHaveValue('Puzzle #PUZZLE_NUMBER')
  })

  it('Step 3 import preview -> accept -> blocks Continue when a chapter has wrong word count', async () => {
    mockUpload(() => importBody())
    mockFetch({
      '/api/bank/validate': () => ({ ready: false, summary: {}, issues: [wcIssue(1, 'Chapter 2', 20, 18)] }),
      '/api/preview': () => ({ puzzle_svg: svg, answer_svg: svg, rows: 10, cols: 10, seed: 1, key: [] }),
    })
    await goToStep3()
    await upload()
    expect(await screen.findByText(/Import summary — book.xlsx/)).toBeInTheDocument()
    const row = screen.getByTestId('chapter-row-1')
    expect(row).toHaveTextContent('Chapter 2 has 18 words. Expected 20. Missing 2.')
    await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
    expect(await screen.findByText(/Generate is blocked/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
  })

  it('Title rule: 3-chapter file with Title ON (first line = title) vs Title OFF (every line = word)', async () => {
    const threeChWithTitle = [
      {
        title: 'Fruits',
        title_entry: word(1, 'Fruits'),
        words: [word(2, 'APPLE'), word(3, 'MANGO')],
      },
      {
        title: 'Animals',
        title_entry: word(4, 'Animals'),
        words: [word(5, 'TIGER'), word(6, 'LION')],
      },
      {
        title: 'Space',
        title_entry: word(7, 'Space'),
        words: [word(8, 'PLANET'), word(9, 'GALAXY')],
      },
    ]
    const calls = mockUpload(() => importBody({
      filename: 'three_chapters.txt',
      chapters: threeChWithTitle,
      issues: [],
    }))
    await goToStep3()
    await userEvent.selectOptions(screen.getByLabelText('Words Per Puzzle'), 'none')

    // Title ON by default -> sends first_line_title=true; first line of each of the 3 chapters is the title (2 words each)
    await upload('three_chapters.txt')
    expect(calls[0].get('first_line_title')).toBe('true')
    await userEvent.click(await screen.findByRole('button', { name: 'Accept' }))
    expect(screen.getByTestId('chapter-row-0')).toHaveTextContent('Fruits')
    expect(screen.getByTestId('chapter-row-0')).toHaveTextContent('2')
    expect(screen.getByTestId('chapter-row-1')).toHaveTextContent('Animals')
    expect(screen.getByTestId('chapter-row-1')).toHaveTextContent('2')
    expect(screen.getByTestId('chapter-row-2')).toHaveTextContent('Space')
    expect(screen.getByTestId('chapter-row-2')).toHaveTextContent('2')

    // Toggle Title OFF -> every line becomes a word (3 words per chapter, titles reset to Chapter 1..3)
    await userEvent.click(screen.getByLabelText(/Enable Title/))
    expect(screen.getByTestId('chapter-row-0')).toHaveTextContent('Chapter 1')
    expect(screen.getByTestId('chapter-row-0')).toHaveTextContent('3')
    expect(screen.getByTestId('chapter-row-1')).toHaveTextContent('Chapter 2')
    expect(screen.getByTestId('chapter-row-1')).toHaveTextContent('3')
    expect(screen.getByTestId('chapter-row-2')).toHaveTextContent('Chapter 3')
    expect(screen.getByTestId('chapter-row-2')).toHaveTextContent('3')
  })

  it('walks through Step 3 -> Step 4 (Review & Generate and Download on the same screen)', async () => {
    mockUpload(() => importBody({
      chapters: [chap('Chapter 1', 20), chap('Chapter 2', 20, 100), chap('Chapter 3', 20, 200)],
      issues: [],
    }))
    await goToStep3()
    await upload()
    await userEvent.click(await screen.findByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled())

    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 4 of 4')
    expect(screen.getByRole('heading', { name: 'Review the Whole Project' })).toBeInTheDocument()
    // 3 chapters: 3 puzzle pages + 1 solution page (4 per page) = 4 total pages
    expect(screen.getByText('4 Total Pages')).toBeInTheDocument()
    expect(await screen.findByText('First Puzzle Page')).toBeInTheDocument()
    expect(screen.getByText('First Solution Page')).toBeInTheDocument()

    // One click on "Generate and Download" shows the progress bar and PDF download on that same screen
    await userEvent.click(screen.getByRole('button', { name: 'Generate and Download' }))
    expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 4 of 4')
    expect(await screen.findByTestId('job-progress-text')).toHaveTextContent('2 / 2 chapters')
    const dl = await screen.findByTestId('download-pdf-link')
    expect(dl).toHaveAttribute('href', '/api/wordsearch/jobs/job1/download')
    expect(dl).toHaveTextContent('untitled-project.pdf')
    expect(screen.queryByText(/ZIP/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/puzzle SVG/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/solution SVG/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/bulk/i)).not.toBeInTheDocument()
  })

  it('blocks download on the same screen when any chapter fails and offers Retry failed chapters', async () => {
    mockUpload(() => importBody({
      chapters: [chap('Chapter 1', 20), chap('Chapter 2', 20, 100)],
      issues: [],
    }))
    mockFetch({
      '/api/bank/validate': () => ({ issues: [], ready: true, summary: {} }),
      '/api/preview': () => ({ puzzle_svg: svg, answer_svg: svg, rows: 10, cols: 10, seed: 1, key: [] }),
      '/api/jobs': () => ({
        id: 'job_fail',
        status: 'done',
        done: 2,
        total: 2,
        succeeded: 1,
        failed: 1,
        chapters: [
          { index: 0, title: 'Chapter 1', ok: true, rows: 10, cols: 10, seed: 1, failed_words: [], suggestions: [] },
          { index: 1, title: 'Chapter 2', ok: false, rows: null, cols: null, seed: null, error: 'Could not place word in grid.', failed_words: ['LONGWORD'], suggestions: ['Increase grid size.'] },
        ],
        export: { state: 'none', message: '', size: 0, name: 'book.pdf' },
      }),
    })
    await goToStep3()
    await upload()
    await userEvent.click(await screen.findByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate and Download' }))

    expect(await screen.findByText(/Chapter 2 \(Chapter 2\): Could not place word in grid\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry failed chapters/ })).toBeInTheDocument()
    expect(screen.queryByTestId('download-pdf-link')).not.toBeInTheDocument()
  })
})
