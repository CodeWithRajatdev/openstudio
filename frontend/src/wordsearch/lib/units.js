export const UNITS = [['in', 'inches'], ['mm', 'millimetres'], ['cm', 'centimetres']]
const MM = { in: 25.4, mm: 1, cm: 10 }

// Generic sanity limits for a printed interior page (not a print-service rule).
export const MIN_MM = 76.2   // 3 in
export const MAX_MM = 431.8  // 17 in

export const toMm = (v, unit) => Math.round(Number(v) * MM[unit] * 100) / 100
export const fromMm = (mm, unit) => Math.round((mm / MM[unit]) * 1000) / 1000

export function fmt(mm, unit) {
  const v = fromMm(mm, unit)
  return `${Number.isInteger(v) ? v : +v.toFixed(2)}`
}

export const describeSize = (wMm, hMm) =>
  `${fmt(wMm, 'in')} × ${fmt(hMm, 'in')} in  (${fmt(wMm, 'mm')} × ${fmt(hMm, 'mm')} mm)`

export function validateCustomSize({ w, h, unit }) {
  if (!MM[unit]) return { ok: false, error: 'Choose a unit.' }
  if (!(Number(w) > 0) || !(Number(h) > 0)) return { ok: false, error: 'Enter a width and a height greater than zero.' }
  const wMm = toMm(w, unit), hMm = toMm(h, unit)
  const lim = (m) => `${fmt(m, unit)} ${unit}`
  if (wMm < MIN_MM || hMm < MIN_MM) return { ok: false, error: `Each side must be at least ${lim(MIN_MM)}.` }
  if (wMm > MAX_MM || hMm > MAX_MM) return { ok: false, error: `Each side must be at most ${lim(MAX_MM)}.` }
  return { ok: true, wMm, hMm }
}
