import React, { useState } from 'react'
import { AlertCircle, AlertTriangle, ChevronDown, ChevronRight, Info, Loader2 } from 'lucide-react'

export const Card = ({ title, action, children, className = '' }) => (
  <section className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
    {(title || action) && (
      <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>{action}
      </header>
    )}
    <div className="p-5">{children}</div>
  </section>
)

export function Section({ title, subtitle, badge, action, defaultOpen = true, open: controlledOpen, onToggle, children, testId }) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen
  const toggle = () => {
    const next = !isOpen
    setInternalOpen(next)
    onToggle?.(next)
  }
  return (
    <section data-testid={testId} className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between px-5 py-3.5">
        <button type="button" onClick={toggle} aria-expanded={isOpen}
          className="flex flex-1 items-center gap-2.5 text-left">
          {isOpen ? <ChevronDown size={17} className="text-slate-500" /> : <ChevronRight size={17} className="text-slate-500" />}
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-800">{title}</span>
              {badge}
            </div>
            {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
          </div>
        </button>
        {action && <div className="ml-3">{action}</div>}
      </div>
      {isOpen && <div className="border-t border-slate-100 p-5">{children}</div>}
    </section>
  )
}

const variants = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300',
  secondary: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-white text-red-600 border border-red-200 hover:bg-red-50 disabled:text-red-300',
  ghost: 'text-slate-600 hover:bg-slate-100',
}
export const Button = ({ variant = 'primary', icon: Icon, loading, children, className = '', ...p }) => (
  <button {...p} disabled={p.disabled || loading}
    className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${variants[variant]} ${className}`}>
    {loading ? <Loader2 size={16} className="animate-spin" /> : Icon && <Icon size={16} />}{children}
  </button>
)

export const Field = ({ label, hint, children }) => (
  <label className="block text-sm">
    <span className="mb-1 block font-medium text-slate-700">{label}</span>{children}
    {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
  </label>
)

const inputCls = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100'
export const TextInput = (p) => <input {...p} className={`${inputCls} ${p.className || ''}`} />
export const NumberInput = ({ value, onChange, ...p }) => (
  <input type="number" {...p} value={value ?? ''} className={inputCls}
    onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))} />
)
export const Select = ({ options, ...p }) => (
  <select {...p} className={inputCls}>
    {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
  </select>
)

export const ColorInput = ({ label, hint, value, onChange, allowNone = false, noneLabel = 'None', fallback = '#000000', ariaLabel }) => {
  const hasColor = value != null && value !== ''
  const shown = hasColor ? value : fallback
  return (
    <div className="block text-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-medium text-slate-700">{label}</span>
        {allowNone && (
          <label className="flex cursor-pointer items-center gap-1 text-xs text-slate-500">
            <input type="checkbox" checked={!hasColor}
              onChange={(e) => onChange(e.target.checked ? null : fallback)} />
            {noneLabel}
          </label>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input type="color" aria-label={ariaLabel || label} disabled={allowNone && !hasColor}
          value={shown} onChange={(e) => onChange(e.target.value)}
          className="h-9 w-11 shrink-0 cursor-pointer rounded border border-slate-300 bg-white p-0.5 disabled:opacity-40" />
        <input type="text" aria-label={`${ariaLabel || label} hex`} disabled={allowNone && !hasColor}
          value={hasColor ? value : noneLabel}
          onChange={(e) => /^#[0-9a-fA-F]{0,6}$/.test(e.target.value) && onChange(e.target.value)}
          className={`${inputCls} font-mono text-xs uppercase disabled:bg-slate-50 disabled:text-slate-400`} />
      </div>
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </div>
  )
}

export const Toggle = ({ checked, onChange, label, hint }) => (
  <label className="flex cursor-pointer items-start gap-3 text-sm">
    <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)}
      className="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600" />
    <span><span className="font-medium text-slate-700">{label}</span>
      {hint && <span className="block text-xs text-slate-500">{hint}</span>}</span>
  </label>
)

const badge = {
  slate: 'bg-slate-100 text-slate-700', green: 'bg-emerald-100 text-emerald-700',
  red: 'bg-red-100 text-red-700', amber: 'bg-amber-100 text-amber-800', indigo: 'bg-indigo-100 text-indigo-700',
}
export const Badge = ({ tone = 'slate', children }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge[tone]}`}>{children}</span>
)

