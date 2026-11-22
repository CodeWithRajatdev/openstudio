import React, { useMemo, useRef, useState } from 'react'
import { CheckCircle2, CopyMinus, FileUp, Plus, Trash2, UploadCloud, X } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../store.jsx'
import { chapterReport, readNotes } from '../lib/chapterReport'
import ChapterTable, { Stat } from '../components/ChapterTable.jsx'
import { Badge, Button, Card, Empty, Notice, Progress, TextInput } from '../components/ui.jsx'

const ALLOWED = ['.xlsx', '.xlsm', '.txt', '.csv', '.tsv']
const MAX_BYTES = 25 * 1024 * 1024
const SEV = { error: 'red', warning: 'amber', info: 'slate' }

function checkFile(file) {
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
  if (ext === '.xls') return 'Old .xls files are not supported. In Excel choose File → Save As → Excel Workbook (.xlsx) and upload that.'
  if (!ALLOWED.includes(ext)) return `“${file.name}” is not a supported format. Upload an Excel (.xlsx), text (.txt) or CSV (.csv) file.`
  if (file.size === 0) return 'That file is empty.'
  if (file.size > MAX_BYTES) return `That file is ${(file.size / 1e6).toFixed(1)} MB; the limit is ${MAX_BYTES / 1e6} MB.`
  return null
}

