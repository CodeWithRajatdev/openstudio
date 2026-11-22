/** Page-count calculation for a puzzle book. Pure functions, no UI. */

const ceilDiv = (a, b) => Math.ceil(a / b)

/**
 * Automatic page breakdown of the finished book:
 *  - one puzzle per chapter, `puzzlesPerPage` puzzles on each puzzle page
 *  - one solution per chapter, `solutionsPerPage` solutions on each answer-key page
 *  - a printed book always has an even number of pages (leaves have two sides),
 *    so one blank page is added when the content total is odd.
 */
export function calcPages({ chapters, puzzlesPerPage = 1, solutionsPerPage = 6 }) {
  const ch = Math.max(0, Math.floor(Number(chapters)) || 0)
  const ppp = Math.max(1, Math.floor(puzzlesPerPage) || 1)
  const spp = Math.max(1, Math.floor(solutionsPerPage) || 1)
  const puzzlePages = ceilDiv(ch, ppp)
  const answerPages = ceilDiv(ch, spp)
  const content = puzzlePages + answerPages
  const blankPages = content % 2
  return {
    chapters: ch, puzzlesPerPage: ppp, solutionsPerPage: spp,
    puzzlePages, answerPages,
    content, blankPages, total: content + blankPages,
    lastAnswerPageSolutions: ch === 0 ? 0 : ch - (answerPages - 1) * spp,
    lastPuzzlePagePuzzles: ch === 0 ? 0 : ch - (puzzlePages - 1) * ppp,
  }
}

/** Amazon KDP inside (gutter) minimum margin in mm for a book of `totalPages`. */
export function kdpGutterMm(totalPages) {
  const n = Math.max(1, Number(totalPages) || 1)
  if (n <= 150) return 9.53   // 0.375 in
  if (n <= 300) return 12.7   // 0.500 in
  if (n <= 500) return 15.88  // 0.625 in
  if (n <= 700) return 19.05  // 0.750 in
  return 22.23                // 0.875 in
}

export const KDP_OUTSIDE_MM = 6.35

export function effectiveMargins(layout, totalPages = 100, pageNumber = 1) {
  if (layout.margin_mode === 'kdp') {
    const inside = Math.max(layout.margin, kdpGutterMm(totalPages))
    const outside = Math.max(layout.margin, KDP_OUTSIDE_MM)
    const rightHand = pageNumber % 2 === 1
    return {
      top: outside,
      bottom: outside,
      left: rightHand ? inside : outside,
      right: rightHand ? outside : inside,
      inside,
      outside,
    }
  }
  return {
    top: layout.margin + (layout.extra_margins ? layout.margin_top : 0),
    right: layout.margin + (layout.extra_margins ? layout.margin_right : 0),
    bottom: layout.margin + (layout.extra_margins ? layout.margin_bottom : 0),
    left: layout.margin + (layout.extra_margins ? layout.margin_left : 0),
  }
}
