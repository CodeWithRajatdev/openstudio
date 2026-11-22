import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Grid,
  Grid3x3,
  Layers,
  Undo2,
  XCircle,
} from "lucide-react";

import { AppProvider, useApp } from "./wordsearch/store.jsx";
import WordSearchStepper from "./wordsearch/components/Stepper.jsx";
import { Step2TrimSize as WordSearchTrimSize } from "./wordsearch/components/Wizard.jsx";
import WordSearchSettings from "./wordsearch/pages/PuzzleSettings.jsx";
import WordSearchReview from "./wordsearch/pages/ReviewProject.jsx";
import { Button as WsButton, Field as WsField, TextInput as WsTextInput } from "./wordsearch/components/ui.jsx";

import { ProjectStudioProvider, useStudio } from "./crossword/context/ProjectStudioContext";
import { StudioStep } from "./crossword/hooks/useProjectStudio";
import { ProjectStep as CrosswordProjectStep } from "./crossword/steps/ProjectStep";
import { TrimSizeStep as CrosswordTrimSize } from "./crossword/steps/TrimSizeStep";
import { SetupStep as CrosswordSetup } from "./crossword/steps/SetupStep";
import { ReviewStep as CrosswordReview } from "./crossword/steps/ReviewStep";

export type StudioMode = "wordsearch" | "crossword";

const CW_STEP_META: Array<{ id: StudioStep; title: string }> = [
  { id: 1, title: "1. Project" },
  { id: 2, title: "2. Trim Size" },
  { id: 3, title: "3. Puzzle Setup" },
  { id: 4, title: "4. Review & Download" },
];

function StudioTypePicker({
  mode,
  onSelect,
}: {
  mode: StudioMode;
  onSelect: (m: StudioMode) => void;
}) {
  return (
    <div className="mb-8">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">
        What are you creating?
      </h1>
      <p className="mt-1 text-slate-500">
        Choose a puzzle studio in Openstudio and configure your book project.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          data-testid="studio-card-wordsearch"
          onClick={() => onSelect("wordsearch")}
          aria-pressed={mode === "wordsearch"}
          className={`relative rounded-2xl border-2 bg-white p-5 text-left transition ${
            mode === "wordsearch"
              ? "border-indigo-500 shadow-sm ring-4 ring-indigo-100"
              : "border-slate-200 hover:border-slate-300"
          }`}
        >
          {mode === "wordsearch" && (
            <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-white">
              <Check size={14} />
            </span>
          )}
          <Grid3x3
            className={mode === "wordsearch" ? "text-indigo-600" : "text-slate-400"}
            size={32}
          />
          <div className="mt-4 text-lg font-bold text-slate-900">Word Search</div>
          <p className="mt-1 text-sm text-slate-500">
            Chapter-based word-search puzzle books with customizable grids, clues, and solution pages.
          </p>
        </button>

        <button
          type="button"
          data-testid="studio-card-crossword"
          onClick={() => onSelect("crossword")}
          aria-pressed={mode === "crossword"}
          className={`relative rounded-2xl border-2 bg-white p-5 text-left transition ${
            mode === "crossword"
              ? "border-amber-500 shadow-sm ring-4 ring-amber-100"
              : "border-slate-200 hover:border-slate-300"
          }`}
        >
          {mode === "crossword" && (
            <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-amber-500 text-white">
              <Check size={14} />
            </span>
          )}
          <Grid
            className={mode === "crossword" ? "text-amber-500" : "text-slate-400"}
            size={32}
          />
          <div className="mt-4 text-lg font-bold text-slate-900">Crossword</div>
          <p className="mt-1 text-sm text-slate-500">
            Interconnected crossword books with WordNet/AI clue authoring, quality checks, and a saved project library.
          </p>
        </button>
      </div>
    </div>
  );
}

function WordSearchShell({
  mode,
  onSelectMode,
}: {
  mode: StudioMode;
  onSelectMode: (m: StudioMode) => void;
}) {
  const { state: s, patch, goStep, dispatch } = useApp() as any;
  const step = s.step || 1;

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <header className="bg-slate-900 text-white border-b border-slate-800 px-6 py-3.5">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => goStep(1)}
            className="flex items-center gap-3 text-left group"
          >
            <Layers className="w-7 h-7 text-indigo-400 shrink-0" />
            <div>
              <div className="text-lg font-bold tracking-tight leading-tight flex items-center gap-2">
                <span>Openstudio</span>
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-400/30">
                  Word Search
                </span>
              </div>
              <div className="text-xs text-slate-400">
                Project: <span className="text-slate-200 font-medium">{s.projectName}</span>
                {s.chapters.length > 0 && (
                  <span>
                    {" "}
                    · {s.chapters.length} chapters ·{" "}
                    {s.chapters.reduce((n: number, c: any) => n + c.words.length, 0)} words
                  </span>
                )}
              </div>
            </div>
          </button>

          <div className="flex items-center gap-3">
            {step > 1 && (
              <button
                type="button"
                onClick={() => goStep(1)}
                className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-200"
              >
                Switch Studio
              </button>
            )}
            <span className="bg-slate-800 border border-slate-700 px-3 py-1 rounded-full text-xs font-semibold text-indigo-300">
              Step {step} of 4
            </span>
          </div>
        </div>
      </header>

      <div className={`mx-auto w-full px-6 py-6 ${step === 3 ? "max-w-[1600px]" : "max-w-5xl"}`}>
        <WordSearchStepper current={step} />
        <main className="min-w-0">
          {step === 1 && (
            <section className="mx-auto max-w-3xl">
              <StudioTypePicker mode={mode} onSelect={onSelectMode} />

              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
                <div className="max-w-md">
                  <WsField
                    label="Project name"
                    hint="Used for the exported PDF file name (<project-name>.pdf)."
                  >
                    <WsTextInput
                      value={s.projectName === "Untitled project" ? "" : s.projectName}
                      placeholder="e.g. English Word Search Vol. 1"
                      onChange={(e: any) =>
                        patch({ projectName: e.target.value || "Untitled project" })
                      }
                    />
                  </WsField>
                </div>

                <div className="flex items-center justify-end pt-2">
                  <WsButton
                    icon={ArrowRight}
                    loading={false}
                    onClick={() => {
                      dispatch({ type: "setup", patch: { projectType: "word_search", step: 2 } });
                      goStep(2);
                    }}
                  >
                    Continue
                  </WsButton>
                </div>
              </div>
            </section>
          )}
          {step === 2 && <WordSearchTrimSize />}
          {step === 3 && <WordSearchSettings />}
          {step >= 4 && <WordSearchReview />}
        </main>
      </div>
    </div>
  );
}

