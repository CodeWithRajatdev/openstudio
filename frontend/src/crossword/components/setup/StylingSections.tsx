import { useStudio } from "../../context/ProjectStudioContext";
import { CollapsibleSection } from "../CollapsibleSection";
import { Tooltip } from "../Tooltip";

export function StylingSections() {
  const {
    availableFonts,
    // Section E: Puzzle Appearance
    cellSize,
    setCellSize,
    lineWidth,
    setLineWidth,
    lineUnit,
    setLineUnit,
    outerBorder,
    setOuterBorder,
    borderLineWidth,
    setBorderLineWidth,
    cellFill,
    setCellFill,
    emptyCellStyle,
    setEmptyCellStyle,
    blockColor,
    setBlockColor,
    numberSize,
    setNumberSize,
    numberPosition,
    setNumberPosition,
    numberFont,
    setNumberFont,
    numberColor,
    setNumberColor,
    fontFamily,
    setFontFamily,
    capitalLetters,
    setCapitalLetters,
    // Section F: Clue Layout
    clueLayoutMode,
    setClueLayoutMode,
    clueHeadingStyle,
    setClueHeadingStyle,
    clueFontFamily,
    setClueFontFamily,
    clueFontSize,
    setClueFontSize,
    clueColor,
    setClueColor,
    clueSpacing,
    setClueSpacing,
    puzzleClueGap,
    setPuzzleClueGap,
    clueSort,
    setClueSort,
    showLengths,
    setShowLengths,
    enumerationDisplay,
    setEnumerationDisplay,
    clueCapitalization,
    setClueCapitalization,
    clueEndingPunct,
    setClueEndingPunct,
    cluePlacement,
    setCluePlacement,
    // Section G: Solution
    solutionsPerPage,
    setSolutionsPerPage,
    solutionTitleEnabled,
    setSolutionTitleEnabled,
    solutionTitleMode,
    setSolutionTitleMode,
    solutionTitleTemplate,
    setSolutionTitleTemplate,
    solutionTitleFontFamily,
    setSolutionTitleFontFamily,
    solutionTitleFontSize,
    setSolutionTitleFontSize,
    solutionTitleColor,
    setSolutionTitleColor,
    solutionTitleAlignment,
    setSolutionTitleAlignment,
    solutionTitleGap,
    setSolutionTitleGap,
    solutionHighlightStyle,
    setSolutionHighlightStyle,
    copyAppearanceFromPuzzle,
    setCopyAppearanceFromPuzzle,
    solutionFontFamily,
    setSolutionFontFamily,
    solutionFontSize,
    setSolutionFontSize,
    solutionColor,
    setSolutionColor,
    // Section H: Title
    titleEnabled,
    setTitleEnabled,
    titleMode,
    setTitleMode,
    titleTemplate,
    setTitleTemplate,
    titleStartNumber,
    setTitleStartNumber,
    titleFontFamily,
    setTitleFontFamily,
    titleFontSize,
    setTitleFontSize,
    titleColor,
    setTitleColor,
    titleAlignment,
    setTitleAlignment,
    titleGap,
    setTitleGap,
  } = useStudio();

  const renderFontSelect = (
    value: string,
    onChange: (val: string) => void,
    disabled = false
  ) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white disabled:bg-slate-100"
    >
      {availableFonts.map((f) => (
        <option key={f.family} value={f.family}>
          {f.label} ({f.license})
        </option>
      ))}
    </select>
  );

  return (
    <>
      {/* SECTION E: PUZZLE APPEARANCE */}
      <CollapsibleSection
        letter="E"
        title="Puzzle Appearance"
        subtitle="Cell size, line width, border, colors, numbers & embedded fonts"
        badge={<span className="text-xs text-slate-500">{fontFamily}</span>}
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Cell Size (pt)
              <Tooltip text="Target size per grid cell; scales to fit printable page margins." />
            </label>
            <input
              type="number"
              min={10}
              max={48}
              value={cellSize}
              onChange={(e) => setCellSize(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Line Width
              <Tooltip text="Grid cell stroke thickness, converted automatically to PDF points." />
            </label>
            <div className="flex gap-1.5">
              <input
                type="number"
                step={0.1}
                min={0.1}
                max={10}
                value={lineWidth}
                onChange={(e) => setLineWidth(Number(e.target.value))}
                className="flex-1 border border-slate-300 rounded-lg px-2 py-1.5"
              />
              <select
                value={lineUnit}
                onChange={(e) => setLineUnit(e.target.value as any)}
                className="border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
              >
                <option value="pt">pt</option>
                <option value="px">px</option>
                <option value="mm">mm</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Empty-Cell Style
              <Tooltip text="American crossword blocks fill unused cells solid; blank leaves them open." />
            </label>
            <select
              value={emptyCellStyle}
              onChange={(e) => setEmptyCellStyle(e.target.value as "black" | "blank")}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value="black">Black blocks</option>
              <option value="blank">Blank paper</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Grid Font (Embedded)
              <Tooltip text="Only verified embeddable TTF fonts are offered for KDP print safety." />
            </label>
            {renderFontSelect(fontFamily, setFontFamily)}
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Cell Fill</label>
            <input
              type="color"
              value={cellFill}
              onChange={(e) => setCellFill(e.target.value)}
              className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Block Fill</label>
            <input
              type="color"
              value={blockColor}
              onChange={(e) => setBlockColor(e.target.value)}
              className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">Number Size</label>
            <input
              type="number"
              step={0.5}
              min={4}
              max={16}
              value={numberSize}
              onChange={(e) => setNumberSize(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Number Pos</label>
            <select
              value={numberPosition}
              onChange={(e) => setNumberPosition(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
            >
              <option value="top_left">Top Left</option>
              <option value="top_right">Top Right</option>
              <option value="bottom_left">Bottom Left</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Number Font</label>
            {renderFontSelect(numberFont, setNumberFont)}
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Number Color</label>
            <input
              type="color"
              value={numberColor}
              onChange={(e) => setNumberColor(e.target.value)}
              className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-5 text-xs pt-1">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={outerBorder}
              onChange={(e) => setOuterBorder(e.target.checked)}
            />
            Outer Border ({borderLineWidth} pt)
          </label>
          {outerBorder && (
            <input
              type="number"
              step={0.25}
              min={0.5}
              max={8}
              aria-label="Outer border width"
              value={borderLineWidth}
              onChange={(e) => setBorderLineWidth(Number(e.target.value))}
              className="w-20 border border-slate-300 rounded px-2 py-1"
            />
          )}
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={capitalLetters}
              onChange={(e) => setCapitalLetters(e.target.checked)}
            />
            Capital letters in answer key
          </label>
        </div>
      </CollapsibleSection>

      {/* SECTION F: CLUE LAYOUT */}
      <CollapsibleSection
        letter="F"
        title="Clue Layout & Typography"
        subtitle="Placement (same page/facing), columns, headings & enumerations"
        badge={<span className="text-xs text-slate-500">{cluePlacement.replace("_", " ")}</span>}
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Grid-to-Clue Placement
              <Tooltip text="Default places the puzzle grid and clues together on the same page." />
            </label>
            <select
              value={cluePlacement}
              onChange={(e) => setCluePlacement(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value="same_page">Grid &amp; Clues on same page</option>
              <option value="beside">Clues beside grid</option>
              <option value="facing_page">Clues on facing page</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Clue Layout</label>
            <select
              value={clueLayoutMode}
              onChange={(e) => setClueLayoutMode(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value="columns">2 Columns</option>
              <option value="side_by_side">Side by Side (Across | Down)</option>
              <option value="rows">Single Column Rows</option>
              <option value="inline">Inline Flowing</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Across/Down Heading</label>
            <select
              value={clueHeadingStyle}
              onChange={(e) => setClueHeadingStyle(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value="uppercase">ACROSS / DOWN</option>
              <option value="title">Across / Down</option>
              <option value="bold">Bold Accent</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">Clue Font</label>
            {renderFontSelect(clueFontFamily, setClueFontFamily)}
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Clue Size (pt)</label>
            <input
              type="number"
              step={0.5}
              min={5}
              max={24}
              value={clueFontSize}
              onChange={(e) => setClueFontSize(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Spacing (pt)</label>
            <input
              type="number"
              step={0.5}
              min={0}
              max={12}
              value={clueSpacing}
              onChange={(e) => setClueSpacing(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Gap Below Puzzle (pt)
              <Tooltip text="Vertical space between the puzzle grid and the clue section." />
            </label>
            <input
              type="number"
              step={1}
              min={0}
              max={96}
              value={puzzleClueGap}
              onChange={(e) => setPuzzleClueGap(Number(e.target.value))}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5"
            />
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Clue Color</label>
            <input
              type="color"
              value={clueColor}
              onChange={(e) => setClueColor(e.target.value)}
              className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">Sort Order</label>
            <select
              value={clueSort}
              onChange={(e) => setClueSort(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
            >
              <option value="number">Clue Number</option>
              <option value="alphabetical">Alphabetical</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Capitalization</label>
            <select
              value={clueCapitalization}
              onChange={(e) => setClueCapitalization(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
            >
              <option value="sentence">Sentence case</option>
              <option value="title">Title Case</option>
              <option value="uppercase">ALL CAPS</option>
              <option value="lowercase">lowercase</option>
              <option value="as_is">As stored</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Ending Punctuation</label>
            <select
              value={clueEndingPunct}
              onChange={(e) => setClueEndingPunct(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
            >
              <option value="keep">Keep original</option>
              <option value="period">Add period (.)</option>
              <option value="none">Strip punctuation</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Enumeration</label>
            <select
              value={enumerationDisplay}
              onChange={(e) => setEnumerationDisplay(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
            >
              <option value="formatted">Word breaks (3,5)</option>
              <option value="total">Total length (8)</option>
              <option value="none">Hidden</option>
            </select>
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={showLengths}
            onChange={(e) => setShowLengths(e.target.checked)}
          />
          Show word length hints next to clues
        </label>
      </CollapsibleSection>

      {/* SECTION G: SOLUTION */}
      <CollapsibleSection
        letter="G"
        title="Solution Pages"
        subtitle="Answer keys per page (1/2/4/6/8/9/12), highlight & solution typography"
        badge={<span className="text-xs text-slate-500">{solutionsPerPage}/page</span>}
        defaultOpen={false}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div>
            <label className="block font-medium text-slate-700 mb-1">
              Solutions per Page
              <Tooltip text="Directly controls how many answer key grids share each page at the end of the book." />
            </label>
            <select
              value={solutionsPerPage}
              onChange={(e) =>
                setSolutionsPerPage(Number(e.target.value) as 1 | 2 | 4 | 6 | 8 | 9 | 12)
              }
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value={1}>1 per page</option>
              <option value={2}>2 per page</option>
              <option value={4}>4 per page</option>
              <option value={6}>6 per page</option>
              <option value={8}>8 per page</option>
              <option value={9}>9 per page</option>
              <option value={12}>12 per page</option>
            </select>
          </div>
          <div>
            <label className="block font-medium text-slate-700 mb-1">Highlight Style</label>
            <select
              value={solutionHighlightStyle}
              onChange={(e) => setSolutionHighlightStyle(e.target.value as any)}
              className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <option value="bold">Bold Letters</option>
              <option value="shaded">Lightly Shaded Cells</option>
              <option value="outline">High-Contrast Outline</option>
            </select>
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={copyAppearanceFromPuzzle}
            onChange={(e) => setCopyAppearanceFromPuzzle(e.target.checked)}
          />
          Copy Appearance from Puzzle
        </label>

        {!copyAppearanceFromPuzzle && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block font-medium text-slate-700 mb-1">Solution Font</label>
              {renderFontSelect(solutionFontFamily, setSolutionFontFamily)}
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Solution Size (pt)</label>
              <input
                type="number"
                min={6}
                max={24}
                value={solutionFontSize}
                onChange={(e) => setSolutionFontSize(Number(e.target.value))}
                className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700 mb-1">Solution Color</label>
              <input
                type="color"
                value={solutionColor}
                onChange={(e) => setSolutionColor(e.target.value)}
                className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
              />
            </div>
          </div>
        )}
      </CollapsibleSection>

      {/* SECTION H: TITLE */}
      <CollapsibleSection
        letter="H"
        title="Puzzle Title & Header"
        subtitle="Separate title controls for Puzzle pages and Answer/Solution pages"
        badge={
          <span className="text-xs text-slate-500">
            {titleEnabled ? titleAlignment : "Off"}
          </span>
        }
        defaultOpen={false}
      >
        <div className="space-y-4 text-xs">
          {/* Subsection 1: Puzzle Section */}
          <div className="border border-slate-200 rounded-lg p-3 bg-slate-50/60 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
              <h4 className="font-semibold text-slate-800 uppercase tracking-wide text-[11px]">
                Puzzle Section
              </h4>
              <label className="flex items-center gap-1.5 font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={titleEnabled}
                  onChange={(e) => setTitleEnabled(e.target.checked)}
                />
                Show puzzle title
              </label>
            </div>

            {titleEnabled && (
              <div className="space-y-3">
                <div>
                  <label className="block font-medium text-slate-700 mb-1">
                    Title for Puzzle Page
                    <Tooltip text="Choose whether each puzzle page uses the chapter name from your TXT/CSV file or a custom template." />
                  </label>
                  <select
                    value={titleMode}
                    onChange={(e) =>
                      setTitleMode(e.target.value as "chapter_name" | "custom")
                    }
                    className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                  >
                    <option value="chapter_name">Use Chapter Name from the TXT/CSV File</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>

                {titleMode === "custom" && (
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">
                      Custom Title Template
                      <Tooltip text="Use placeholders {PUZZLE_NUMBER}, {CHAPTER_TITLE}, and {TITLE}." />
                    </label>
                    <input
                      type="text"
                      value={titleTemplate}
                      onChange={(e) => setTitleTemplate(e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 font-mono bg-white"
                    />
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {["{PUZZLE_NUMBER}", "{CHAPTER_TITLE}", "{TITLE}"].map((tok) => (
                        <button
                          key={tok}
                          type="button"
                          onClick={() => setTitleTemplate((t) => `${t} ${tok}`.trim())}
                          className="bg-white hover:bg-slate-100 border border-slate-200 rounded px-2 py-0.5 font-mono text-[11px]"
                        >
                          + {tok}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Start #</label>
                    <input
                      type="number"
                      min={1}
                      max={999}
                      value={titleStartNumber}
                      onChange={(e) => setTitleStartNumber(Number(e.target.value))}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Title Font</label>
                    {renderFontSelect(titleFontFamily, setTitleFontFamily)}
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Title Size (pt)</label>
                    <input
                      type="number"
                      min={6}
                      max={48}
                      value={titleFontSize}
                      onChange={(e) => setTitleFontSize(Number(e.target.value))}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Alignment</label>
                    <select
                      value={titleAlignment}
                      onChange={(e) => setTitleAlignment(e.target.value as any)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    >
                      <option value="left">Left</option>
                      <option value="center">Center</option>
                      <option value="right">Right</option>
                    </select>
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">
                      Gap Below Title (pt)
                      <Tooltip text="Vertical space between the puzzle title and the puzzle grid." />
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={72}
                      step={1}
                      value={titleGap}
                      onChange={(e) => setTitleGap(Number(e.target.value))}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Title Color</label>
                    <input
                      type="color"
                      value={titleColor}
                      onChange={(e) => setTitleColor(e.target.value)}
                      className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Subsection 2: Answer Section */}
          <div className="border border-slate-200 rounded-lg p-3 bg-slate-50/60 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-1.5">
              <h4 className="font-semibold text-slate-800 uppercase tracking-wide text-[11px]">
                Answer Section
              </h4>
              <label className="flex items-center gap-1.5 font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={solutionTitleEnabled}
                  onChange={(e) => setSolutionTitleEnabled(e.target.checked)}
                />
                Show answer title
              </label>
            </div>

            {solutionTitleEnabled && (
              <div className="space-y-3">
                <div>
                  <label className="block font-medium text-slate-700 mb-1">
                    Title for Solution Page
                    <Tooltip text="Choose whether each answer key grid is labeled with the chapter name from your TXT/CSV file or a custom template." />
                  </label>
                  <select
                    value={solutionTitleMode}
                    onChange={(e) =>
                      setSolutionTitleMode(e.target.value as "chapter_name" | "custom")
                    }
                    className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                  >
                    <option value="chapter_name">Use Chapter Name from the TXT/CSV File</option>
                    <option value="custom">Custom</option>
                  </select>
                </div>

                {solutionTitleMode === "custom" && (
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">
                      Custom Solution Title Template
                      <Tooltip text="Use placeholders {PUZZLE_NUMBER}, {CHAPTER_TITLE}, and {TITLE}." />
                    </label>
                    <input
                      type="text"
                      value={solutionTitleTemplate}
                      onChange={(e) => setSolutionTitleTemplate(e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 font-mono bg-white"
                    />
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {["{PUZZLE_NUMBER}", "{CHAPTER_TITLE}", "{TITLE}"].map((tok) => (
                        <button
                          key={tok}
                          type="button"
                          onClick={() => setSolutionTitleTemplate((t) => `${t} ${tok}`.trim())}
                          className="bg-white hover:bg-slate-100 border border-slate-200 rounded px-2 py-0.5 font-mono text-[11px]"
                        >
                          + {tok}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Answer Title Font</label>
                    {renderFontSelect(solutionTitleFontFamily, setSolutionTitleFontFamily)}
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Answer Title Size (pt)</label>
                    <input
                      type="number"
                      min={6}
                      max={48}
                      value={solutionTitleFontSize}
                      onChange={(e) => setSolutionTitleFontSize(Number(e.target.value))}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Alignment</label>
                    <select
                      value={solutionTitleAlignment}
                      onChange={(e) => setSolutionTitleAlignment(e.target.value as any)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    >
                      <option value="left">Left</option>
                      <option value="center">Center</option>
                      <option value="right">Right</option>
                    </select>
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">
                      Gap Below Title (pt)
                      <Tooltip text="Vertical space between the answer title and the answer grid." />
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={72}
                      step={1}
                      value={solutionTitleGap}
                      onChange={(e) => setSolutionTitleGap(Number(e.target.value))}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">Answer Title Color</label>
                    <input
                      type="color"
                      value={solutionTitleColor}
                      onChange={(e) => setSolutionTitleColor(e.target.value)}
                      className="w-full h-8 border border-slate-300 rounded p-0.5 bg-white"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </CollapsibleSection>
    </>
  );
}
