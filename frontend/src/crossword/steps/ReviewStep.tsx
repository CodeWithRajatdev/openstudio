import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Download,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useStudio } from "../context/ProjectStudioContext";
import { StatusBadge } from "../components/StatusBadge";
import { Tooltip } from "../components/Tooltip";

export function ReviewStep() {
  const {
    projectName,
    projectTrimSize,
    trimValidation,
    chapters,
    wordsPerChapter,
    solutionsPerPage,
    startPuzzlesOnRightHandPage,
    showPageNumbers,
    bookPagePlan,
    blockingIssues,
    blockingWarnings,
    bookGenJob,
    retryingFailedChapters,
    bookPdfFilename,
    setStep,
    setActiveCollectionId,
    handleGenerateAndDownloadBook,
    handleDownloadVerifiedBookPdf,
    handleCancelBookJob,
    handleRetryFailedChapters,
    refreshProjectPlanAndIssues,
  } = useStudio();

  const isJobRunning =
    bookGenJob?.status === "pending" || bookGenJob?.status === "running";
  const hasBlocked = blockingIssues.length > 0 || chapters.length === 0;
  const hasFailedChapters =
    blockingIssues.some(
      (b) => b.type === "needs_attention" || b.type === "no_puzzle"
    ) ||
    bookGenJob?.status === "failed" ||
    (bookGenJob?.result?.failed_chapters?.length ?? 0) > 0;

  return (
    <div data-testid="review-step" className="max-w-5xl mx-auto space-y-6">
      {/* Book Summary Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-slate-700" />
              Step 4: Review &amp; Download Verified Book PDF
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Review all chapters, page plan pagination, and readiness checks before building your single print-ready PDF.
            </p>
          </div>
          <button
            type="button"
            onClick={() => refreshProjectPlanAndIssues()}
            className="border border-slate-300 hover:bg-slate-50 text-xs font-medium px-3 py-1.5 rounded-lg flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh Summary
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="text-slate-500">Project Name</div>
            <div className="font-semibold text-slate-900 truncate mt-0.5">
              {projectName}
            </div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="text-slate-500">Trim Size</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {projectTrimSize === "custom"
                ? `${trimValidation.widthIn}×${trimValidation.heightIn} in`
                : projectTrimSize}
            </div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="text-slate-500">Chapters</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {chapters.length}
            </div>
          </div>
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="text-slate-500">Target Words / Chapter</div>
            <div className="font-semibold text-slate-900 mt-0.5">
              {wordsPerChapter === null ? "Varies by chapter" : wordsPerChapter}
            </div>
          </div>
        </div>
      </div>

      {/* Per-Chapter Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-sm font-semibold">
          <span>Chapters Breakdown ({chapters.length})</span>
          <span className="text-xs font-normal text-slate-500">
            Click Inspect to fix words, clues, or grid settings in Step 3.
          </span>
        </div>

        {chapters.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No chapters found in this project. Return to Step 3 Section B to import words.
          </div>
        ) : (
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
              <tr>
                <th className="px-5 py-2.5">Chapter</th>
                <th className="px-5 py-2.5">Words</th>
                <th className="px-5 py-2.5">Chapter Status</th>
                <th className="px-5 py-2.5">Clue Status</th>
                <th className="px-5 py-2.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {chapters.map((ch) => (
                <tr key={ch.id} className="hover:bg-slate-50/70">
                  <td className="px-5 py-3 font-semibold text-slate-900">
                    {ch.name}
                  </td>
                  <td className="px-5 py-3 text-slate-600">
                    {ch.word_count_label || `${ch.word_count} words`}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge status={ch.status} />
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge
                      status={
                        ch.clue_status ||
                        ((ch as any).missing_clue_count === 0 && ch.word_count > 0
                          ? "complete"
                          : "incomplete")
                      }
                    />
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveCollectionId(ch.id);
                        setStep(3);
                      }}
                      className="text-blue-600 hover:underline font-medium"
                    >
                      Inspect in Step 3 →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Unified Page Plan */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-1">
            Book Page Plan
            <Tooltip
              label="Book Page Plan"
              text="Calculated directly from the PDF export geometry. Includes front/trailing blank pages when needed so books end on an even page count."
            />
          </h3>
          <div className="text-xs text-slate-500 flex flex-wrap gap-3">
            <span>Solutions/page: <b>{solutionsPerPage}</b></span>
            <span>Right-hand start: <b>{startPuzzlesOnRightHandPage ? "On" : "Off"}</b></span>
            <span>Page numbers: <b>{showPageNumbers ? "On" : "Off"}</b></span>
          </div>
        </div>

        {bookPagePlan ? (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-slate-800">
                {bookPagePlan.front_matter_blank_pages > 0 && (
                  <>
                    <b>{bookPagePlan.front_matter_blank_pages}</b> front blank +{" "}
                  </>
                )}
                <b>{bookPagePlan.puzzle_pages}</b> puzzle{" "}
                {bookPagePlan.puzzle_pages === 1 ? "page" : "pages"} +{" "}
                <b>{bookPagePlan.solution_pages}</b> solution{" "}
                {bookPagePlan.solution_pages === 1 ? "page" : "pages"} (
                {bookPagePlan.solutions_per_page}/page) +{" "}
                <b>{bookPagePlan.trailing_blank_pages}</b> trailing blank ={" "}
                <b className="text-sm text-slate-950">
                  {bookPagePlan.total_pages} TOTAL PAGES
                </b>
              </div>
              <span className="font-mono text-slate-500">
                {Math.round(bookPagePlan.width_pt)}×{Math.round(bookPagePlan.height_pt)} pt
              </span>
            </div>

            {bookPagePlan.chapters?.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-1.5 pt-2">
                {bookPagePlan.chapters.map((ch) => {
                  const endPage = Number(ch.start_page) + Number(ch.puzzle_pages || 0) - 1;
                  return (
                    <div
                      key={ch.chapter_id}
                      className="bg-white border border-slate-200 rounded px-2.5 py-1 flex justify-between"
                    >
                      <span className="truncate pr-2">{ch.chapter_name}</span>
                      <span className="font-mono shrink-0">
                        p.{ch.start_page}
                        {endPage > ch.start_page ? `–${endPage}` : ""} ({ch.puzzle_pages})
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-slate-500">
            Import chapters to calculate the exact page count.
          </p>
        )}
      </div>

      {/* Blocking Issues & Warnings */}
      {blockingIssues.length > 0 && (
        <div
          role="alert"
          className="bg-red-50 border border-red-200 rounded-xl p-4 text-xs text-red-900 space-y-1.5"
        >
          <div className="font-semibold flex items-center gap-1.5 text-sm">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            Resolve Blocking Issues Before Download ({blockingIssues.length})
          </div>
          {blockingIssues.map((issue, idx) => (
            <div key={idx}>{issue.message}</div>
          ))}
        </div>
      )}

      {blockingWarnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-900 space-y-1">
          <div className="font-semibold">Warnings (build allowed):</div>
          {blockingWarnings.map((w, idx) => (
            <div key={idx}>{w.message}</div>
          ))}
        </div>
      )}

      {/* Generate & Download Action + Background Job Progress */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={hasBlocked || retryingFailedChapters || isJobRunning}
            onClick={() => handleGenerateAndDownloadBook(false)}
            className="flex-1 min-w-[260px] bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed text-white font-semibold py-3 px-5 rounded-xl flex items-center justify-center gap-2 text-sm shadow-sm transition"
          >
            <Download className="w-4 h-4" />
            Generate and Download ({bookPdfFilename})
          </button>

          {hasFailedChapters && (
            <button
              type="button"
              onClick={handleRetryFailedChapters}
              disabled={retryingFailedChapters || isJobRunning}
              className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-medium py-3 px-4 rounded-xl flex items-center gap-2 text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              {retryingFailedChapters ? "Retrying..." : "Retry failed chapters"}
            </button>
          )}

          {bookGenJob?.status === "completed" && (
            <button
              type="button"
              onClick={() => handleDownloadVerifiedBookPdf()}
              className="border border-slate-300 hover:bg-slate-50 text-slate-800 font-medium py-3 px-4 rounded-xl flex items-center gap-2 text-sm"
            >
              <Download className="w-4 h-4" /> Download Again
            </button>
          )}
        </div>

        {bookGenJob && (
          <div className="bg-slate-900 text-white rounded-xl p-4 space-y-2.5 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-sm">
                Book Build Status: {bookGenJob.status}
              </span>
              <div className="flex items-center gap-3">
                <span className="text-slate-300">
                  Done: {bookGenJob.completed} • Failed: {bookGenJob.failed} • Remaining:{" "}
                  {bookGenJob.remaining ??
                    Math.max(
                      0,
                      bookGenJob.total - bookGenJob.completed - bookGenJob.failed
                    )}
                </span>
                {isJobRunning && (
                  <button
                    type="button"
                    onClick={handleCancelBookJob}
                    className="bg-red-600 hover:bg-red-700 text-white px-2.5 py-1 rounded flex items-center gap-1"
                  >
                    <XCircle className="w-3.5 h-3.5" /> Cancel
                  </button>
                )}
              </div>
            </div>

            <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
              <div
                className={`h-2 transition-all ${
                  bookGenJob.status === "failed"
                    ? "bg-red-500"
                    : bookGenJob.status === "cancelled"
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
                style={{
                  width: `${Math.min(
                    100,
                    Math.round(
                      ((bookGenJob.completed + bookGenJob.failed) /
                        Math.max(1, bookGenJob.total)) *
                        100
                    )
                  )}%`,
                }}
              />
            </div>

            {bookGenJob.error && (
              <div className="text-red-300 bg-red-950/60 border border-red-800 rounded p-2.5">
                {bookGenJob.error}
              </div>
            )}

            {bookGenJob.result?.verification?.valid && (
              <div className="text-emerald-300 flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                Verified PDF: {bookGenJob.result.verification.actual_pages} pages, zero raster images, vector paths present, all fonts embedded, no transparency.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
