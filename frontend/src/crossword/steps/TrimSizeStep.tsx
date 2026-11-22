import { AlertTriangle, CheckCircle2, Ruler } from "lucide-react";
import { useStudio } from "../context/ProjectStudioContext";
import { Tooltip } from "../components/Tooltip";
import { TRIM_PRESETS, TrimUnit } from "../utils/trimSize";

export function TrimSizeStep() {
  const {
    projectTrimSize,
    setProjectTrimSize,
    customWidth,
    setCustomWidth,
    customHeight,
    setCustomHeight,
    customUnit,
    setCustomUnit,
    trimValidation,
  } = useStudio();

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-5">
        <div>
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <Ruler className="w-4 h-4 text-slate-700" />
            Step 2: Trim Size &amp; Page Dimensions
            <Tooltip
              label="Trim Size"
              text="Sets the physical book trim dimensions for puzzle geometry, PDF pagination, and KDP/print verification."
            />
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Select a standard publishing trim size or enter custom dimensions in inches, millimeters, or centimeters.
          </p>
        </div>

        {/* Standard Presets + Custom Toggle */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {TRIM_PRESETS.map((preset) => {
            const active = projectTrimSize === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => setProjectTrimSize(preset.id)}
                className={`text-left p-4 rounded-xl border transition space-y-1 ${
                  active
                    ? "border-slate-900 bg-slate-900 text-white shadow-sm"
                    : "border-slate-200 bg-white hover:border-slate-400 text-slate-900"
                }`}
              >
                <div className="text-sm font-semibold">{preset.label}</div>
                <div
                  className={`text-xs ${
                    active ? "text-slate-300" : "text-slate-500"
                  }`}
                >
                  {preset.subtitle}
                </div>
                <div
                  className={`text-[11px] font-mono pt-1 ${
                    active ? "text-amber-300" : "text-slate-400"
                  }`}
                >
                  {preset.widthIn.toFixed(2)}×{preset.heightIn.toFixed(2)} in ({preset.widthMm}×{preset.heightMm} mm)
                </div>
              </button>
            );
          })}

          <button
            type="button"
            onClick={() => setProjectTrimSize("custom")}
            className={`text-left p-4 rounded-xl border transition space-y-1 ${
              projectTrimSize === "custom"
                ? "border-slate-900 bg-slate-900 text-white shadow-sm"
                : "border-slate-200 bg-white hover:border-slate-400 text-slate-900"
            }`}
          >
            <div className="text-sm font-semibold">Custom Size</div>
            <div
              className={`text-xs ${
                projectTrimSize === "custom" ? "text-slate-300" : "text-slate-500"
              }`}
            >
              Specify exact width &amp; height in in, mm, or cm
            </div>
            <div
              className={`text-[11px] font-mono pt-1 ${
                projectTrimSize === "custom" ? "text-amber-300" : "text-slate-400"
              }`}
            >
              Range: 3.0–12.0 in
            </div>
          </button>
        </div>

        {/* Custom Size Inputs */}
        {projectTrimSize === "custom" && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div className="flex items-center mb-1">
                  <label
                    htmlFor="custom-trim-width"
                    className="text-xs font-medium text-slate-700"
                  >
                    Custom Width
                  </label>
                  <Tooltip
                    label="Custom Width"
                    text="Supported printable page width in your selected unit."
                  />
                </div>
                <input
                  id="custom-trim-width"
                  aria-label="Custom Width"
                  type="number"
                  step="0.01"
                  value={customWidth}
                  onChange={(e) => setCustomWidth(Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                />
              </div>

              <div>
                <div className="flex items-center mb-1">
                  <label
                    htmlFor="custom-trim-height"
                    className="text-xs font-medium text-slate-700"
                  >
                    Custom Height
                  </label>
                  <Tooltip
                    label="Custom Height"
                    text="Supported printable page height in your selected unit."
                  />
                </div>
                <input
                  id="custom-trim-height"
                  aria-label="Custom Height"
                  type="number"
                  step="0.01"
                  value={customHeight}
                  onChange={(e) => setCustomHeight(Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                />
              </div>

              <div>
                <div className="flex items-center mb-1">
                  <label
                    htmlFor="custom-trim-unit"
                    className="text-xs font-medium text-slate-700"
                  >
                    Dimension Unit
                  </label>
                  <Tooltip
                    label="Dimension Unit"
                    text="Changing the unit automatically converts your width and height."
                  />
                </div>
                <select
                  id="custom-trim-unit"
                  aria-label="Dimension Unit"
                  value={customUnit}
                  onChange={(e) => setCustomUnit(e.target.value as TrimUnit)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
                >
                  <option value="in">Inches (in)</option>
                  <option value="mm">Millimeters (mm)</option>
                  <option value="cm">Centimeters (cm)</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Live Conversion & Validation Summary */}
        {trimValidation.valid ? (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs text-emerald-900">
            <div className="flex items-center gap-2 font-medium">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              Valid trim size ready for page geometry &amp; print verification
            </div>
            <div className="font-mono flex flex-wrap gap-3">
              <span>{trimValidation.widthIn} × {trimValidation.heightIn} in</span>
              <span>•</span>
              <span>{trimValidation.widthMm} × {trimValidation.heightMm} mm</span>
              <span>•</span>
              <span>{trimValidation.widthCm} × {trimValidation.heightCm} cm</span>
              <span>•</span>
              <span>{trimValidation.widthPt} × {trimValidation.heightPt} pt</span>
            </div>
          </div>
        ) : (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-2 text-xs text-red-800 font-medium"
          >
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{trimValidation.error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