export const Empty = ({ icon: Icon, title, text, children }) => (
  <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
    {Icon && <Icon size={36} className="mb-3 text-slate-400" />}
    <h3 className="font-semibold text-slate-800">{title}</h3>
    <p className="mt-1 max-w-md text-sm text-slate-500">{text}</p>
    <div className="mt-4 flex gap-2">{children}</div>
  </div>
)

export const Progress = ({ value, max, tone = 'indigo' }) => {
  const pct = max ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div role="progressbar" aria-valuenow={value} aria-valuemax={max}
      className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full ${tone === 'green' ? 'bg-emerald-500' : 'bg-indigo-500'} transition-all`}
        style={{ width: `${pct}%` }} />
    </div>
  )
}

const noteTone = {
  error: ['border-red-200 bg-red-50 text-red-800', AlertCircle],
  warning: ['border-amber-200 bg-amber-50 text-amber-800', AlertTriangle],
  info: ['border-sky-200 bg-sky-50 text-sky-800', Info],
}
export const Notice = ({ tone = 'info', title, children }) => {
  const [cls, Icon] = noteTone[tone]
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex gap-3 rounded-lg border px-4 py-3 text-sm ${cls}`}>
      <Icon size={18} className="mt-0.5 shrink-0" />
      <div>{title && <div className="font-semibold">{title}</div>}{children}</div>
    </div>
  )
}

export const PageHeader = ({ title, subtitle, children }) => (
  <div className="mb-6 flex items-start justify-between gap-4">
    <div><h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}</div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
)

export const SvgPage = ({ svg, zoom = 100, showMarginGuide = false, layout = null }) => {
  let Guide = null
  if (showMarginGuide && layout) {
    const mt = layout.margin + (layout.extra_margins ? layout.margin_top : 0)
    const mr = layout.margin + (layout.extra_margins ? layout.margin_right : 0)
    const mb = layout.margin + (layout.extra_margins ? layout.margin_bottom : 0)
    const ml = layout.margin + (layout.extra_margins ? layout.margin_left : 0)
    const leftPct = (ml / layout.page_width) * 100
    const topPct = (mt / layout.page_height) * 100
    const widthPct = Math.max(0, ((layout.page_width - ml - mr) / layout.page_width) * 100)
    const heightPct = Math.max(0, ((layout.page_height - mt - mb) / layout.page_height) * 100)
    Guide = (
      <div data-testid="margin-guide"
        className="pointer-events-none absolute border border-dashed border-indigo-400/80"
        style={{ left: `${leftPct}%`, top: `${topPct}%`, width: `${widthPct}%`, height: `${heightPct}%` }} />
    )
  }
  return (
    <div className="overflow-auto">
      <div className="svg-page relative mx-auto overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-all"
        style={{ width: `${zoom}%`, maxWidth: zoom === 100 ? '100%' : 'none' }}>
        <div dangerouslySetInnerHTML={{ __html: svg }} />
        {Guide}
      </div>
    </div>
  )
}

export function Modal({ title, step, onClose, footer, children, wide = false }) {
  React.useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div role="dialog" aria-modal="true" aria-label={title}
        className={`flex max-h-[92vh] w-full flex-col rounded-2xl bg-white shadow-2xl ${wide ? 'max-w-3xl' : 'max-w-xl'}`}>
        <header className="flex items-start justify-between border-b border-slate-100 px-6 py-4">
          <div>
            {step && <div className="text-xs font-semibold uppercase tracking-wide text-indigo-600">{step}</div>}
            <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          </div>
          {onClose && <button aria-label="Go back" onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700">✕</button>}
        </header>
        <div className="overflow-auto px-6 py-5">{children}</div>
        {footer && <footer className="flex items-center justify-between gap-3 border-t border-slate-100 px-6 py-4">{footer}</footer>}
      </div>
    </div>
  )
}
