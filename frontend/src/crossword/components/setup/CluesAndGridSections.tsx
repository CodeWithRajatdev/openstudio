import { useState } from "react";
import { Play, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useStudio } from "../../context/ProjectStudioContext";
import { CollapsibleSection } from "../CollapsibleSection";
import { StatusBadge } from "../StatusBadge";
import { Tooltip } from "../Tooltip";

export function CluesAndGridSections() {
  const {
    activeCollectionId,
    clueMode,
    setClueMode,
    difficulty,
    setDifficulty,
    verifyClues,
    setVerifyClues,
    requireAllCluesApproved,
    setRequireAllCluesApproved,
    activeClueJob,
    clueSummary,
    clueStatusFilter,
    setClueStatusFilter,
    clueAltsByWord,
    editingWordId,
    setEditingWordId,
    editingClueText,
    setEditingClueText,
    blockingIssues,
    handleStartClueGen,
    handleBulkApprove,
    handleSaveManualClue,
    handleRegenerateSingleClue,
    handleSelectOrRestoreClue,
    gridMode,
    setGridMode,
    customRows,
    setCustomRows,
    customCols,
    setCustomCols,
    symmetry,
    setSymmetry,
    minWordLength,
    setMinWordLength,
    minDensity,
    setMinDensity,
    generatingPuzzle,
    puzzle,
    handleGenerateChapterPuzzle,
    handleEditEntryClue,
    handleRegeneratePuzzle,
  } = useStudio();

  const [editingEntryId, setEditingEntryId] = useState<number | null>(null);
  const [entryClueDraft, setEntryClueDraft] = useState("");
  const [newWordInput, setNewWordInput] = useState("");
  const [newWordClue, setNewWordClue] = useState("");
  const [replaceOld, setReplaceOld] = useState("");
  const [replaceNew, setReplaceNew] = useState("");
  const [replaceClue, setReplaceClue] = useState("");

  const missingClueIssues = blockingIssues.filter((b) => b.type === "missing_clues");

  return (
    <>
      {/* SECTION C: CLUES */}
      <CollapsibleSection
        letter="C"
        title="Clues & Per-Chapter Review"
        subtitle="Automatic/Manual/Hybrid mode, generation progress & clue approval"
        badge={
          clueSummary ? (
            <StatusBadge status={clueSummary.clue_status || "incomplete"} />
          ) : undefined
        }
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Clue Mode
              <Tooltip text="Hybrid keeps manual/imported clues and generates missing ones. Manual never generates. Automatic uses generated clues only." />
            </label>
            <select
              value={clueMode}
              onChange={(e) => setClueMode(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
            >
              <option value="hybrid">Hybrid (Keep mine + generate missing)</option>
              <option value="automatic">Automatic (Generated only)</option>
              <option value="manual">Manual (Mine only)</option>
            </select>
          </div>

          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Difficulty
              <Tooltip text="Adjusts clue phrasing complexity and word-count guidelines." />
            </label>
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-2 bg-white"
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-5 text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={verifyClues}
              onChange={(e) => setVerifyClues(e.target.checked)}
            />
            Reverse-solve AI verification
            <Tooltip text="AI clues only auto-approve when a blind reverse-solve recovers the original word." />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={requireAllCluesApproved}
              onChange={(e) => setRequireAllCluesApproved(e.target.checked)}
            />
            Require all clues approved
            <Tooltip text="Turns 'needs_review' dictionary clues from warnings into Download blockers in Step 4." />
          </label>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          <button
            type="button"
            onClick={() => handleStartClueGen(false)}
            disabled={clueMode === "manual" || !activeCollectionId}
            className="bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white font-medium px-3.5 py-2 rounded-lg flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" /> Generate Missing Clues
          </button>
          <button
            type="button"
            onClick={handleBulkApprove}
            disabled={!activeCollectionId}
            className="border border-slate-300 hover:bg-slate-50 disabled:opacity-40 text-slate-700 font-medium px-3 py-2 rounded-lg"
          >
            Approve All Needs Review
          </button>
        </div>

        {activeClueJob && (
          <div className="bg-slate-900 text-white rounded-lg p-3 space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="font-semibold">
                Clue Job ({activeClueJob.status})
              </span>
              <span>
                {activeClueJob.completed} / {activeClueJob.total}
              </span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-emerald-500 h-1.5 transition-all"
                style={{
                  width: `${Math.min(
                    100,
                    Math.round(
                      (activeClueJob.completed / Math.max(1, activeClueJob.total)) * 100
                    )
                  )}%`,
                }}
              />
            </div>
          </div>
        )}

        {missingClueIssues.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-800 space-y-1">
            {missingClueIssues.map((b, idx) => (
              <div key={idx}>{b.message}</div>
            ))}
          </div>
        )}

        {clueSummary ? (
          <div className="border border-slate-200 rounded-lg overflow-hidden text-xs">
            <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-2">
              <span className="font-semibold text-slate-800">
                {clueSummary.collection_name}: {clueSummary.covered_words}/{clueSummary.total_words} clues
              </span>
              <select
                value={clueStatusFilter}
                onChange={(e) => setClueStatusFilter(e.target.value as any)}
                className="border border-slate-300 rounded px-2 py-1 bg-white"
              >
                <option value="all">All statuses</option>
                <option value="needs_review">Needs review</option>
                <option value="approved">Approved</option>
                <option value="missing">Missing clues</option>
              </select>
            </div>
            <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
              {clueSummary.items
                .filter((item: any) => {
                  if (clueStatusFilter === "missing") return !item.active_clue;
                  if (clueStatusFilter === "needs_review") return item.active_clue?.status === "needs_review";
                  if (clueStatusFilter === "approved") return item.active_clue?.status === "approved";
                  return true;
                })
                .map((item: any) => {
                  const alts = clueAltsByWord[item.word_id] || [];
                  return (
                    <div key={item.word_id} className="p-2.5 space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <span className="font-mono font-bold text-slate-900">
                            {item.answer}
                          </span>
                          <span className="ml-2 text-slate-500">
                            {item.display} {item.enumeration}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {item.active_clue && (
                            <StatusBadge status={item.active_clue.status} />
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              setEditingWordId(item.word_id);
                              setEditingClueText(item.active_clue?.text || "");
                            }}
                            className="text-slate-600 hover:text-slate-900 underline"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRegenerateSingleClue(item.word_id)}
                            className="text-blue-600 hover:text-blue-800 underline"
                          >
                            Regenerate
                          </button>
                        </div>
                      </div>

                      {editingWordId === item.word_id ? (
                        <div className="flex gap-1.5">
                          <input
                            type="text"
                            autoFocus
                            value={editingClueText}
                            onChange={(e) => setEditingClueText(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === "Tab") {
                                e.preventDefault();
                                handleSaveManualClue(item.word_id, true);
                              } else if (e.key === "Escape") {
                                setEditingWordId(null);
                                setEditingClueText("");
                              }
                            }}
                            className="flex-1 border border-slate-300 rounded px-2 py-1"
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveManualClue(item.word_id, false)}
                            className="bg-emerald-600 text-white px-2.5 py-1 rounded"
                          >
                            Save
                          </button>
                        </div>
                      ) : (
                        <div className="text-slate-600">
                          {item.rendered_preview || item.active_clue?.text || (
                            <span className="text-red-600 italic">Missing clue</span>
                          )}
                        </div>
                      )}

                      {alts.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {alts.map((alt: any) => (
                            <button
                              key={alt.id}
                              type="button"
                              onClick={() => handleSelectOrRestoreClue(item.word_id, alt.id)}
                              className="bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 px-2 py-0.5 rounded text-[11px]"
                            >
                              {alt.text}
                            </button>
                          ))}
                        </div>
                      )}

                      {item.all_clues?.length > 1 && (
                        <select
                          value=""
                          onChange={(e) => {
                            const cid = Number(e.target.value);
                            if (cid) handleSelectOrRestoreClue(item.word_id, cid);
                          }}
                          className="border border-slate-200 rounded px-1.5 py-0.5 text-[11px] text-slate-600"
                        >
                          <option value="">History ({item.all_clues.length}) — Restore...</option>
                          {item.all_clues.map((hist: any) => (
                            <option key={hist.id} value={hist.id}>
                              [{hist.source}] {hist.text.slice(0, 42)}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-500">
            Select or import a chapter in Section B to review its clues.
          </div>
        )}
      </CollapsibleSection>

      {/* SECTION D: GRID */}
      <CollapsibleSection
        letter="D"
        title="Grid & Words"
        subtitle="Dimensions, symmetry, min length, quality threshold & placed words"
        badge={
          puzzle ? (
            <span className="text-xs text-slate-500">
              {puzzle.rows}×{puzzle.cols}
            </span>
          ) : undefined
        }
        defaultOpen={false}
      >
        <div className="space-y-3 text-xs">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={gridMode === "auto"}
                onChange={() => setGridMode("auto")}
              />
              Automatic grid sizing
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={gridMode === "custom"}
                onChange={() => setGridMode("custom")}
              />
              Custom rows × cols
            </label>
          </div>

          {gridMode === "custom" && (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={5}
                max={50}
                value={customRows}
                onChange={(e) => setCustomRows(Number(e.target.value))}
                className="w-20 border border-slate-300 rounded px-2 py-1"
              />
              <span>×</span>
              <input
                type="number"
                min={5}
                max={50}
                value={customCols}
                onChange={(e) => setCustomCols(Number(e.target.value))}
                className="w-20 border border-slate-300 rounded px-2 py-1"
              />
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block font-medium text-slate-700 mb-1">
                Symmetry
                <Tooltip text="Best-effort 180° rotational symmetry without adding filler words." />
              </label>
              <select
                value={symmetry}
                onChange={(e) => setSymmetry(e.target.value as any)}
                className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
              >
                <option value="off">Off</option>
                <option value="preferred">Preferred</option>
              </select>
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">
                Min Entry Length
                <Tooltip text="Words shorter than this normalized letter count are skipped during import/generation." />
              </label>
              <input
                type="number"
                min={2}
                max={10}
                value={minWordLength}
                onChange={(e) => setMinWordLength(Math.max(2, Number(e.target.value)))}
                className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">
                Min Density ({Math.round(minDensity * 100)}%)
                <Tooltip text="Grids below this letter-to-cell ratio trigger automatic seed/strategy retries." />
              </label>
              <input
                type="number"
                step={0.05}
                min={0}
                max={0.95}
                value={minDensity}
                onChange={(e) =>
                  setMinDensity(Math.max(0, Math.min(0.95, Number(e.target.value))))
                }
                className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => handleGenerateChapterPuzzle()}
            disabled={generatingPuzzle || !activeCollectionId}
            className="bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white font-medium px-3.5 py-2 rounded-lg flex items-center gap-1.5"
          >
            <Play className="w-3.5 h-3.5" />
            {generatingPuzzle ? "Generating Chapter Grid..." : "Generate / Refresh Chapter Grid"}
          </button>

          {puzzle && (
            <div className="border-t border-slate-200 pt-3 space-y-3">
              <div className="font-semibold text-slate-800">
                Placed Entries ({puzzle.entries?.length || 0})
              </div>
              <div className="max-h-48 overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-lg">
                {(puzzle.entries || []).map((e: any) => (
                  <div key={e.id} className="p-2 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-slate-800">
                        {e.number}
                        {e.direction}. {e.answer} ({e.length})
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingEntryId(e.id);
                            setEntryClueDraft(e.clue || "");
                          }}
                          className="text-blue-600 hover:underline"
                        >
                          Edit Clue
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            handleRegeneratePuzzle({ remove_words: [e.answer] })
                          }
                          title="Remove word and regenerate"
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    {editingEntryId === e.id ? (
                      <div className="flex gap-1.5">
                        <input
                          type="text"
                          value={entryClueDraft}
                          onChange={(ev) => setEntryClueDraft(ev.target.value)}
                          className="flex-1 border border-slate-300 rounded px-2 py-0.5"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            handleEditEntryClue(e.id, entryClueDraft);
                            setEditingEntryId(null);
                          }}
                          className="bg-emerald-600 text-white px-2 py-0.5 rounded"
                        >
                          Save
                        </button>
                      </div>
                    ) : (
                      <div className="text-slate-600">{e.clue || "Missing clue"}</div>
                    )}
                  </div>
                ))}
              </div>

              {/* Add / Replace Word */}
              <div className="grid grid-cols-1 gap-2 bg-slate-50 border border-slate-200 rounded-lg p-3">
                <div className="flex gap-1.5">
                  <input
                    type="text"
                    placeholder="Add word"
                    value={newWordInput}
                    onChange={(e) => setNewWordInput(e.target.value)}
                    className="w-28 border border-slate-300 rounded px-2 py-1 bg-white"
                  />
                  <input
                    type="text"
                    placeholder="Optional clue"
                    value={newWordClue}
                    onChange={(e) => setNewWordClue(e.target.value)}
                    className="flex-1 border border-slate-300 rounded px-2 py-1 bg-white"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (!newWordInput.trim()) return;
                      handleRegeneratePuzzle({
                        add_words: [
                          { word: newWordInput.trim(), clue: newWordClue.trim() || null },
                        ],
                      });
                      setNewWordInput("");
                      setNewWordClue("");
                    }}
                    className="bg-slate-900 text-white px-2.5 py-1 rounded flex items-center gap-1"
                  >
                    <Plus className="w-3 h-3" /> Add
                  </button>
                </div>

                <div className="flex gap-1.5">
                  <input
                    type="text"
                    placeholder="Old word"
                    value={replaceOld}
                    onChange={(e) => setReplaceOld(e.target.value)}
                    className="w-24 border border-slate-300 rounded px-2 py-1 bg-white"
                  />
                  <input
                    type="text"
                    placeholder="New word"
                    value={replaceNew}
                    onChange={(e) => setReplaceNew(e.target.value)}
                    className="w-24 border border-slate-300 rounded px-2 py-1 bg-white"
                  />
                  <input
                    type="text"
                    placeholder="New clue"
                    value={replaceClue}
                    onChange={(e) => setReplaceClue(e.target.value)}
                    className="flex-1 border border-slate-300 rounded px-2 py-1 bg-white"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      if (!replaceOld.trim() || !replaceNew.trim()) return;
                      handleRegeneratePuzzle({
                        replace_words: [
                          {
                            old: replaceOld.trim(),
                            new: replaceNew.trim(),
                            clue: replaceClue.trim() || null,
                          },
                        ],
                      });
                      setReplaceOld("");
                      setReplaceNew("");
                      setReplaceClue("");
                    }}
                    className="bg-slate-900 text-white px-2.5 py-1 rounded flex items-center gap-1"
                  >
                    <RefreshCw className="w-3 h-3" /> Replace
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </CollapsibleSection>
    </>
  );
}