export default function ImportWords() {
  const { state: s, dispatch, patch } = useApp()
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(null)       // 0-100 while uploading, 'parsing' afterwards
  const [err, setErr] = useState(null)
  const [pending, setPending] = useState(null)         // parsed but not yet accepted
  const [sheet, setSheet] = useState('__all__')
  const [newWord, setNewWord] = useState('')
  const [removed, setRemoved] = useState(null)
  const [drag, setDrag] = useState(false)
  const fileRef = useRef()
  const expected = s.wordsPerChapter
  const titleEnabled = !!s.layout.title_enabled

  async function runImport(file, o = {}) {
    const bad = checkFile(file)
    if (bad) { setErr(bad); return }
    const opt = { sheet, expected, firstLineTitle: titleEnabled, ...o }
    setBusy(true); setErr(null); setRemoved(null); setProgress(0)
    const form = new FormData()
    form.append('file', file)
    form.append('layout', 'lines')
    form.append('split_commas', false)
    form.append('first_line_title', opt.firstLineTitle)
    if (opt.sheet && opt.sheet !== '__all__') form.append('sheet', opt.sheet)
    if (opt.expected) form.append('expected_words', opt.expected)
    form.append('check_cross_chapter', s.validateOpts.checkCross)
    if (s.validateOpts.maxLen) form.append('max_word_length', s.validateOpts.maxLen)
    try {
      const r = await api.upload('/api/import', form, (p) => setProgress(p >= 100 ? 'parsing' : p))
      setPending({ file, data: r })
    } catch (e) { setErr(e.message) } finally {
      setBusy(false); setProgress(null)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function accept() {
    const r = pending.data
    dispatch({
      type: 'loadImport',
      chapters: r.chapters,
      issues: r.issues,
      info: {
        filename: r.filename,
        sha256: r.sha256,
        summary: r.summary,
        sheets: r.sheets,
        notes: readNotes(r.issues),
      },
    })
    setPending(null)
  }

  async function dedupe() {
    const r = await api.post('/api/bank/remove-duplicates', {
      chapters: s.chapters,
      rules: s.config.normalize,
      check_cross_chapter: s.validateOpts.checkCross,
      expected_words: expected || null,
    })
    dispatch({ type: 'setChapters', chapters: r.chapters })
    setRemoved(r.removed)
  }

  const live = useMemo(() => chapterReport(s.chapters, s.issues, expected), [s.chapters, s.issues, expected])
  const prev = useMemo(() => pending && chapterReport(pending.data.chapters, pending.data.issues, expected), [pending, expected])
  const byWord = useMemo(() => {
    const m = {}
    s.issues.forEach((i) => { if (i.word_id != null) (m[i.word_id] ||= []).push(i) })
    return m
  }, [s.issues])
  const ci = Math.min(s.selectedChapter, s.chapters.length - 1)
  const chapter = s.chapters[ci]
  const dupCount = s.issues.filter((i) => i.code === 'duplicate_in_chapter').length
  const blockingIssues = s.issues.filter((i) => i.severity === 'error')
  const blocking = blockingIssues.length

  return (
    <div className="space-y-5">
      <div className="grid gap-5 md:grid-cols-[1fr_20rem]">
        <label
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); e.dataTransfer.files[0] && runImport(e.dataTransfer.files[0]) }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-10 text-center text-sm text-slate-600 ${
            drag ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/40'
          }`}
        >
          <UploadCloud className="mb-2 text-slate-400" size={30} />
          {busy ? 'Reading file…' : <>Drag &amp; drop a file here, or <span className="font-semibold text-indigo-600">browse files</span></>}
          <span className="mt-1 text-xs text-slate-400">Excel (.xlsx) · Text (.txt) · CSV (.csv)</span>
          <input
            ref={fileRef}
            data-testid="file-input"
            type="file"
            accept=".csv,.tsv,.txt,.xlsx,.xlsm"
            className="hidden"
            onChange={(e) => e.target.files[0] && runImport(e.target.files[0])}
          />
        </label>

        <div className="rounded-xl bg-slate-50 p-4 text-xs text-slate-600">
          <div className="mb-1.5 font-semibold text-slate-700">File rules (applied automatically)</div>
          <ul className="list-disc space-y-1 pl-4 text-slate-600">
            <li>One line / row = one word</li>
            <li>Blank line / blank row = the chapter ends here</li>
            <li>
              {titleEnabled ? (
                <>Title is <b>ON</b>: first line of each chapter is the chapter title (not a word)</>
              ) : (
                <>Title is <b>OFF</b>: every line is a word</>
              )}
            </li>
            {expected != null && (
              <li>
                Every chapter must have <b>exactly {expected} words</b>
              </li>
            )}
          </ul>
          <p className="mt-2 text-[11px] text-slate-500">
            Nothing is ever added, removed, merged, split or skipped automatically.
          </p>
        </div>
      </div>

      {progress != null && (
        <div>
          <Progress value={progress === 'parsing' ? 100 : progress} max={100} />
          <p className="mt-1 text-xs text-slate-500">
            {progress === 'parsing' ? 'Upload complete — reading chapters…' : `Uploading… ${progress}%`}
          </p>
        </div>
      )}

      {err && <Notice tone="error" title="Could not import">{err}</Notice>}

      {pending && prev && (
        <Card
          title={`Import summary — ${pending.data.filename}`}
          className="border-indigo-300 ring-2 ring-indigo-100"
          action={<Badge tone="indigo">Preview before accepting</Badge>}
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Chapters" value={prev.totals.chapters} />
            <Stat label="Total words" value={prev.totals.words} />
            <Stat label="Ready chapters" value={prev.totals.valid} tone="green" />
            <Stat label="Chapters with issues" value={prev.totals.invalid} tone={prev.totals.invalid ? 'red' : undefined} />
          </div>

          {pending.data.sheets.length > 1 && (
            <fieldset className="mt-4 text-sm">
              <legend className="mb-1 font-medium text-slate-700">
                This workbook has {pending.data.sheets.length} worksheets
              </legend>
              <div className="flex flex-wrap gap-x-5 gap-y-1">
                {['__all__', ...pending.data.sheets.map((x) => x.name)].map((n) => (
                  <label key={n} className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="sheet"
                      checked={sheet === n}
                      onChange={() => {
                        setSheet(n)
                        runImport(pending.file, { sheet: n })
                      }}
                    />
                    {n === '__all__' ? 'All worksheets (in order)' : n}
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {readNotes(pending.data.issues).length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {readNotes(pending.data.issues).slice(0, 6).map((i, k) => (
                <li key={k} className="flex gap-2">
                  <Badge tone={SEV[i.severity]}>{i.severity}</Badge>
                  <span>{i.message}</span>
                </li>
              ))}
            </ul>
          )}

          {prev.totals.invalid > 0 && (
            <div className="mt-4">
              <Notice tone="warning" title={`${prev.totals.invalid} chapter(s) need attention`}>
                <ul className="mt-1 list-disc pl-5">
                  {pending.data.issues.filter((i) => i.severity === 'error').slice(0, 5).map((i, k) => (
                    <li key={k}>{i.message}</li>
                  ))}
                </ul>
                <p className="mt-1.5 text-xs">
                  Generate is blocked until fixed. Accept to fix in the app, or fix the file and re-upload.
                </p>
              </Notice>
            </div>
          )}

          <h3 className="mb-2 mt-5 text-sm font-semibold">Chapters found</h3>
          <ChapterTable rows={prev.rows} />
          <div className="mt-5 flex gap-2">
            <Button icon={CheckCircle2} onClick={accept}>
              Accept
            </Button>
            <Button variant="secondary" icon={X} onClick={() => { setPending(null); setErr(null) }}>
              Cancel — choose another file
            </Button>
          </div>
        </Card>
      )}

      {!s.chapters.length ? (
        !pending && (
          <Empty
            icon={FileUp}
            title="No word list imported yet"
            text="Drop an .xlsx, .txt or .csv file above, or load the built-in sample chapters to test."
          >
            <Button variant="secondary" onClick={() => dispatch({ type: 'sample' })}>
              Load sample chapters
            </Button>
          </Empty>
        )
      ) : (
        <div className="space-y-5">
          {blocking > 0 && (
            <Notice tone="error" title="Generate is blocked — fix the chapters below or re-upload your file">
              <ul className="mt-1 list-disc pl-5">
                {blockingIssues.slice(0, 6).map((i, k) => (
                  <li key={k}>{i.message}</li>
                ))}
              </ul>
            </Notice>
          )}

          <Card
            title={`Imported chapters${s.importInfo?.filename ? ` — ${s.importInfo.filename}` : ''}`}
            action={
              dupCount > 0 && (
                <Button variant="secondary" icon={CopyMinus} onClick={dedupe}>
                  Remove {dupCount} duplicate(s)
                </Button>
              )
            }
          >
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Chapters" value={live.totals.chapters} />
              <Stat label="Total words" value={live.totals.words} />
              <Stat label="Ready" value={live.totals.valid} tone="green" />
              <Stat label="With issues" value={live.totals.invalid} tone={live.totals.invalid ? 'red' : undefined} />
            </div>

            {removed && (
              <div className="mb-3">
                <Notice tone="info" title={`Removed ${removed.length} duplicate(s)`}>
                  {removed.slice(0, 8).map((r) => `${r.word} (${r.chapter})`).join(', ')}
                  {removed.length > 8 && ' …'}
                </Notice>
              </div>
            )}

            <ChapterTable rows={live.rows} selected={ci} onSelect={(i) => patch({ selectedChapter: i })} />
          </Card>

          {chapter && (
            <Card
              title={
                <span className="flex items-center gap-2">
                  <input
                    aria-label="Chapter title"
                    value={chapter.title}
                    onChange={(e) => dispatch({ type: 'renameChapter', ci, title: e.target.value })}
                    className="w-64 rounded border border-transparent px-1 text-sm font-semibold hover:border-slate-300 focus:border-indigo-400 focus:outline-none"
                  />
                  <span className="text-xs font-normal text-slate-500">
                    {chapter.words.length}{expected ? ` / ${expected}` : ''} words
                  </span>
                </span>
              }
              action={
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    icon={Plus}
                    onClick={() => dispatch({ type: 'addChapter', title: `Chapter ${s.chapters.length + 1}` })}
                  >
                    Add chapter
                  </Button>
                  <Button variant="danger" icon={Trash2} onClick={() => dispatch({ type: 'removeChapter', ci })}>
                    Remove chapter
                  </Button>
                </div>
              }
            >
              {live.rows[ci]?.errors.filter((e) => e.code === 'wrong_word_count').map((e) => (
                <div key="wc" className="mb-3">
                  <Notice tone="error">{e.message}</Notice>
                </div>
              ))}
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase text-slate-500">
                    <th className="w-10 pb-2">#</th>
                    <th className="pb-2">Word</th>
                    <th className="pb-2">Source</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody>
                  {chapter.words.map((w, n) => (
                    <tr key={w.id} className="border-t border-slate-100">
                      <td className="py-1 text-slate-400">{n + 1}</td>
                      <td className="py-1 pr-3">
                        <input
                          aria-label={`Word ${n + 1}`}
                          defaultValue={w.text}
                          key={w.id + ':' + w.text}
                          onBlur={(e) => e.target.value.trim() !== w.text && dispatch({ type: 'editWord', ci, id: w.id, text: e.target.value })}
                          className={`w-full rounded border px-2 py-1 ${
                            byWord[w.id]?.some((i) => i.severity === 'error')
                              ? 'border-red-300 bg-red-50'
                              : byWord[w.id]
                              ? 'border-amber-300 bg-amber-50'
                              : 'border-transparent hover:border-slate-300'
                          }`}
                        />
                        {byWord[w.id]?.map((i, k) => (
                          <div key={k} className="mt-0.5 text-xs text-red-600">
                            {i.message}
                          </div>
                        ))}
                      </td>
                      <td className="py-1 text-xs text-slate-400">
                        {w.source}
                        {w.raw.trim() !== w.text && <div title={w.raw}>edited (was “{w.raw.trim()}”)</div>}
                      </td>
                      <td className="py-1">
                        <button
                          type="button"
                          aria-label={`Delete ${w.text}`}
                          onClick={() => dispatch({ type: 'deleteWord', ci, id: w.id })}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!chapter.words.length && <p className="py-4 text-sm text-slate-500">This chapter has no words yet.</p>}
              <form
                className="mt-3 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  if (newWord.trim()) {
                    dispatch({ type: 'addWord', ci, text: newWord })
                    setNewWord('')
                  }
                }}
              >
                <TextInput
                  aria-label="New word"
                  placeholder="Add a word or phrase…"
                  value={newWord}
                  onChange={(e) => setNewWord(e.target.value)}
                />
                <Button type="submit" variant="secondary" icon={Plus}>
                  Add
                </Button>
              </form>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
