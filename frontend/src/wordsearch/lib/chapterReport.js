/** Per-chapter validity report built from the server's issues (no guessing, no auto-fixing). */

const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`

function describe(errs) {
  const by = {}
  for (const e of errs) (by[e.code] ||= []).push(e)
  const out = []
  const wc = by.wrong_word_count?.[0]
  if (wc) {
    if (wc.message) {
      out.push(wc.message)
    } else {
      const diff = wc.expected - wc.actual
      const chNum = (wc.chapter_index ?? 0) + 1
      out.push(`Chapter ${chNum} has ${plural(wc.actual, 'word')}. Expected ${wc.expected}. ${diff > 0 ? `Missing ${diff}.` : `Extra ${-diff}.`}`)
    }
  }
  if (by.invalid_word) out.push(plural(by.invalid_word.length, 'invalid word'))
  if (by.duplicate_in_chapter) out.push(plural(by.duplicate_in_chapter.length, 'duplicate'))
  if (by.word_too_long) out.push(`${plural(by.word_too_long.length, 'word')} too long`)
  if (by.blank_word) out.push(plural(by.blank_word.length, 'blank word'))
  return out
}

export function chapterReport(chapters, issues, expected = null) {
  const errors = {}
  for (const i of issues) {
    if (i.severity === 'error' && i.chapter_index != null) (errors[i.chapter_index] ||= []).push(i)
  }
  const rows = chapters.map((c, index) => {
    const errs = errors[index] || []
    return { index, title: c.title, count: c.words.length, expected, valid: errs.length === 0,
      problems: describe(errs), errors: errs }
  })
  const valid = rows.filter((r) => r.valid).length
  return { rows, totals: { chapters: rows.length, words: rows.reduce((n, r) => n + r.count, 0),
    valid, invalid: rows.length - valid } }
}

// Notices produced while reading the file (as opposed to checks that are re-run on every edit).
export const CHECK_CODES = new Set(['wrong_word_count', 'invalid_word', 'duplicate_in_chapter',
  'duplicate_across_chapters', 'word_too_long', 'blank_word', 'empty_chapter', 'duplicate_chapter_title'])
export const readNotes = (issues) => issues.filter((i) => !CHECK_CODES.has(i.code))
