import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Lock,
  Play,
  RefreshCw,
  Unlock,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useStudio } from "../context/ProjectStudioContext";
import { StatusBadge } from "./StatusBadge";
import { Tooltip } from "./Tooltip";

export function LivePreviewPane() {
  const {
    chapters,
    activeCollectionId,
    setActiveCollectionId,
    activeChapter,
    activeChapterIndex,
    goPrevChapter,
    goNextChapter,
    puzzle,
    previewMode,
    setPreviewMode,
    previewZoom,
    setPreviewZoom,
    showMarginGuides,
    setShowMarginGuides,
    guidelineMode,
    marginTop,
    marginBottom,
    marginLeft,
    marginRight,
    gutterPt,
    trimValidation,
    puzzleSvg,
    answerKeySvg,
    solutionsPerPage,
    previewLoading,
    generatingPuzzle,
    handleGenerateChapterPuzzle,
    handleInlineChapterAction,
    handleDownloadSinglePuzzle,
    unplacedEdits,
    setUnplacedEdits,
    seedPinned,
    setSeedPinned,
    seed,
    setSeed,
    strategy,
    setStrategy,
    showAdvanced,
    setShowAdvanced,
  } = useStudio();

  const marginLeftPct = trimValidation.widthPt > 0 ? ((marginLeft + gutterPt) / trimValidation.widthPt) * 100 : 8;
  const marginRightPct = trimValidation.widthPt > 0 ? (marginRight / trimValidation.widthPt) * 100 : 6;
  const marginTopPct = trimValidation.heightPt > 0 ? (marginTop / trimValidation.heightPt) * 100 : 6;
  const marginBottomPct = trimValidation.heightPt > 0 ? (marginBottom / trimValidation.heightPt) * 100 : 6;

  const renderSvgCard = (svgHtml: string, label: string) => (
    <div className="flex flex-col items-center">
      <div className="text-[11px] font-medium text-slate-500 mb-1">{label}</div>
      <div
        className="relative bg-white border border-slate-300 shadow-sm inline-block origin-top transition-transform"
        style={{
          transform: `scale(${previewZoom / 100})`,
          marginBottom: previewZoom > 100 ? `${(previewZoom - 100) * 3}px` : undefined,
        }}
      >
        {svgHtml ? (
          <div
            className={`w-[340px] [&>svg]:w-full [&>svg]:h-auto transition-opacity duration-100 ${
              previewLoading ? "opacity-75" : "opacity-100"
            }`}
            dangerouslySetInnerHTML={{ __html: svgHtml }}
          />
        ) : (
          <div className="w-[340px] h-[440px] flex items-center justify-center text-xs text-slate-400">
            Rendering SVG preview...
          </div>
        )}

        {showMarginGuides && (
          <div
            aria-label="Margin guide overlay"
            className="pointer-events-none absolute inset-0"
            style={{
              paddingTop: `${marginTopPct}%`,
              paddingBottom: `${marginBottomPct}%`,
              paddingLeft: `${marginLeftPct}%`,
              paddingRight: `${marginRightPct}%`,
            }}
          >
            <div
              className={`w-full h-full border border-dashed ${
                guidelineMode === "kdp" ? "border-sky-500/70" : "border-amber-500/70"
              }`}
            />
          </div>
        )}
      </div>
    </div>
  );

  return (
    <aside className="space-y-4 lg:sticky lg:top-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
        {/* Chapter switcher + Seed Pinning */}
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={goPrevChapter}
              disabled={chapters.length <= 1}
              title="Previous chapter (Left Arrow)"
              aria-label="Go to previous chapter"
              className="border border-slate-300 hover:bg-slate-50 disabled:opacity-40 p-1.5 rounded"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <select
              aria-label="Active Chapter"
              value={activeCollectionId || ""}
              onChange={(e) => setActiveCollectionId(Number(e.target.value) || null)}
              className="border border-slate-300 rounded px-2.5 py-1 text-xs font-medium max-w-[200px]"
            >
              {chapters.length === 0 ? (
                <option value="">No chapters imported yet</option>
              ) : (
                chapters.map((ch, idx) => (
                  <option key={ch.id} value={ch.id}>
                    {idx + 1}. {ch.name} ({ch.word_count})
                  </option>
                ))
              )}
            </select>
            <button
              type="button"
              onClick={goNextChapter}
              disabled={chapters.length <= 1}
              title="Next chapter (Right Arrow)"
              aria-label="Go to next chapter"
              className="border border-slate-300 hover:bg-slate-50 disabled:opacity-40 p-1.5 rounded"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            {activeChapter && <StatusBadge status={activeChapter.status} />}
          </div>

          <div className="flex items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => {
                if (!seedPinned && puzzle?.winning_seed !== undefined && puzzle?.winning_seed !== null) {
                  setSeed(Number(puzzle.winning_seed));
                }
                setSeedPinned((v) => !v);
              }}
              title="Pin current seed so chapter regeneration stays reproducible"
              className={`px-2 py-1 rounded border flex items-center gap-1 font-medium ${
                seedPinned
                  ? "bg-amber-50 border-amber-300 text-amber-900"
                  : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            >
              {seedPinned ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
              {seedPinned ? `Seed ${seed} Pinned` : "Pin Seed"}
            </button>
          </div>
        </div>

        {/* View Toggle + Zoom + Margin Guides */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex gap-1">
            {(
              [
                ["puzzle", "Puzzle"],
                ["answer_key", "Answer Key"],
                ["side_by_side", "Side by Side"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setPreviewMode(k)}
                className={`px-2.5 py-1 rounded font-medium ${
                  previewMode === k
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={showMarginGuides}
                onChange={(e) => setShowMarginGuides(e.target.checked)}
              />
              Guides
              <Tooltip text="Shows printable margin and binding gutter boundaries on the live SVG page preview." />
            </label>

            <div className="flex items-center gap-1 border border-slate-200 rounded px-1.5 py-0.5 bg-slate-50">
              <button
                type="button"
                onClick={() => setPreviewZoom((z) => Math.max(50, z - 25))}
                aria-label="Zoom out"
                className="p-0.5 text-slate-600 hover:text-slate-900"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <input
                type="range"
                aria-label="Preview zoom"
                min={50}
                max={200}
                step={10}
                value={previewZoom}
                onChange={(e) => setPreviewZoom(Number(e.target.value))}
                className="w-16"
              />
              <span className="font-mono w-9 text-right">{previewZoom}%</span>
              <button
                type="button"
                onClick={() => setPreviewZoom((z) => Math.min(200, z + 25))}
                aria-label="Zoom in"
                className="p-0.5 text-slate-600 hover:text-slate-900"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* SVG Viewport */}
        {!activeChapter ? (
          <div className="border-2 border-dashed border-slate-200 rounded-lg p-10 text-center text-xs text-slate-500">
            Import a word list in Section B to preview chapters here.
          </div>
        ) : !puzzle ? (
          <div className="border border-slate-200 rounded-lg bg-slate-50 p-8 text-center space-y-3">
            <p className="text-xs text-slate-600">
              Chapter <b>{activeChapter.name}</b> ({activeChapter.word_count} words) does not have a generated grid yet.
            </p>
            <button
              type="button"
              onClick={() => handleGenerateChapterPuzzle()}
              disabled={generatingPuzzle}
              className="bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-medium px-4 py-2 rounded-lg inline-flex items-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              {generatingPuzzle ? "Generating Grid..." : "Generate Live Preview Grid"}
            </button>
          </div>
        ) : (
          <div className="border border-slate-200 rounded-lg bg-slate-100 p-4 overflow-auto max-h-[min(540px,max(260px,calc(100vh-16rem)))]">
            <div className="flex flex-wrap justify-center gap-4">
              {(previewMode === "puzzle" || previewMode === "side_by_side") &&
                renderSvgCard(puzzleSvg, `Chapter ${activeChapterIndex + 1} Puzzle`)}
              {(previewMode === "answer_key" || previewMode === "side_by_side") &&
                renderSvgCard(
                  answerKeySvg,
                  solutionsPerPage > 1 ? `Answer Key (${solutionsPerPage}/page)` : "Answer Key"
                )}
            </div>
          </div>
        )}

        {/* Quick Single-Page Exports */}
        {puzzle && (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
            <span className="text-slate-500 flex items-center gap-1.5">
              {previewLoading ? (
                <>
                  <RefreshCw className="w-3 h-3 animate-spin text-slate-600" />
                  <span>Updating preview...</span>
                </>
              ) : (
                "Server SVG matches print PDF output."
              )}
            </span>
            <div className="flex gap-1.5">
              {(["svg", "pdf", "png"] as const).map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  onClick={() =>
                    handleDownloadSinglePuzzle(
                      previewMode === "answer_key" ? "answer_key" : "puzzle_with_clues",
                      fmt
                    )
                  }
                  className="border border-slate-300 hover:bg-slate-50 px-2.5 py-1 rounded flex items-center gap-1 font-medium uppercase"
                >
                  <Download className="w-3 h-3" /> {fmt}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Chapter Validation, Needs-Attention Actions & Advanced Toggle */}
      {puzzle && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {!puzzle.needs_attention && puzzle.validation?.valid ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span className="text-emerald-700">Valid crossword grid</span>
                </>
              ) : (
                <>
                  <AlertTriangle className="w-4 h-4 text-red-600" />
                  <span className="text-red-700">
                    {puzzle.quality_status || "Needs attention"}
                  </span>
                </>
              )}
            </div>
            <div className="text-xs text-slate-600 flex flex-wrap gap-3">
              <span>
                Grid: <b>{puzzle.rows}×{puzzle.cols}</b>
              </span>
              <span>
                Placed:{" "}
                <b>
                  {puzzle.entries?.length || 0} /{" "}
                  {(puzzle.entries?.length || 0) + (puzzle.unplaced?.length || 0)}
                </b>
              </span>
              <span>
                Density: <b>{Math.round((puzzle.quality?.density || 0) * 100)}%</b>
              </span>
              <span>
                Crossings: <b>{puzzle.quality?.crossing_count ?? 0}</b>
              </span>
              <span>
                Symmetry: <b>{Math.round((puzzle.stats?.symmetry_ratio || 0) * 100)}%</b>
              </span>
            </div>
          </div>

          {puzzle.plain_errors?.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs space-y-1 text-red-800">
              {puzzle.plain_errors.map((msg: string, idx: number) => (
                <div key={idx}>{msg}</div>
              ))}
            </div>
          )}

          {(puzzle.needs_attention || puzzle.unplaced?.length > 0) && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs space-y-2">
              <div className="font-semibold text-amber-900 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                Unplaced Words — Inline Recovery Actions
              </div>
              {(puzzle.unplaced || []).map((u: any, idx: number) => (
                <div
                  key={idx}
                  className="flex flex-wrap items-center justify-between gap-2 bg-white border border-amber-200 rounded px-2.5 py-1.5"
                >
                  <div className="text-amber-900">
                    <b>{u.answer}</b> — {u.reason}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="text"
                      placeholder="Replacement word"
                      value={unplacedEdits[u.answer] ?? ""}
                      onChange={(e) =>
                        setUnplacedEdits((prev) => ({
                          ...prev,
                          [u.answer]: e.target.value,
                        }))
                      }
                      className="w-28 border border-amber-300 rounded px-2 py-0.5 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        (unplacedEdits[u.answer] || "").trim() &&
                        handleInlineChapterAction({
                          action: "edit_word",
                          old_word: u.answer,
                          new_word: (unplacedEdits[u.answer] || "").trim(),
                        })
                      }
                      className="bg-slate-900 text-white px-2 py-0.5 rounded text-xs"
                    >
                      Edit Word
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        handleInlineChapterAction({
                          action: "remove_word",
                          old_word: u.answer,
                        })
                      }
                      className="bg-red-600 text-white px-2 py-0.5 rounded text-xs"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => handleInlineChapterAction({ action: "larger_grid" })}
                  className="bg-white border border-amber-300 text-amber-900 px-2.5 py-1 rounded text-xs font-medium"
                >
                  Use Larger Grid
                </button>
                <button
                  type="button"
                  onClick={() => handleInlineChapterAction({ action: "new_seed" })}
                  className="bg-amber-700 text-white px-2.5 py-1 rounded text-xs font-medium"
                >
                  Retry New Seed
                </button>
              </div>
            </div>
          )}

          {/* Advanced Toggle: seed, strategy, winning_seed, hit_time_limit & raw validator checks */}
          <div className="pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="text-xs font-medium text-slate-600 hover:text-slate-900 underline"
            >
              {showAdvanced ? "Hide Advanced" : "Advanced"}
            </button>

            {showAdvanced && (
              <div className="mt-3 space-y-3 text-xs border border-slate-200 rounded-lg p-3 bg-slate-50">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600 mb-1">
                      Placement Strategy
                    </label>
                    <select
                      value={strategy}
                      onChange={(e) => setStrategy(e.target.value as any)}
                      className="w-full border border-slate-300 rounded px-2 py-1 bg-white"
                    >
                      <option value="auto">Auto</option>
                      <option value="longest">Longest first</option>
                      <option value="crossable">Most crossable</option>
                      <option value="random">Random order</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600 mb-1">
                      Seed
                    </label>
                    <div className="flex gap-1.5">
                      <input
                        type="number"
                        value={seed}
                        onChange={(e) => setSeed(Number(e.target.value))}
                        className="w-full border border-slate-300 rounded px-2 py-1 bg-white"
                      />
                      <button
                        type="button"
                        onClick={() => handleGenerateChapterPuzzle(seed)}
                        title="Regenerate using this seed"
                        className="bg-slate-900 text-white px-2 rounded"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3 text-slate-600">
                  <span>
                    Winning seed: <b>{puzzle.winning_seed ?? puzzle.settings?.engine?.seed ?? 0}</b>
                  </span>
                  <span>
                    Winning strategy:{" "}
                    <b>{puzzle.winning_strategy ?? puzzle.settings?.engine?.strategy ?? "auto"}</b>
                  </span>
                  <span>
                    hit_time_limit: <b>{puzzle.hit_time_limit ? "true" : "false"}</b>
                  </span>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(
                    puzzle.diagnostics?.raw_checks || puzzle.validation?.checks || {}
                  ).map(([check, ok]) => (
                    <span
                      key={check}
                      className={`px-2 py-0.5 rounded font-mono text-[11px] ${
                        ok
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-red-50 text-red-700 border border-red-200"
                      }`}
                    >
                      {ok ? "✓" : "✗"} {check}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
