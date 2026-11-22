import { useState } from "react";
import { FileSpreadsheet, Upload } from "lucide-react";
import { useStudio } from "../../context/ProjectStudioContext";
import { CollapsibleSection } from "../CollapsibleSection";
import { StatusBadge } from "../StatusBadge";
import { Tooltip } from "../Tooltip";

type PageUnit = "pt" | "mm" | "in";

function ptToUnit(pt: number, unit: PageUnit): number {
  if (unit === "in") return Math.round((pt / 72) * 1000) / 1000;
  if (unit === "mm") return Math.round(((pt * 25.4) / 72) * 100) / 100;
  return Math.round(pt * 100) / 100;
}

function unitToPt(val: number, unit: PageUnit): number {
  if (!Number.isFinite(val)) return 0;
  if (unit === "in") return Math.round(val * 72 * 100) / 100;
  if (unit === "mm") return Math.round(((val * 72) / 25.4) * 100) / 100;
  return Math.round(val * 100) / 100;
}

export function PageAndImportSections() {
  const {
    guidelineMode,
    setGuidelineMode,
    pageUnit,
    setPageUnit,
    independentMargins,
    setIndependentMargins,
    marginTop,
    setMarginTop,
    marginBottom,
    setMarginBottom,
    marginLeft,
    setMarginLeft,
    marginRight,
    setMarginRight,
    setUniformMargin,
    gutterPt,
    setGutterPt,
    startPuzzlesOnRightHandPage,
    setStartPuzzlesOnRightHandPage,
    showPageNumbers,
    setShowPageNumbers,
    wordsPerChapter,
    setWordsPerChapter,
    importColName,
    setImportColName,
    stagedBatch,
    uploadProgress,
    handleStageFile,
    handleAcceptImport,
    chapters,
    firstLineIsTitle,
    setFirstLineIsTitle,
  } = useStudio();

  const [isDragging, setIsDragging] = useState(false);

  const unitStep = pageUnit === "in" ? 0.05 : pageUnit === "mm" ? 0.5 : 1;
  const maxMarginDisplay = ptToUnit(200, pageUnit);
  const maxGutterDisplay = ptToUnit(100, pageUnit);

  return (
    <>
      {/* SECTION A: PAGE SETTINGS */}
      <CollapsibleSection
        letter="A"
        title="Page Settings"
        subtitle="Margins, KDP guidelines, gutter & page numbering"
        badge={
          <span className="text-xs text-slate-500">
            {guidelineMode.toUpperCase()} • {ptToUnit(marginTop, pageUnit)} {pageUnit}
          </span>
        }
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Guideline Mode
              <Tooltip
                label="Guideline Mode"
                text="KDP mode enforces safe print margins; Paper Edges previews right up to trim edges."
              />
            </label>
            <select
              value={guidelineMode}
              onChange={(e) => setGuidelineMode(e.target.value as "kdp" | "paper")}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
            >
              <option value="kdp">KDP Print Margin Guidelines</option>
              <option value="paper">Paper Edges Only</option>
            </select>
          </div>

          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Margin &amp; Gutter Unit
              <Tooltip
                label="Page Units"
                text="Display and enter margins and gutter in points (pt), millimeters (mm), or inches (in)."
              />
            </label>
            <select
              aria-label="Page Settings Unit"
              value={pageUnit}
              onChange={(e) => setPageUnit(e.target.value as PageUnit)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
            >
              <option value="pt">Points (pt)</option>
              <option value="mm">Millimeters (mm)</option>
              <option value="in">Inches (in)</option>
            </select>
          </div>

          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Binding Gutter ({pageUnit})
              <Tooltip
                label="Binding Gutter"
                text="Extra inside margin reserved along the spine for paperback binding (72 pt = 25.4 mm = 1 in)."
              />
            </label>
            <input
              type="number"
              min={0}
              max={maxGutterDisplay}
              step={unitStep}
              value={ptToUnit(gutterPt, pageUnit)}
              onChange={(e) => setGutterPt(Math.max(0, Math.min(100, unitToPt(Number(e.target.value), pageUnit))))}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-5 text-xs pt-1">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={independentMargins}
              onChange={(e) => setIndependentMargins(e.target.checked)}
            />
            Independent top/left/bottom/right margins
            <Tooltip text="Set a single uniform margin or customize each edge independently." />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={startPuzzlesOnRightHandPage}
              onChange={(e) => setStartPuzzlesOnRightHandPage(e.target.checked)}
            />
            Start puzzles on a right-hand page
            <Tooltip text="Inserts a front-matter blank page if needed so Chapter 1 begins on an odd right-hand page." />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={showPageNumbers}
              onChange={(e) => setShowPageNumbers(e.target.checked)}
            />
            Show page numbers
          </label>
        </div>

        {!independentMargins ? (
          <div className="max-w-xs text-xs">
            <label className="block font-medium text-slate-700 mb-1">
              All Page Margins ({pageUnit})
              <Tooltip text="Uniform distance from trim edge on all 4 sides (36 pt = 12.7 mm = 0.5 in)." />
            </label>
            <input
              type="number"
              min={0}
              max={maxMarginDisplay}
              step={unitStep}
              value={ptToUnit(marginTop, pageUnit)}
              onChange={(e) => setUniformMargin(unitToPt(Number(e.target.value), pageUnit))}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2"
            />
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <label className="block font-medium text-slate-600 mb-1">Top ({pageUnit})</label>
              <input
                type="number"
                min={0}
                max={maxMarginDisplay}
                step={unitStep}
                value={ptToUnit(marginTop, pageUnit)}
                onChange={(e) => setMarginTop(Math.max(0, Math.min(200, unitToPt(Number(e.target.value), pageUnit))))}
                className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-600 mb-1">Bottom ({pageUnit})</label>
              <input
                type="number"
                min={0}
                max={maxMarginDisplay}
                step={unitStep}
                value={ptToUnit(marginBottom, pageUnit)}
                onChange={(e) => setMarginBottom(Math.max(0, Math.min(200, unitToPt(Number(e.target.value), pageUnit))))}
                className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-600 mb-1">Left ({pageUnit})</label>
              <input
                type="number"
                min={0}
                max={maxMarginDisplay}
                step={unitStep}
                value={ptToUnit(marginLeft, pageUnit)}
                onChange={(e) => setMarginLeft(Math.max(0, Math.min(200, unitToPt(Number(e.target.value), pageUnit))))}
                className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-600 mb-1">Right ({pageUnit})</label>
              <input
                type="number"
                min={0}
                max={maxMarginDisplay}
                step={unitStep}
                value={ptToUnit(marginRight, pageUnit)}
                onChange={(e) => setMarginRight(Math.max(0, Math.min(200, unitToPt(Number(e.target.value), pageUnit))))}
                className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
              />
            </div>
          </div>
        )}
      </CollapsibleSection>

      {/* SECTION B: IMPORT WORD LIST (+ CLUES) */}
      <CollapsibleSection
        letter="B"
        title="Import Word List (+ Clues)"
        subtitle="Drag & drop .xlsx/.csv/.txt file with chapters separated by blank lines"
        badge={<span className="text-xs text-slate-500">{chapters.length} chapters</span>}
        defaultOpen={chapters.length === 0}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Default First Chapter Name
              <Tooltip text="Used if an imported file or pasted block has no header or group name column." />
            </label>
            <input
              type="text"
              value={importColName}
              onChange={(e) => setImportColName(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Expected Words per Chapter
              <Tooltip text="Choose 'Varies by chapter' when each chapter can have a different number of words, or pick 'Fixed count' to check every chapter against an exact word count." />
            </label>
            <div className="flex items-center gap-2">
              <select
                aria-label="Expected Words per Chapter"
                value={wordsPerChapter === null ? "variable" : "fixed"}
                onChange={(e) => {
                  if (e.target.value === "variable") {
                    setWordsPerChapter(null);
                  } else {
                    setWordsPerChapter(15);
                  }
                }}
                className="flex-1 border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
              >
                <option value="variable">Varies by chapter (different counts)</option>
                <option value="fixed">Fixed target count</option>
              </select>
              {wordsPerChapter !== null && (
                <input
                  type="number"
                  aria-label="Fixed expected words count"
                  min={1}
                  max={200}
                  value={wordsPerChapter}
                  onChange={(e) => {
                    const raw = e.target.value.trim();
                    if (raw === "") {
                      setWordsPerChapter(null);
                    } else {
                      setWordsPerChapter(Math.max(1, Math.min(200, Number(raw))));
                    }
                  }}
                  className="w-20 border border-slate-300 rounded-lg px-2.5 py-2"
                />
              )}
            </div>
          </div>
        </div>

        <label className="flex items-start gap-2 text-xs bg-white border border-slate-200 rounded-lg px-3 py-2">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={firstLineIsTitle}
            onChange={(e) => setFirstLineIsTitle(e.target.checked)}
            aria-label="First line of each chapter is its title"
          />
          <span>
            <span className="font-medium text-slate-800">First line of each chapter is its title</span>
            <Tooltip text="When on, the first line after each blank line becomes the chapter name. It is printed on the puzzle page and labels the puzzle on the answer pages. A leading number like '1.' is removed." />
            <span className="block text-slate-500 mt-0.5 font-mono">
              1. Sense of Organs / Nose | Helps breathe / Ear | Helps hear / (blank line) / 2. Farm animals / ...
            </span>
          </span>
        </label>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleStageFile(file);
          }}
          className={`border-2 border-dashed rounded-xl p-4 text-center transition ${
            isDragging
              ? "border-slate-900 bg-slate-100"
              : "border-slate-300 bg-slate-50/50"
          }`}
        >
          <FileSpreadsheet className="w-6 h-6 text-slate-600 mx-auto mb-1" />
          <p className="text-xs font-medium text-slate-700">
            Drag &amp; drop Excel (.xlsx), CSV, or TXT file here
          </p>
          <p className="text-[11px] text-slate-500 mb-2.5">
            Supports Word | Word, Clue | Word, Clue, Difficulty. Blank lines split chapters; multi-word spaces never split chapters.
          </p>
          <label className="inline-flex items-center gap-1.5 bg-white border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer">
            <Upload className="w-3.5 h-3.5" /> Browse File
            <input
              type="file"
              accept=".csv,.tsv,.xlsx,.xlsm,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleStageFile(file);
                e.target.value = "";
              }}
              className="hidden"
            />
          </label>
        </div>

        {uploadProgress > 0 && uploadProgress < 100 && (
          <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-slate-900 h-1.5 transition-all"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
        )}

        {/* Staged Preview & Accept */}
        {stagedBatch && (
          <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 space-y-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-sm text-slate-900">
                Pre-Save Import Report
              </span>
              <span className="text-slate-500">Press Enter or click Accept to save</span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-2">
                <div className="text-base font-bold text-emerald-700">
                  {stagedBatch.report.valid_count}
                </div>
                <div className="text-[11px] text-emerald-600">Valid Words</div>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-2">
                <div className="text-base font-bold text-amber-700">
                  {stagedBatch.report.duplicate_count}
                </div>
                <div className="text-[11px] text-amber-600">Duplicates Skipped</div>
              </div>
              <div className="bg-red-50 border border-red-200 rounded-lg p-2">
                <div className="text-base font-bold text-red-700">
                  {stagedBatch.report.invalid_count}
                </div>
                <div className="text-[11px] text-red-600">Invalid Skipped</div>
              </div>
            </div>

            {stagedBatch.report.groups?.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-lg divide-y divide-slate-100">
                {stagedBatch.report.groups.map((ch: any, idx: number) => (
                  <div key={idx} className="px-3 py-2 flex items-center justify-between gap-2">
                    <div>
                      <span className="font-semibold text-slate-800">{ch.name}</span>
                      <span className="ml-2 text-slate-500">{ch.word_count_label}</span>
                    </div>
                    <StatusBadge status={ch.status} />
                  </div>
                ))}
              </div>
            )}

            {stagedBatch.report.chapter_titles?.length > 0 && (
              <div className="bg-white border border-slate-200 rounded p-2 text-slate-700 space-y-0.5">
                <div className="font-semibold">Chapter Titles Detected (first line of each chapter):</div>
                {stagedBatch.report.chapter_titles.map((t: any, idx: number) => (
                  <div key={idx}>
                    {t.cell_ref}: "{t.raw}" → <b>{t.title}</b>
                  </div>
                ))}
              </div>
            )}

            {stagedBatch.report.skipped_headers?.length > 0 && (
              <div className="text-slate-600 space-y-0.5">
                <div className="font-semibold">Headers Skipped:</div>
                {stagedBatch.report.skipped_headers.map((h: any, idx: number) => (
                  <div key={idx}>{h.note}</div>
                ))}
              </div>
            )}

            {stagedBatch.report.extra_columns?.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded p-2 text-amber-900 space-y-0.5">
                <div className="font-semibold">Data Outside Word/Clue Columns:</div>
                {stagedBatch.report.extra_columns.map((ex: any, idx: number) => (
                  <div key={idx}>
                    {ex.cell_ref}: "{ex.value}" ({ex.reason})
                  </div>
                ))}
              </div>
            )}

            {stagedBatch.report.invalid?.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded p-2 text-red-800 space-y-0.5">
                <div className="font-semibold">Invalid Entries (Reported, Not Dropped Silently):</div>
                {stagedBatch.report.invalid.map((inv: any, idx: number) => (
                  <div key={idx}>
                    {inv.cell_ref || `Row ${inv.row}`}: "{inv.raw}" — {inv.reason}
                  </div>
                ))}
              </div>
            )}

            {stagedBatch.report.duplicates?.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded p-2 text-amber-800 space-y-0.5">
                <div className="font-semibold">Duplicates Skipped:</div>
                {stagedBatch.report.duplicates.map((dup: any, idx: number) => (
                  <div key={idx}>
                    Row {dup.row}: "{dup.raw}" — {dup.reason}
                  </div>
                ))}
              </div>
            )}

            {stagedBatch.report.warnings?.length > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded p-2 text-blue-800 space-y-0.5">
                <div className="font-semibold">Warnings:</div>
                {stagedBatch.report.warnings.map((w: any, idx: number) => (
                  <div key={idx}>
                    Row {w.row}: {w.reason}
                  </div>
                ))}
              </div>
            )}

            <button
              type="button"
              onClick={handleAcceptImport}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2.5 rounded-lg"
            >
              Accept ({stagedBatch.report.valid_count} words across{" "}
              {stagedBatch.report.group_count} chapters)
            </button>
          </div>
        )}
      </CollapsibleSection>
    </>
  );
}
