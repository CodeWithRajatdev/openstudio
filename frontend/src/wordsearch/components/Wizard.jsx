import React from 'react'
import { ArrowLeft, ArrowRight, Check, Grid3x3 } from 'lucide-react'
import { useApp } from '../store.jsx'
import { BOOK_SIZES } from '../defaults'
import { UNITS, describeSize, fromMm, toMm, validateCustomSize } from '../lib/units'
import { Button, Card, Field, Notice, NumberInput, Select, TextInput } from './ui.jsx'

// ---------------------------------------------------------------- STEP 1 - PROJECT
export function Step1Project() {
  const { state: s, patch, goStep, dispatch } = useApp()
  return (
    <section className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold tracking-tight">What are you creating?</h1>
      <p className="mt-1 text-slate-500">Pick a project type and give your project a name.</p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          aria-pressed="true"
          className="relative rounded-2xl border-2 border-indigo-500 bg-white p-5 text-left shadow-sm ring-4 ring-indigo-100"
        >
          <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-white">
            <Check size={14} />
          </span>
          <Grid3x3 className="text-indigo-600" size={34} />
          <div className="mt-4 text-lg font-bold">Word Search</div>
          <p className="mt-1 text-sm text-slate-500">
            Chapter-based word-search puzzle books with matching solution pages.
          </p>
        </button>
      </div>

      <div className="mt-8 max-w-md">
        <Field label="Project name" hint="Used for the exported PDF file name (<project-name>.pdf).">
          <TextInput
            value={s.projectName === 'Untitled project' ? '' : s.projectName}
            placeholder="e.g. English Word Search Vol. 1"
            onChange={(e) => patch({ projectName: e.target.value || 'Untitled project' })}
          />
        </Field>
      </div>

      <div className="mt-8 flex items-center justify-end">
        <Button
          icon={ArrowRight}
          onClick={() => {
            dispatch({ type: 'setup', patch: { projectType: 'word_search', step: 2 } })
            goStep(2)
          }}
        >
          Continue
        </Button>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- STEP 2 - TRIM SIZE
export function Step2TrimSize() {
  const { state: s, patch, goStep, dispatch } = useApp()
  const st = s.setup
  const set = (p) => dispatch({ type: 'setup', patch: p })
  const custom = st.sizeId === 'custom'
  const check = custom ? validateCustomSize(st.custom) : null
  const std = BOOK_SIZES.find((b) => b.id === st.sizeId)
  const wMm = custom ? check.wMm : std?.w
  const hMm = custom ? check.hMm : std?.h
  const ok = custom ? check.ok : !!std

  function changeUnit(unit) {
    const c = st.custom
    const conv = (v) => (Number(v) > 0 ? Math.round(fromMm(toMm(v, c.unit), unit) * 1000) / 1000 : v)
    set({ custom: { w: conv(c.w), h: conv(c.h), unit } })
  }

  function handleContinue() {
    if (!ok) return
    patch({ layout: { ...s.layout, page_width: wMm, page_height: hMm } })
    set({ started: true, step: 3 })
    goStep(3)
  }

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Trim Size</h1>
        <p className="mt-1 text-slate-500">Choose a standard interior trim size or enter a custom width and height.</p>
      </div>

      <Card title="Standard sizes">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {BOOK_SIZES.map((b) => {
            const sel = st.sizeId === b.id
            const scale = 64 / Math.max(b.w, b.h)
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => set({ sizeId: b.id })}
                aria-pressed={sel}
                className={`flex flex-col items-center rounded-xl border-2 px-2 py-3 text-xs transition ${sel ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-slate-300'
                  }`}
              >
                <div className="flex h-[68px] items-end">
                  <div
                    className="border border-slate-400 bg-white shadow-sm"
                    style={{ width: b.w * scale, height: b.h * scale }}
                  />
                </div>
                <span className="mt-2 font-semibold">{b.label}</span>
              </button>
            )
          })}
        </div>
      </Card>

      <Card title="Custom size">
        <div className={`rounded-xl border-2 p-4 ${custom ? 'border-indigo-500 bg-indigo-50/40' : 'border-slate-200'}`}>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Width">
              <NumberInput
                aria-label="Custom width"
                step="any"
                value={st.custom.w}
                onChange={(v) => set({ sizeId: 'custom', custom: { ...st.custom, w: v } })}
              />
            </Field>
            <Field label="Height">
              <NumberInput
                aria-label="Custom height"
                step="any"
                value={st.custom.h}
                onChange={(v) => set({ sizeId: 'custom', custom: { ...st.custom, h: v } })}
              />
            </Field>
            <Field label="Unit">
              <Select aria-label="Unit" value={st.custom.unit} onChange={(e) => changeUnit(e.target.value)} options={UNITS} />
            </Field>
          </div>
          {!custom && (
            <button
              type="button"
              className="mt-3 text-sm font-medium text-indigo-600 hover:underline"
              onClick={() => set({ sizeId: 'custom' })}
            >
              Use custom size
            </button>
          )}
          {custom && !check.ok && (
            <div className="mt-3">
              <Notice tone="error">{check.error}</Notice>
            </div>
          )}
        </div>
      </Card>

      {ok && (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 px-4 py-3 text-sm">
          <span className="text-slate-600">Selected size: </span>
          <b data-testid="selected-size" className="text-slate-900">
            {describeSize(wMm, hMm)}
          </b>
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <Button
          variant="secondary"
          icon={ArrowLeft}
          onClick={() => {
            set({ step: 1 })
            goStep(1)
          }}
        >
          Back
        </Button>
        <Button icon={ArrowRight} disabled={!ok} onClick={handleContinue}>
          Continue
        </Button>
      </div>
    </section>
  )
}

export default function Wizard() {
  const { state: s } = useApp()
  return s.step === 2 ? <Step2TrimSize /> : <Step1Project />
}
