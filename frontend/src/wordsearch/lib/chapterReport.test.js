import { describe, expect, it } from 'vitest'
import { chapterReport, readNotes } from './chapterReport'

const ch = (n) => ({ title: `Chapter ${n}`, words: Array.from({ length: n }, (_, i) => ({ id: i, text: 'x' })) })
const wc = (index, expected, actual, message) => ({ severity: 'error', code: 'wrong_word_count', chapter_index: index, expected, actual, message })

describe('chapterReport', () => {
  it('marks short and long chapters invalid with exact wording, others valid', () => {
    const r = chapterReport(
      [ch(20), ch(18), ch(22)],
      [
        wc(1, 20, 18, 'Chapter 2 has 18 words. Expected 20. Missing 2.'),
        wc(2, 20, 22, 'Chapter 3 has 22 words. Expected 20. Extra 2.'),
      ],
      20
    )
    expect(r.rows.map((x) => x.valid)).toEqual([true, false, false])
    expect(r.rows[1].problems).toEqual(['Chapter 2 has 18 words. Expected 20. Missing 2.'])
    expect(r.rows[2].problems).toEqual(['Chapter 3 has 22 words. Expected 20. Extra 2.'])
    expect(r.totals).toEqual({ chapters: 3, words: 60, valid: 1, invalid: 2 })
  })
  it('singular wording, mixed problems and warnings do not make a chapter invalid', () => {
    const issues = [wc(0, 20, 19), { severity: 'error', code: 'invalid_word', chapter_index: 0 },
    { severity: 'warning', code: 'duplicate_across_chapters', chapter_index: 1 }]
    const r = chapterReport([ch(19), ch(5)], issues, 20)
    expect(r.rows[0].problems).toEqual(['Chapter 1 has 19 words. Expected 20. Missing 1.', '1 invalid word'])
    expect(r.rows[1].valid).toBe(true)
  })
  it('splits read-time notes from re-runnable checks', () => {
    const notes = readNotes([{ code: 'header_row_skipped' }, { code: 'wrong_word_count' }, { code: 'extra_columns_ignored' }])
    expect(notes.map((n) => n.code)).toEqual(['header_row_skipped', 'extra_columns_ignored'])
  })
})
