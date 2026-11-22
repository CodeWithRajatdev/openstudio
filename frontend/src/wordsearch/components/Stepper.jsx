import React from 'react'

export const WORKFLOW = [
  'Project',
  'Trim Size',
  'Puzzle Setup',
  'Review & Download',
]

export default function Stepper({ current = 1 }) {
  const n = Math.max(1, Math.min(WORKFLOW.length, Number(current) || 1))
  const label = WORKFLOW[n - 1]
  return (
    <div aria-label="Step indicator" className="mb-6 flex items-center justify-between border-b border-slate-200 pb-3 text-xs text-slate-500">
      <div className="flex items-center gap-2">
        <span data-testid="step-counter" className="rounded-full bg-indigo-50 px-2.5 py-0.5 font-semibold text-indigo-700">
          Step {n} of {WORKFLOW.length}
        </span>
        <span className="font-medium text-slate-700">{label}</span>
      </div>
      <div className="hidden gap-1.5 sm:flex" aria-hidden="true">
        {WORKFLOW.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 w-6 rounded-full transition-colors ${i + 1 === n ? 'bg-indigo-600' : i + 1 < n ? 'bg-emerald-500' : 'bg-slate-200'
              }`}
          />
        ))}
      </div>
    </div>
  )
}

