import { useEffect } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, XCircle } from "lucide-react";
import { ProjectStudioProvider, useStudio } from "./context/ProjectStudioContext";
import { StudioHeader } from "./components/StudioHeader";
import { StudioStep } from "./hooks/useProjectStudio";
import { ProjectStep } from "./steps/ProjectStep";
import { TrimSizeStep } from "./steps/TrimSizeStep";
import { SetupStep } from "./steps/SetupStep";
import { ReviewStep } from "./steps/ReviewStep";

function BookStudioShell() {
  const {
    step,
    setStep,
    canGoToStep,
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

  const nextStep = (step < 4 ? ((step + 1) as StudioStep) : null);
  const prevStep = (step > 1 ? ((step - 1) as StudioStep) : null);

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 text-slate-900">
      <StudioHeader />

      {/* Plain-language Error & Notice Banners */}
      {error && (
        <div
          role="alert"
          className="max-w-7xl w-full mx-auto px-6 pt-4"
        >
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

      {/* Active Step Screen (No Sidebar, No Dashboard) */}
      <main className="flex-1 px-6 py-6 w-full">
        {step === 1 && <ProjectStep />}
        {step === 2 && <TrimSizeStep />}
        {step === 3 && <SetupStep />}
        {step === 4 && <ReviewStep />}
      </main>

      {/* Bottom Linear Navigation Bar */}
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
  return (
    <ProjectStudioProvider>
      <BookStudioShell />
    </ProjectStudioProvider>
  );
}
