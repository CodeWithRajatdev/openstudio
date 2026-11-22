import { LivePreviewPane } from "../components/LivePreviewPane";
import { PageAndImportSections } from "../components/setup/PageAndImportSections";
import { CluesAndGridSections } from "../components/setup/CluesAndGridSections";
import { StylingSections } from "../components/setup/StylingSections";

export function SetupStep() {
  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-4">
        <h2 className="text-base font-semibold text-slate-900">
          Step 3: Puzzle Setup &amp; Live Book Preview
        </h2>
        <p className="text-xs text-slate-500">
          Configure page margins, word import, clues, grid, styling, solutions, and title on the left while previewing server-rendered SVGs on the right (use ←/→ keys to switch chapters).
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 lg:self-start space-y-3">
          <PageAndImportSections />
          <CluesAndGridSections />
          <StylingSections />
        </div>

        <div className="lg:col-span-5">
          <LivePreviewPane />
        </div>
      </div>
    </div>
  );
}
