import React from 'react'
import { FileUp } from 'lucide-react'
import { useApp } from '../store.jsx'
import { Button, Empty, Notice, Select } from './ui.jsx'

export function NoWords() {
  const { dispatch } = useApp()
  return (
    <Empty icon={FileUp} title="Import a word list above to see the live preview" text="Or load the three built-in sample chapters to try the preview immediately.">
      <Button variant="secondary" onClick={() => dispatch({ type: 'sample' })}>Load sample chapters</Button>
    </Empty>
  )
}

export function ChapterSelect({ label = 'Chapter' }) {
  const { state: s, patch } = useApp()
  const i = Math.max(0, Math.min(s.selectedChapter, s.chapters.length - 1))
  return (
    <div className="w-72">
      <Select aria-label={label} value={i} onChange={(e) => patch({ selectedChapter: Number(e.target.value) })}
        options={s.chapters.map((c, n) => [n, `${n + 1}. ${c.title}`])} />
    </div>
  )
}

export function PreviewError({ error }) {
  if (!error) return null
  return (
    <Notice tone="error" title="Cannot render this preview">
      {error.message}
      {error.failedWords?.length > 0 && <div className="mt-1">Unplaced: {error.failedWords.join(', ')}</div>}
      {error.suggestions?.length > 0 && <ul className="mt-1 list-disc pl-5">{error.suggestions.map((t) => <li key={t}>{t}</li>)}</ul>}
    </Notice>
  )
}

/** Words of the selected chapter as plain strings. */
export const useChapterWords = (s) => {
  const i = Math.max(0, Math.min(s.selectedChapter, s.chapters.length - 1))
  return { index: i, chapter: s.chapters[i], words: s.chapters[i]?.words.map((w) => w.text) ?? [] }
}

export const seedFor = (s, index) => s.chapterSeeds[index] ?? s.baseSeed + index

export const extraPuzzlesFor = (s, index) => {
  const per = s.layout.puzzles_per_page || 1
  if (per <= 1) return []
  const out = []
  for (let k = 1; k < per; k++) {
    const idx = index + k
    const ch = s.chapters[idx]
    if (!ch || !ch.words.length) break
    out.push({ title: ch.title, words: ch.words.map((w) => w.text), seed: seedFor(s, idx), index: idx })
  }
  return out
}

export const solutionItemsFor = (s, index) => {
  const per = s.answers.perPage || 1
  if (per <= 1) return []
  const start = Math.floor(index / per) * per
  const out = []
  for (let k = 0; k < per; k++) {
    const idx = start + k
    const ch = s.chapters[idx]
    if (!ch || !ch.words.length) break
    out.push({ title: ch.title, words: ch.words.map((w) => w.text), seed: seedFor(s, idx), index: idx })
  }
  return out
}
