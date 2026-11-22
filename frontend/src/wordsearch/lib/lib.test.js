import { describe, expect, it } from 'vitest'
import { calcPages } from './pagePlan'
import { describeSize, fromMm, toMm, validateCustomSize } from './units'

describe('calcPages', () => {
  it('365 chapters, 1 puzzle/page, 6 solutions/page (the worked example)', () => {
    const p = calcPages({ chapters: 365, solutionsPerPage: 6 })
    expect(p.puzzlePages).toBe(365)
    expect(p.answerPages).toBe(61)          // ceil(365 / 6)
    expect(p.lastAnswerPageSolutions).toBe(5)
    expect(p.content).toBe(426)
    expect(p.blankPages).toBe(0)
    expect(p.total).toBe(426)
  })
  it('adds one blank page when the content count is odd', () => {
    const p = calcPages({ chapters: 100, solutionsPerPage: 6 })   // 100 + 17 = 117
    expect(p.content).toBe(117); expect(p.blankPages).toBe(1); expect(p.total).toBe(118)
  })
  it('respects puzzles per page and solutions per page', () => {
    expect(calcPages({ chapters: 10, solutionsPerPage: 1 }).answerPages).toBe(10)
    expect(calcPages({ chapters: 10, solutionsPerPage: 4 }).answerPages).toBe(3)
    expect(calcPages({ chapters: 10, puzzlesPerPage: 2, solutionsPerPage: 4 }).puzzlePages).toBe(5)
  })
  it('handles zero / junk input without NaN', () => {
    const p = calcPages({ chapters: 'abc' })
    expect(p.total).toBe(0); expect(Number.isNaN(p.total)).toBe(false)
  })
})

describe('units', () => {
  it('converts between inches, mm and cm', () => {
    expect(toMm(8.5, 'in')).toBe(215.9); expect(toMm(21, 'cm')).toBe(210); expect(toMm(210, 'mm')).toBe(210)
    expect(fromMm(215.9, 'in')).toBe(8.5)
    expect(describeSize(215.9, 279.4)).toBe('8.5 × 11 in  (215.9 × 279.4 mm)')
  })
  it('validates custom sizes', () => {
    expect(validateCustomSize({ w: 7, h: 10, unit: 'in' })).toMatchObject({ ok: true, wMm: 177.8, hMm: 254 })
    expect(validateCustomSize({ w: 0, h: 10, unit: 'in' }).ok).toBe(false)
    expect(validateCustomSize({ w: '', h: 10, unit: 'in' }).ok).toBe(false)
    expect(validateCustomSize({ w: 1, h: 10, unit: 'in' }).error).toMatch(/at least/)
    expect(validateCustomSize({ w: 30, h: 10, unit: 'in' }).error).toMatch(/at most/)
    expect(validateCustomSize({ w: 150, h: 200, unit: 'mm' }).ok).toBe(true)
  })
})
