import { CheckCircle2, Grid, Undo2 } from "lucide-react";
import { StudioStep } from "../hooks/useProjectStudio";
import { useStudio } from "../context/ProjectStudioContext";

const STEP_META: Array<{ id: StudioStep; title: string }> = [
  { id: 1, title: "1. Project" },
  { id: 2, title: "2. Trim Size" },
  { id: 3, title: "3. Puzzle Setup" },
  { id: 4, title: "4. Review & Download" },
];

export function StudioHeader() {
  const {
    step,
    setStep,
    canGoToStep,
    projectName,
    autosaveStatus,
    autosavedAt,
    undoStack,
    handleUndo,
  } = useStudio();

  const autosaveLabel =
    autosaveStatus === "saving"
      ? "Saving..."
      : autosaveStatus === "error"
      ? "Save failed — will retry"
      : autosavedAt
      ? `Autosaved ${new Date(autosavedAt).toLocaleTimeString()}`
      : "Autosave ready";

  return (
    <header className="bg-slate-900 text-white border-b border-slate-800 px-6 py-3.5 space-y-3">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Grid className="w-7 h-7 text-amber-400 shrink-0" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              Openstudio — Crossword Studio
            </h1>
            <p className="text-xs text-slate-400">
              Book Project: <span className="text-slate-200 font-medium">{projectName || "Untitled"}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {undoStack.length > 0 && (
            <button
              type="button"
              onClick={handleUndo}
              title={`Undo ${undoStack[0].label}`}
              className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5"
            >
              <Undo2 className="w-3.5 h-3.5" />
              Undo {undoStack[0].label}
            </button>
          )}

          <span
            data-testid="autosave-indicator"
            className={`px-2.5 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1.5 ${
              autosaveStatus === "saving"
                ? "bg-amber-900/60 text-amber-200"
                : autosaveStatus === "error"
                ? "bg-red-900/60 text-red-200"
                : "bg-emerald-900/60 text-emerald-200"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            {autosaveLabel}
          </span>

          <span className="bg-slate-800 border border-slate-700 px-3 py-1 rounded-full text-xs font-semibold text-amber-300">
            Step {step} of 4
          </span>
        </div>
      </div>

      {/* Linear guarded 4-step counter */}
      <nav aria-label="Book creation steps" className="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto pb-0.5">
        {STEP_META.map((item) => {
          const active = step === item.id;
          const reachable = canGoToStep(item.id);
          return (
            <button
              key={item.id}
              type="button"
              disabled={!reachable}
              onClick={() => setStep(item.id)}
              title={
                reachable
                  ? `Go to ${item.title}`
                  : "Complete earlier required fields before opening this step"
              }
              className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
                active
                  ? "bg-amber-400 text-slate-950 font-semibold shadow-sm"
                  : reachable
                  ? "bg-slate-800 text-slate-200 hover:bg-slate-700"
                  : "bg-slate-800/40 text-slate-500 cursor-not-allowed opacity-50"
              }`}
            >
              {item.title}
            </button>
          );
        })}
      </nav>
    </header>
  );
}
