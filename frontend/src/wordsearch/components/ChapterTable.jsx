import React, { useState } from 'react'
import { Badge } from './ui.jsx'

export const Stat = ({ label, value, tone }) => (
  <div className={`rounded-xl border px-4 py-3 ${tone === 'red' ? 'border-red-200 bg-red-50' : tone === 'green' ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white'}`}>
    <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-0.5 text-2xl font-bold tabular-nums">{value}</div>
  </div>
)

/** Chapter overview: one row per chapter with count, expected count and status. */
export default function ChapterTable({ rows, selected, onSelect, pageSize = 200, maxHeight = 'max-h-80' }) {
  const [onlyInvalid, setOnlyInvalid] = useState(false)
  const [shown, setShown] = useState(pageSize)
  const list = onlyInvalid ? rows.filter((r) => !r.valid) : rows
  const invalid = rows.filter((r) => !r.valid).length
  return (
    <div>
      <div className="mb-2 flex items-center gap-3 text-sm">
        <button type="button" onClick={() => setOnlyInvalid(false)} aria-pressed={!onlyInvalid}
          className={`rounded-full px-3 py-1 ${!onlyInvalid ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>All ({rows.length})</button>
        {invalid > 0 && (
          <button type="button" onClick={() => setOnlyInvalid(true)} aria-pressed={onlyInvalid}
            className={`rounded-full px-3 py-1 ${onlyInvalid ? 'bg-red-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}>Needs attention ({invalid})</button>
        )}
      </div>
      <div className={`${maxHeight} overflow-auto rounded-lg border border-slate-200`}>
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr><th className="px-3 py-2">Chapter</th><th>Words</th><th>Expected</th><th>Status</th><th>Message</th></tr></thead>
          <tbody>
            {list.slice(0, shown).map((r) => (
              <tr key={r.index} onClick={() => onSelect?.(r.index)} data-testid={`chapter-row-${r.index}`}
                className={`border-t border-slate-100 ${onSelect ? 'cursor-pointer hover:bg-indigo-50/50' : ''} ${selected === r.index ? 'bg-indigo-50' : ''}`}>
                <td className="px-3 py-1.5 font-medium">{r.title}</td>
                <td className="tabular-nums">{r.count}</td>
                <td className="tabular-nums text-slate-500">{r.expected ?? '—'}</td>
                <td>{r.valid ? <Badge tone="green">OK</Badge> : <Badge tone="red">Wrong count / error</Badge>}</td>
                <td className="py-1.5 pr-3 text-xs text-red-700">{r.problems.join(' · ')}</td>
              </tr>))}
            {!list.length && <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">
              {onlyInvalid ? 'Every chapter is ready.' : 'No chapters'}</td></tr>}
          </tbody>
        </table>
      </div>
      {list.length > shown && (
        <button type="button" className="mt-2 text-sm font-medium text-indigo-600 hover:underline" onClick={() => setShown(shown + pageSize)}>
          Show {Math.min(pageSize, list.length - shown)} more ({list.length - shown} hidden)</button>)}
    </div>
  )
}