function CrosswordShellInner({
  mode,
  onSelectMode,
}: {
  mode: StudioMode;
  onSelectMode: (m: StudioMode) => void;
}) {
  const {
    step,
    setStep,
    canGoToStep,
    projectName,
    autosaveStatus,
    autosavedAt,
    undoStack,
    handleUndo,
    error,
    setError,
    notice,
    setNotice,
    stagedBatch,
    handleAcceptImport,
    goPrevChapter,
    goNextChapter,
  } = useStudio();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toUpperCase() || "";
      const isEditingField =
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable;
      if (isEditingField) return;

      if (step === 3 && e.key === "ArrowLeft") {
        e.preventDefault();
        goPrevChapter();
      } else if (step === 3 && e.key === "ArrowRight") {
        e.preventDefault();
        goNextChapter();
      } else if (step === 3 && e.key === "Enter" && stagedBatch) {
        e.preventDefault();
        handleAcceptImport();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [step, stagedBatch, goPrevChapter, goNextChapter, handleAcceptImport]);

  const nextStep = step < 4 ? ((step + 1) as StudioStep) : null;
  const prevStep = step > 1 ? ((step - 1) as StudioStep) : null;

  const autosaveLabel =
    autosaveStatus === "saving"
      ? "Saving..."
      : autosaveStatus === "error"
      ? "Save failed — will retry"
      : autosavedAt
      ? `Autosaved ${new Date(autosavedAt).toLocaleTimeString()}`
      : "Autosave ready";

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 text-slate-900">
      <header className="bg-slate-900 text-white border-b border-slate-800 px-6 py-3.5 space-y-3">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => setStep(1)}
            className="flex items-center gap-3 text-left"
          >
            <Layers className="w-7 h-7 text-amber-400 shrink-0" />
            <div>
              <h1 className="text-lg font-bold tracking-tight flex items-center gap-2">
                <span>Openstudio</span>
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-400/30">
                  Crossword
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Book Project:{" "}
                <span className="text-slate-200 font-medium">{projectName || "Untitled"}</span>
              </p>
            </div>
          </button>

          <div className="flex items-center gap-3">
            {step > 1 && (
              <button
                type="button"
                onClick={() => setStep(1)}
                className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-200"
              >
                Switch Studio
              </button>
            )}

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

        <nav
          aria-label="Book creation steps"
          className="max-w-7xl mx-auto flex items-center gap-2 overflow-x-auto pb-0.5"
        >
          {CW_STEP_META.map((item) => {
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

      {error && (
        <div role="alert" className="max-w-7xl w-full mx-auto px-6 pt-4">
          <div className="bg-red-50 border border-red-200 text-red-900 px-4 py-3 rounded-xl flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-red-600 shrink-0" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-xs font-medium underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {notice && (
        <div className="max-w-7xl w-full mx-auto px-6 pt-3">
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 px-4 py-2.5 rounded-xl flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{notice}</span>
            </div>
            <button
              type="button"
              onClick={() => setNotice(null)}
              className="font-medium underline"
            >
              Close
            </button>
          </div>
        </div>
      )}

      <main className="flex-1 px-6 py-6 w-full">
        {step === 1 && (
          <div className="max-w-4xl mx-auto">
            <StudioTypePicker mode={mode} onSelect={onSelectMode} />
            <CrosswordProjectStep />
          </div>
        )}
        {step === 2 && <CrosswordTrimSize />}
        {step === 3 && <CrosswordSetup />}
        {step === 4 && <CrosswordReview />}
      </main>

      <footer className="bg-white border-t border-slate-200 px-6 py-3.5">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <button
            type="button"
            disabled={!prevStep}
            onClick={() => prevStep && setStep(prevStep)}
            className="border border-slate-300 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-slate-700 text-sm font-medium px-4 py-2 rounded-lg inline-flex items-center gap-1.5"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>

          <button
            type="button"
            disabled={!nextStep || !canGoToStep(nextStep)}
            onClick={() => nextStep && setStep(nextStep)}
            className="bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed text-white text-sm font-medium px-5 py-2 rounded-lg inline-flex items-center gap-1.5 shadow-sm transition"
          >
            Next <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </footer>
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState<StudioMode>("wordsearch");

  if (mode === "crossword") {
    return (
      <ProjectStudioProvider>
        <CrosswordShellInner mode={mode} onSelectMode={setMode} />
      </ProjectStudioProvider>
    );
  }

  return (
    <AppProvider>
      <WordSearchShell mode={mode} onSelectMode={setMode} />
    </AppProvider>
  );
}
