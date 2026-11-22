import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  apiDownload,
  apiFetchSvg,
  apiRequest,
  BlockingIssue,
  ChapterInfo,
  FontOption,
  JobData,
  PagePlan,
  projectApi,
  ProjectData,
  ProjectSummary,
} from "../api";
import { toPlainLanguageError } from "../utils/errors";
import { convertDimension, TrimUnit, validateTrimSize } from "../utils/trimSize";

export type StudioStep = 1 | 2 | 3 | 4;
export type AutosaveStatus = "idle" | "saving" | "saved" | "error";
export type PreviewMode = "puzzle" | "answer_key" | "side_by_side";

export type UndoItem =
  | {
      kind: "clue_restore";
      wordId: number;
      previousClueId: number;
      label: string;
    }
  | {
      kind: "clue_text";
      wordId: number;
      previousText: string;
      difficulty: string;
      label: string;
    }
  | {
      kind: "entry_clue_text";
      puzzleId: number;
      entryId: number;
      previousText: string;
      label: string;
    }
  | {
      kind: "puzzle_regenerate";
      puzzleId: number;
      payload: any;
      label: string;
    };

function clamp(val: number, min: number, max: number): number {
  if (!Number.isFinite(val)) return min;
  return Math.max(min, Math.min(max, val));
}

function lineWidthToPt(value: number, unit: "pt" | "px" | "mm"): number {
  const pts =
    unit === "px" ? value * 0.75 : unit === "mm" ? value * (72 / 25.4) : value;
  return clamp(Math.round(pts * 100) / 100, 0.1, 5.0);
}

export function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function useProjectStudio() {
  const [step, setStepState] = useState<StudioStep>(1);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Project library & active project
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<number | null>(null);
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [activeCollectionId, setActiveCollectionId] = useState<number | null>(null);
  const [autosaveStatus, setAutosaveStatus] = useState<AutosaveStatus>("idle");
  const [autosavedAt, setAutosavedAt] = useState<string | null>(null);
  const skipNextAutosave = useRef(true);

  // Step 1: Project Identity
  const [projectName, setProjectName] = useState("My Crossword Book");
  const [projectType, setProjectType] = useState("crossword");

  // Step 2: Trim Size
  const [projectTrimSize, setProjectTrimSize] = useState("6x9");
  const [customWidth, setCustomWidth] = useState(6.0);
  const [customHeight, setCustomHeight] = useState(9.0);
  const [customUnit, setCustomUnitState] = useState<TrimUnit>("in");

  // Section A: Page Settings
  const [guidelineMode, setGuidelineMode] = useState<"kdp" | "paper">("kdp");
  const [pageUnit, setPageUnit] = useState<"pt" | "mm" | "in">("pt");
  const [independentMargins, setIndependentMargins] = useState(false);
  const [marginTop, setMarginTop] = useState(36);
  const [marginBottom, setMarginBottom] = useState(36);
  const [marginLeft, setMarginLeft] = useState(36);
  const [marginRight, setMarginRight] = useState(36);
  const [gutterPt, setGutterPt] = useState(18);
  const [startPuzzlesOnRightHandPage, setStartPuzzlesOnRightHandPage] = useState(false);
  const [showPageNumbers, setShowPageNumbers] = useState(true);

  // Section B: Import Word List (+ Clues)
  const [wordsPerChapter, setWordsPerChapter] = useState<number | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [importColName, setImportColName] = useState("Chapter 1");
  const [stagedBatch, setStagedBatch] = useState<any | null>(null);
  const [loadingImport, setLoadingImport] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Section C: Clues
  const [clueMode, setClueMode] = useState<"hybrid" | "automatic" | "manual">("hybrid");
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [verifyClues, setVerifyClues] = useState(false);
  const [requireAllCluesApproved, setRequireAllCluesApproved] = useState(false);
  const [clueSummary, setClueSummary] = useState<any | null>(null);
  const [clueStatusFilter, setClueStatusFilter] = useState<"all" | "needs_review" | "approved" | "missing">("all");
  const [clueAltsByWord, setClueAltsByWord] = useState<Record<number, any[]>>({});
  const [activeClueJob, setActiveClueJob] = useState<JobData | null>(null);
  const [editingWordId, setEditingWordId] = useState<number | null>(null);
  const [editingClueText, setEditingClueText] = useState("");

  // Section D: Grid
  const [gridMode, setGridMode] = useState<"auto" | "custom">("auto");
  const [customRows, setCustomRows] = useState(15);
  const [customCols, setCustomCols] = useState(15);
  const [symmetry, setSymmetry] = useState<"off" | "preferred">("off");
  const [strategy, setStrategy] = useState<"auto" | "longest" | "crossable" | "random">("auto");
  const [seed, setSeed] = useState(1);
  const [seedPinned, setSeedPinned] = useState(false);
  const [minWordLength, setMinWordLength] = useState(3);
  const [minDensity, setMinDensity] = useState(0.25);
  const [generatingPuzzle, setGeneratingPuzzle] = useState(false);

  // Section E: Puzzle Appearance
  const [availableFonts, setAvailableFonts] = useState<FontOption[]>([
    { family: "Open Sans", label: "Open Sans", license: "OFL-1.1" },
    { family: "Vera", label: "Bitstream Vera Sans", license: "Bitstream Vera" },
  ]);
  const [cellSize, setCellSize] = useState(24);
  const [lineWidth, setLineWidth] = useState(0.75);
  const [lineUnit, setLineUnit] = useState<"pt" | "px" | "mm">("pt");
  const [outerBorder, setOuterBorder] = useState(true);
  const [borderLineWidth, setBorderLineWidth] = useState(1.5);
  const [cellFill, setCellFill] = useState("#FFFFFF");
  const [emptyCellStyle, setEmptyCellStyle] = useState<"black" | "blank">("black");
  const [blockColor, setBlockColor] = useState("#000000");
  const [numberSize, setNumberSize] = useState(6.5);
  const [numberPosition, setNumberPosition] = useState<"top_left" | "top_right" | "bottom_left">("top_left");
  const [numberFont, setNumberFont] = useState("Open Sans");
  const [numberColor, setNumberColor] = useState("#000000");
  const [fontFamily, setFontFamily] = useState("Open Sans");
  const [capitalLetters, setCapitalLetters] = useState(true);

  // Section F: Clue Layout
  const [clueLayoutMode, setClueLayoutMode] = useState<"columns" | "rows" | "inline" | "side_by_side">("columns");
  const [clueHeadingStyle, setClueHeadingStyle] = useState<"uppercase" | "title" | "bold">("uppercase");
  const [clueFontFamily, setClueFontFamily] = useState("Open Sans");
  const [clueFontSize, setClueFontSize] = useState(9.5);
  const [clueColor, setClueColor] = useState("#000000");
  const [clueSpacing, setClueSpacing] = useState(2.0);
  const [puzzleClueGap, setPuzzleClueGap] = useState(16);
  const [clueSort, setClueSort] = useState<"number" | "alphabetical">("number");
  const [showLengths, setShowLengths] = useState(true);
  const [enumerationDisplay, setEnumerationDisplay] = useState<"formatted" | "total" | "none">("formatted");
  const [clueCapitalization, setClueCapitalization] = useState<
    "sentence" | "title" | "uppercase" | "lowercase" | "as_is"
  >("sentence");
  const [clueEndingPunct, setClueEndingPunct] = useState<"keep" | "period" | "none">("keep");
  const [cluePlacement, setCluePlacement] = useState<"same_page" | "beside" | "facing_page">("same_page");

  // Section G: Solution
  const [solutionsPerPage, setSolutionsPerPage] = useState<1 | 2 | 4 | 6 | 8 | 9 | 12>(4);
  const [solutionTitleEnabled, setSolutionTitleEnabled] = useState(true);
  const [solutionTitleMode, setSolutionTitleModeState] = useState<"chapter_name" | "custom">("chapter_name");
  const [solutionTitleTemplate, setSolutionTitleTemplate] = useState("Puzzle {PUZZLE_NUMBER}: {CHAPTER_TITLE}");
  const [solutionTitleFontFamily, setSolutionTitleFontFamily] = useState("Open Sans");
  const [solutionTitleFontSize, setSolutionTitleFontSize] = useState(12);
  const [solutionTitleColor, setSolutionTitleColor] = useState("#000000");
  const [solutionTitleAlignment, setSolutionTitleAlignment] = useState<"left" | "center" | "right">("center");
  const [solutionTitleGap, setSolutionTitleGap] = useState(8);
  const [solutionHighlightStyle, setSolutionHighlightStyle] = useState<"bold" | "shaded" | "outline">("bold");
  const [copyAppearanceFromPuzzle, setCopyAppearanceFromPuzzle] = useState(true);
  const [solutionFontFamily, setSolutionFontFamily] = useState("Open Sans");
  const [solutionFontSize, setSolutionFontSize] = useState(10);
  const [solutionColor, setSolutionColor] = useState("#000000");

  // Section H: Title
  const [titleEnabled, setTitleEnabled] = useState(true);
  const [titleMode, setTitleModeState] = useState<"chapter_name" | "custom">("chapter_name");
  const [firstLineIsTitle, setFirstLineIsTitle] = useState(false);
  const [titleTemplate, setTitleTemplate] = useState("Chapter {PUZZLE_NUMBER}: {CHAPTER_TITLE}");

  const setTitleMode = useCallback((mode: "chapter_name" | "custom") => {
    setTitleModeState(mode);
    if (mode === "chapter_name") setFirstLineIsTitle(true);
  }, []);

  const setSolutionTitleMode = useCallback((mode: "chapter_name" | "custom") => {
    setSolutionTitleModeState(mode);
    if (mode === "chapter_name") setFirstLineIsTitle(true);
  }, []);
  const [titleStartNumber, setTitleStartNumber] = useState(1);
  const [titleFontFamily, setTitleFontFamily] = useState("Open Sans");
  const [titleFontSize, setTitleFontSize] = useState(16);
  const [titleColor, setTitleColor] = useState("#000000");
  const [titleAlignment, setTitleAlignment] = useState<"left" | "center" | "right">("center");
  const [titleGap, setTitleGap] = useState(10);

  // Live Preview & Chapter Diagnostics
  const [puzzle, setPuzzle] = useState<any | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("puzzle");
  const [previewZoom, setPreviewZoom] = useState(100);
  const [showMarginGuides, setShowMarginGuides] = useState(true);
  const [puzzleSvg, setPuzzleSvg] = useState("");
  const [answerKeySvg, setAnswerKeySvg] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewReqIdRef = useRef(0);
  const lastPuzzleSvgKeyRef = useRef("");
  const lastAnswerKeySvgKeyRef = useRef("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [unplacedEdits, setUnplacedEdits] = useState<Record<string, string>>({});

  // Review & Book Download (Step 4)
  const [bookPagePlan, setBookPagePlan] = useState<PagePlan | null>(null);
  const [blockingIssues, setBlockingIssues] = useState<BlockingIssue[]>([]);
  const [blockingWarnings, setBlockingWarnings] = useState<BlockingIssue[]>([]);
  const [bookGenJob, setBookGenJob] = useState<JobData | null>(null);
  const [retryingFailedChapters, setRetryingFailedChapters] = useState(false);
  const downloadedBookJobRef = useRef<string | null>(null);

  // Undo History for clue and word edits
  const [undoStack, setUndoStack] = useState<UndoItem[]>([]);

  const pushUndo = useCallback((item: UndoItem) => {
    setUndoStack((prev) => [item, ...prev].slice(0, 20));
  }, []);

  const trimValidation = useMemo(
    () => validateTrimSize(projectTrimSize, customWidth, customHeight, customUnit),
    [projectTrimSize, customWidth, customHeight, customUnit]
  );

  const isStep1Valid = projectName.trim().length > 0;
  const isStep2Valid = isStep1Valid && trimValidation.valid;
  const isStep3Valid = isStep2Valid && chapters.length > 0;

  const canGoToStep = useCallback(
    (target: StudioStep) => {
      if (target === 1) return true;
      if (target === 2) return isStep1Valid;
      if (target === 3) return isStep2Valid;
      return isStep3Valid;
    },
    [isStep1Valid, isStep2Valid, isStep3Valid]
  );

  const setStep = useCallback(
    (target: StudioStep) => {
      if (!canGoToStep(target)) return;
      setError(null);
      setStepState(target);
    },
    [canGoToStep]
  );

  const setCustomUnit = useCallback(
    (nextUnit: TrimUnit) => {
      setCustomWidth((w) => convertDimension(w, customUnit, nextUnit));
      setCustomHeight((h) => convertDimension(h, customUnit, nextUnit));
      setCustomUnitState(nextUnit);
    },
    [customUnit]
  );

  const setUniformMargin = useCallback((val: number) => {
    const clean = clamp(val, 0, 200);
    setMarginTop(clean);
    setMarginBottom(clean);
    setMarginLeft(clean);
    setMarginRight(clean);
  }, []);

  const buildAutosaveSettings = useCallback(
    () => ({
      words_per_chapter: wordsPerChapter,
      min_word_length: minWordLength,
      enumeration_display: enumerationDisplay,
      trim: {
        preset: projectTrimSize,
        custom_width: customWidth,
        custom_height: customHeight,
        custom_unit: customUnit,
      },
      page: {
        guideline_mode: guidelineMode,
        unit: pageUnit,
        independent_margins: independentMargins,
        margin_top: marginTop,
        margin_bottom: marginBottom,
        margin_left: marginLeft,
        margin_right: marginRight,
        gutter: gutterPt,
        start_puzzles_on_right_hand_page: startPuzzlesOnRightHandPage,
        show_page_numbers: showPageNumbers,
      },
      clues: {
        mode: clueMode,
        difficulty,
        verify: verifyClues,
        capitalization: clueCapitalization,
        ending_punctuation: clueEndingPunct,
        show_length_hint: showLengths,
        require_all_clues_approved: requireAllCluesApproved,
      },
      grid: {
        mode: gridMode,
        rows: customRows,
        cols: customCols,
        symmetry,
        strategy,
        seed,
        seed_pinned: seedPinned,
        min_word_length: minWordLength,
        min_density: minDensity,
      },
      appearance: {
        cell_size: cellSize,
        line_width: lineWidth,
        line_unit: lineUnit,
        outer_border: outerBorder,
        border_line_width: borderLineWidth,
        cell_fill: cellFill,
        empty_cell_style: emptyCellStyle,
        block_color: blockColor,
        number_size: numberSize,
        number_position: numberPosition,
        number_font: numberFont,
        number_color: numberColor,
        font_family: fontFamily,
        capital_letters: capitalLetters,
      },
      clue_layout: {
        layout_mode: clueLayoutMode,
        heading_style: clueHeadingStyle,
        font_family: clueFontFamily,
        font_size: clueFontSize,
        color: clueColor,
        spacing: clueSpacing,
        puzzle_clue_gap: puzzleClueGap,
        sort: clueSort,
        show_length_hint: showLengths,
        placement: cluePlacement,
      },
      solution: {
        per_page: solutionsPerPage,
        title_enabled: solutionTitleEnabled,
        title_mode: solutionTitleMode,
        title_template: solutionTitleTemplate,
        title_font_family: solutionTitleFontFamily,
        title_font_size: solutionTitleFontSize,
        title_color: solutionTitleColor,
        title_alignment: solutionTitleAlignment,
        title_gap: solutionTitleGap,
        highlight_style: solutionHighlightStyle,
        copy_appearance: copyAppearanceFromPuzzle,
        font_family: solutionFontFamily,
        font_size: solutionFontSize,
        color: solutionColor,
      },
      title: {
        enabled: titleEnabled,
        mode: titleMode,
        first_line_is_title: firstLineIsTitle,
        template: titleTemplate,
        start_number: titleStartNumber,
        font_family: titleFontFamily,
        font_size: titleFontSize,
        color: titleColor,
        alignment: titleAlignment,
        gap: titleGap,
      },
    }),
    [
      wordsPerChapter,
      minWordLength,
      enumerationDisplay,
      projectTrimSize,
      customWidth,
      customHeight,
      customUnit,
      guidelineMode,
      pageUnit,
      independentMargins,
      marginTop,
      marginBottom,
      marginLeft,
      marginRight,
      gutterPt,
      startPuzzlesOnRightHandPage,
      showPageNumbers,
      clueMode,
      difficulty,
      verifyClues,
      clueCapitalization,
      clueEndingPunct,
      showLengths,
      requireAllCluesApproved,
      gridMode,
      customRows,
      customCols,
      symmetry,
      strategy,
      seed,
      seedPinned,
      minDensity,
      cellSize,
      lineWidth,
      lineUnit,
      outerBorder,
      borderLineWidth,
      cellFill,
      emptyCellStyle,
      blockColor,
      numberSize,
      numberPosition,
      numberFont,
      numberColor,
      fontFamily,
      capitalLetters,
      clueLayoutMode,
      clueHeadingStyle,
      clueFontFamily,
      clueFontSize,
      clueColor,
      clueSpacing,
      puzzleClueGap,
      clueSort,
      cluePlacement,
      solutionsPerPage,
      solutionTitleEnabled,
      solutionTitleMode,
      solutionTitleTemplate,
      solutionTitleFontFamily,
      solutionTitleFontSize,
      solutionTitleColor,
      solutionTitleAlignment,
      solutionTitleGap,
      solutionHighlightStyle,
      copyAppearanceFromPuzzle,
      solutionFontFamily,
      solutionFontSize,
      solutionColor,
      titleEnabled,
      titleMode,
      firstLineIsTitle,
      titleTemplate,
      titleStartNumber,
      titleFontFamily,
      titleFontSize,
      titleColor,
      titleAlignment,
      titleGap,
    ]
  );

  const buildLiveExportSettings = useCallback(() => {
    const linePt = lineWidthToPt(lineWidth, lineUnit);
    return {
      page_size: projectTrimSize,
      custom_width: projectTrimSize === "custom" ? customWidth : null,
      custom_height: projectTrimSize === "custom" ? customHeight : null,
      custom_unit: customUnit,
      margin_top: clamp(marginTop, 0, 200),
      margin_bottom: clamp(marginBottom, 0, 200),
      margin_left: clamp(marginLeft, 0, 200),
      margin_right: clamp(marginRight, 0, 200),
      gutter: clamp(gutterPt, 0, 100),
      grid_alignment: "center",
      font_family: fontFamily,
      title_font_family: titleFontFamily,
      title_font_size: clamp(titleEnabled ? titleFontSize : 6, 6, 48),
      title_color: titleColor,
      title_alignment: titleAlignment,
      title_gap: clamp(titleGap, 0, 72),
      solution_title_font_family: solutionTitleFontFamily,
      solution_title_font_size: clamp(solutionTitleEnabled ? solutionTitleFontSize : 6, 6, 48),
      solution_title_color: solutionTitleColor,
      solution_title_alignment: solutionTitleAlignment,
      solution_title_gap: clamp(solutionTitleGap, 0, 72),
      clue_font_family: clueFontFamily,
      clue_font_size: clamp(clueFontSize, 5, 24),
      clue_color: clueColor,
      clue_spacing: clamp(clueSpacing, 0, 24),
      puzzle_clue_gap: clamp(puzzleClueGap, 0, 96),
      clue_layout_mode: clueLayoutMode,
      clue_heading_style: clueHeadingStyle,
      clue_sort: clueSort,
      number_font_family: numberFont,
      number_font_size: clamp(numberSize, 4, 16),
      number_color: numberColor,
      number_position: numberPosition,
      letter_font_size: clamp(
        copyAppearanceFromPuzzle ? Math.round(cellSize * 0.5) : solutionFontSize,
        6,
        32
      ),
      capital_letters: capitalLetters,
      solution_font_family: copyAppearanceFromPuzzle ? fontFamily : solutionFontFamily,
      solution_color: copyAppearanceFromPuzzle ? "#000000" : solutionColor,
      solution_highlight_style: solutionHighlightStyle,
      grid_line_width: linePt,
      border_line_width: outerBorder ? clamp(borderLineWidth, 0, 8) : 0,
      ink_color: "#000000",
      bg_color: "#FFFFFF",
      block_color: blockColor,
      cell_bg_color: cellFill,
      show_clue_lengths: showLengths,
      enumeration_display: enumerationDisplay,
      clue_capitalization: clueCapitalization,
      clue_ending_punctuation: clueEndingPunct,
      black_empty_cells: emptyCellStyle === "black",
      dpi: 300,
    };
  }, [
    lineWidth,
    lineUnit,
    projectTrimSize,
    customWidth,
    customHeight,
    customUnit,
    marginTop,
    marginBottom,
    marginLeft,
    marginRight,
    gutterPt,
    fontFamily,
    titleFontFamily,
    titleEnabled,
    titleFontSize,
    titleColor,
    titleAlignment,
    titleGap,
    solutionTitleEnabled,
    solutionTitleFontFamily,
    solutionTitleFontSize,
    solutionTitleColor,
    solutionTitleAlignment,
    solutionTitleGap,
    clueFontFamily,
    clueFontSize,
    clueColor,
    clueSpacing,
    puzzleClueGap,
    clueLayoutMode,
    clueHeadingStyle,
    clueSort,
    numberFont,
    numberSize,
    numberColor,
    numberPosition,
    copyAppearanceFromPuzzle,
    cellSize,
    solutionFontSize,
    capitalLetters,
    solutionFontFamily,
    solutionColor,
    solutionHighlightStyle,
    outerBorder,
    borderLineWidth,
    blockColor,
    cellFill,
    showLengths,
    enumerationDisplay,
    clueCapitalization,
    clueEndingPunct,
    emptyCellStyle,
  ]);

  const loadProjectIntoState = useCallback(
    (proj: ProjectData) => {
      skipNextAutosave.current = true;
      if (proj.id !== activeProjectId) {
        setBookGenJob(null);
        downloadedBookJobRef.current = null;
        setUndoStack([]);
      }
      setActiveProjectId(proj.id);
      setProjectName(proj.name || "Untitled Crossword Book");
      setProjectType(proj.project_type || "crossword");
      setProjectTrimSize(proj.trim_size || "6x9");
      setChapters(proj.chapters || []);
      setBlockingIssues(proj.blocking_issues || []);
      setBlockingWarnings(proj.warnings || []);
      setBookPagePlan(proj.page_plan || null);

      const st = proj.settings || {};
      const trim = st.trim || {};
      if (trim.preset) setProjectTrimSize(String(trim.preset));
      if (trim.custom_width !== undefined) setCustomWidth(Number(trim.custom_width));
      if (trim.custom_height !== undefined) setCustomHeight(Number(trim.custom_height));
      if (trim.custom_unit && ["in", "mm", "cm"].includes(trim.custom_unit)) {
        setCustomUnitState(trim.custom_unit);
      }

      setWordsPerChapter(
        st.words_per_chapter === null || st.words_per_chapter === undefined || st.words_per_chapter === ""
          ? null
          : Number(st.words_per_chapter)
      );
      if (st.enumeration_display) setEnumerationDisplay(st.enumeration_display);

      const pageCfg = st.page || {};
      if (pageCfg.guideline_mode) setGuidelineMode(pageCfg.guideline_mode);
      if (pageCfg.unit && ["pt", "mm", "in"].includes(pageCfg.unit)) {
        setPageUnit(pageCfg.unit);
      }
      if (pageCfg.independent_margins !== undefined) setIndependentMargins(Boolean(pageCfg.independent_margins));
      setMarginTop(Number(pageCfg.margin_top ?? 36));
      setMarginBottom(Number(pageCfg.margin_bottom ?? 36));
      setMarginLeft(Number(pageCfg.margin_left ?? 36));
      setMarginRight(Number(pageCfg.margin_right ?? 36));
      setGutterPt(Number(pageCfg.gutter ?? 18));
      setStartPuzzlesOnRightHandPage(Boolean(pageCfg.start_puzzles_on_right_hand_page ?? false));
      setShowPageNumbers(pageCfg.show_page_numbers !== undefined ? Boolean(pageCfg.show_page_numbers) : true);

      const clueCfg = st.clues || {};
      if (clueCfg.mode) setClueMode(clueCfg.mode);
      if (clueCfg.difficulty) setDifficulty(clueCfg.difficulty);
      if (clueCfg.verify !== undefined) setVerifyClues(Boolean(clueCfg.verify));
      if (clueCfg.capitalization) setClueCapitalization(clueCfg.capitalization);
      if (clueCfg.ending_punctuation) setClueEndingPunct(clueCfg.ending_punctuation);
      setShowLengths(clueCfg.show_length_hint !== undefined ? Boolean(clueCfg.show_length_hint) : true);
      setRequireAllCluesApproved(Boolean(clueCfg.require_all_clues_approved ?? false));

      const gridCfg = st.grid || {};
      if (gridCfg.mode) setGridMode(gridCfg.mode);
      if (gridCfg.rows) setCustomRows(Number(gridCfg.rows));
      if (gridCfg.cols) setCustomCols(Number(gridCfg.cols));
      if (gridCfg.symmetry) setSymmetry(gridCfg.symmetry);
      if (gridCfg.strategy) setStrategy(gridCfg.strategy);
      if (gridCfg.seed !== undefined) setSeed(Number(gridCfg.seed));
      setSeedPinned(Boolean(gridCfg.seed_pinned ?? false));
      if (gridCfg.min_word_length !== undefined) {
        setMinWordLength(Number(gridCfg.min_word_length));
      } else if (st.min_word_length !== undefined) {
        setMinWordLength(Number(st.min_word_length));
      }
      if (gridCfg.min_density !== undefined) setMinDensity(Number(gridCfg.min_density));

      const appCfg = st.appearance || {};
      setCellSize(Number(appCfg.cell_size ?? 24));
      setLineWidth(Number(appCfg.line_width ?? 0.75));
      if (appCfg.line_unit) setLineUnit(appCfg.line_unit);
      setOuterBorder(appCfg.outer_border !== undefined ? Boolean(appCfg.outer_border) : true);
      setBorderLineWidth(Number(appCfg.border_line_width ?? 1.5));
      setCellFill(String(appCfg.cell_fill || "#FFFFFF"));
      setEmptyCellStyle(appCfg.empty_cell_style === "blank" ? "blank" : "black");
      setBlockColor(String(appCfg.block_color || "#000000"));
      setNumberSize(Number(appCfg.number_size ?? 6.5));
      if (appCfg.number_position) setNumberPosition(appCfg.number_position);
      setNumberFont(String(appCfg.number_font || "Open Sans"));
      setNumberColor(String(appCfg.number_color || "#000000"));
      setFontFamily(String(appCfg.font_family || "Open Sans"));
      setCapitalLetters(appCfg.capital_letters !== undefined ? Boolean(appCfg.capital_letters) : true);

      const clCfg = st.clue_layout || {};
      if (clCfg.layout_mode) setClueLayoutMode(clCfg.layout_mode);
      if (clCfg.heading_style) setClueHeadingStyle(clCfg.heading_style);
      setClueFontFamily(String(clCfg.font_family || "Open Sans"));
      setClueFontSize(Number(clCfg.font_size ?? 9.5));
      setClueColor(String(clCfg.color || "#000000"));
      setClueSpacing(Number(clCfg.spacing ?? 2.0));
      setPuzzleClueGap(Number(clCfg.puzzle_clue_gap ?? 16));
      if (clCfg.sort) setClueSort(clCfg.sort);
      if (clCfg.placement) setCluePlacement(clCfg.placement);

      const solCfg = st.solution || {};
      const titleCfg = st.title || {};
      const perPageNum = Number(solCfg.per_page);
      setSolutionsPerPage(
        perPageNum === 1 ||
          perPageNum === 2 ||
          perPageNum === 4 ||
          perPageNum === 6 ||
          perPageNum === 8 ||
          perPageNum === 9 ||
          perPageNum === 12
          ? perPageNum
          : 4
      );
      setSolutionTitleEnabled(solCfg.title_enabled !== undefined ? Boolean(solCfg.title_enabled) : true);
      setSolutionTitleModeState(solCfg.title_mode === "custom" ? "custom" : "chapter_name");
      setSolutionTitleTemplate(String(solCfg.title_template || "Puzzle {PUZZLE_NUMBER}: {CHAPTER_TITLE}"));
      setSolutionTitleFontFamily(String(solCfg.title_font_family || titleCfg?.font_family || "Open Sans"));
      setSolutionTitleFontSize(Number(solCfg.title_font_size ?? 12));
      setSolutionTitleColor(String(solCfg.title_color || "#000000"));
      if (solCfg.title_alignment) setSolutionTitleAlignment(solCfg.title_alignment);
      setSolutionTitleGap(Number(solCfg.title_gap ?? 8));
      if (solCfg.highlight_style) setSolutionHighlightStyle(solCfg.highlight_style);
      setCopyAppearanceFromPuzzle(solCfg.copy_appearance !== undefined ? Boolean(solCfg.copy_appearance) : true);
      setSolutionFontFamily(String(solCfg.font_family || "Open Sans"));
      setSolutionFontSize(Number(solCfg.font_size ?? 10));
      setSolutionColor(String(solCfg.color || "#000000"));

      setTitleEnabled(titleCfg.enabled !== undefined ? Boolean(titleCfg.enabled) : true);
      setTitleModeState(titleCfg.mode === "custom" ? "custom" : "chapter_name");
      setFirstLineIsTitle(Boolean(titleCfg.first_line_is_title));
      setTitleTemplate(String(titleCfg.template || "Chapter {PUZZLE_NUMBER}: {CHAPTER_TITLE}"));
      setTitleStartNumber(Number(titleCfg.start_number ?? 1));
      setTitleFontFamily(String(titleCfg.font_family || "Open Sans"));
      setTitleFontSize(Number(titleCfg.font_size ?? 16));
      setTitleColor(String(titleCfg.color || "#000000"));
      if (titleCfg.alignment) setTitleAlignment(titleCfg.alignment);
      setTitleGap(Number(titleCfg.gap ?? 10));

      if (proj.autosaved_at) {
        setAutosavedAt(proj.autosaved_at);
        setAutosaveStatus("saved");
      }

      const chList = proj.chapters || [];
      if (chList.length > 0) {
        setActiveCollectionId((prev) =>
          prev && chList.some((c) => c.id === prev) ? prev : chList[0].id
        );
      } else {
        setActiveCollectionId(null);
        setPuzzle(null);
        setPuzzleSvg("");
        setAnswerKeySvg("");
        setClueSummary(null);
      }
    },
    [activeProjectId]
  );

  const refreshProjects = useCallback(
    async (selectId?: number) => {
      try {
        const list = await projectApi.list();
        setProjects(list);
        const targetId = selectId ?? activeProjectId ?? list[0]?.id;
        if (targetId) {
          const full = await projectApi.get(targetId);
          loadProjectIntoState(full);
        } else {
          const created = await projectApi.create({
            name: "My Crossword Book",
            project_type: "crossword",
            trim_size: "6x9",
          });
          setProjects([created]);
          loadProjectIntoState(created);
        }
      } catch (e) {
        setError(toPlainLanguageError(e));
      }
    },
    [activeProjectId, loadProjectIntoState]
  );

  const reloadActiveProject = useCallback(async () => {
    if (!activeProjectId) return;
    try {
      const full = await projectApi.get(activeProjectId);
      loadProjectIntoState(full);
    } catch (e) {
      setError(toPlainLanguageError(e));
    }
  }, [activeProjectId, loadProjectIntoState]);

  const refreshProjectPlanAndIssues = useCallback(
    async (projId = activeProjectId) => {
      if (!projId) return;
      try {
        const [blk, plan] = await Promise.all([
          projectApi.blockingIssues(projId),
          projectApi.pagePlan(projId),
        ]);
        setBlockingIssues(blk.blocking_issues || []);
        setBlockingWarnings(blk.warnings || []);
        setBookPagePlan(plan || blk.page_plan || null);
      } catch {
        // Ignore transient refresh failure
      }
    },
    [activeProjectId]
  );

  const didInitRef = useRef(false);
  useEffect(() => {
    if (didInitRef.current) return;
    didInitRef.current = true;
    if (typeof document !== "undefined" && !document.getElementById("woodpecker-embedded-fonts")) {
      const link = document.createElement("link");
      link.id = "woodpecker-embedded-fonts";
      link.rel = "stylesheet";
      link.href = `${API_BASE}/api/export/fonts.css`;
      document.head.appendChild(link);
    }
    refreshProjects();
    projectApi
      .exportFonts()
      .then((fonts) => {
        if (Array.isArray(fonts) && fonts.length > 0) setAvailableFonts(fonts);
      })
      .catch(() => {
        // Fallback to built-in Open Sans + Vera options
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced autosave
  const serializedSettings = useMemo(() => JSON.stringify(buildAutosaveSettings()), [buildAutosaveSettings]);

  useEffect(() => {
    if (!activeProjectId) return;
    if (skipNextAutosave.current) {
      skipNextAutosave.current = false;
      return;
    }
    if (!projectName.trim()) return;

    setAutosaveStatus("saving");
    const timer = setTimeout(async () => {
      try {
        const updated = await projectApi.patch(activeProjectId, {
          name: projectName.trim(),
          project_type: projectType,
          trim_size: projectTrimSize,
          settings: JSON.parse(serializedSettings),
        });
        setAutosavedAt(updated.autosaved_at || new Date().toISOString());
        setAutosaveStatus("saved");
        if (updated.chapters) setChapters(updated.chapters);
        if (updated.blocking_issues) setBlockingIssues(updated.blocking_issues);
        if (updated.warnings) setBlockingWarnings(updated.warnings);
        if (updated.page_plan) setBookPagePlan(updated.page_plan);
        setProjects((prev) =>
          prev.map((p) =>
            p.id === updated.id
              ? { ...p, name: updated.name, trim_size: updated.trim_size }
              : p
          )
        );
      } catch {
        setAutosaveStatus("error");
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [activeProjectId, projectName, projectType, projectTrimSize, serializedSettings]);

  const refreshClueSummary = useCallback(
    async (colId = activeCollectionId) => {
      if (!colId) return;
      try {
        const data = await apiRequest(
          `/api/collections/${colId}/clues?mode=${clueMode}&difficulty=${difficulty}&capitalization=${clueCapitalization}&ending_punctuation=${clueEndingPunct}&show_length_hint=${showLengths}&enumeration_display=${enumerationDisplay}`
        );
        setClueSummary(data);
        if (activeProjectId) {
          await refreshProjectPlanAndIssues(activeProjectId);
        }
      } catch (e) {
        setError(toPlainLanguageError(e));
      }
    },
    [
      activeCollectionId,
      activeProjectId,
      clueMode,
      difficulty,
      clueCapitalization,
      clueEndingPunct,
      showLengths,
      enumerationDisplay,
      refreshProjectPlanAndIssues,
    ]
  );

  useEffect(() => {
    if (step === 3 && activeCollectionId) {
      refreshClueSummary(activeCollectionId);
    }
  }, [step, activeCollectionId, refreshClueSummary]);

  useEffect(() => {
    if (step === 4 && activeProjectId) {
      refreshProjectPlanAndIssues(activeProjectId);
      reloadActiveProject();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  // Load puzzle for active chapter when on Step 3
  const activeChapter = useMemo(
    () => chapters.find((c) => c.id === activeCollectionId) || null,
    [chapters, activeCollectionId]
  );

  const activeChapterIndex = useMemo(
    () => (activeChapter ? chapters.findIndex((c) => c.id === activeChapter.id) : -1),
    [chapters, activeChapter]
  );

  useEffect(() => {
    if (step !== 3) return;
    if (!activeChapter?.puzzle_id) {
      setPuzzle(null);
      setPuzzleSvg("");
      setAnswerKeySvg("");
      lastPuzzleSvgKeyRef.current = "";
      lastAnswerKeySvgKeyRef.current = "";
      return;
    }
    if (puzzle && puzzle.id === activeChapter.puzzle_id) return;
    apiRequest(`/api/puzzles/${activeChapter.puzzle_id}`)
      .then((p) => setPuzzle(p))
      .catch((e) => setError(toPlainLanguageError(e)));
  }, [step, activeChapter?.puzzle_id, puzzle]);

  // Fetch server SVG preview matching live export settings whenever puzzle or appearance changes
  const serializedExportSettings = useMemo(
    () => JSON.stringify(buildLiveExportSettings()),
    [buildLiveExportSettings]
  );

  const puzzleId = puzzle?.id ?? null;
  const puzzleUpdatedAt = puzzle?.updated_at ?? "";
  const puzzleTitle = puzzle?.title ?? "";
  const activeChapterId = activeChapter?.id ?? null;
  const activeChapterName = activeChapter?.name ?? "";

  useEffect(() => {
    if (!puzzleId || step !== 3) return;

    const puzzleKind = cluePlacement === "facing_page" ? "puzzle" : "puzzle_with_clues";
    const chapName = activeChapterName || puzzleTitle || "Chapter 1";
    const puzNum = titleStartNumber + Math.max(0, activeChapterIndex);
    const formatTitle = (mode: "chapter_name" | "custom", tmpl: string) => {
      if (mode === "custom" && tmpl.trim()) {
        return tmpl
          .trim()
          .replace(/\{PUZZLE_NUMBER\}/g, String(puzNum))
          .replace(/\{CHAPTER_TITLE\}/g, chapName)
          .replace(/\{TITLE\}/g, chapName);
      }
      return chapName;
    };
    const livePuzzleTitle = titleEnabled ? formatTitle(titleMode, titleTemplate) : "";
    const liveSolutionTitle = solutionTitleEnabled
      ? formatTitle(solutionTitleMode, solutionTitleTemplate)
      : "";

    const renderKey = [
      puzzleId,
      puzzleUpdatedAt,
      puzzleKind,
      livePuzzleTitle,
      liveSolutionTitle,
      solutionsPerPage,
      activeChapterIndex,
      serializedExportSettings,
    ].join("|");

    const needPuzzle =
      (previewMode === "puzzle" || previewMode === "side_by_side") &&
      lastPuzzleSvgKeyRef.current !== renderKey;
    const needAnswerKey =
      (previewMode === "answer_key" || previewMode === "side_by_side") &&
      lastAnswerKeySvgKeyRef.current !== renderKey;

    if (!needPuzzle && !needAnswerKey) return;

    const controller = new AbortController();
    const reqId = ++previewReqIdRef.current;

    const timer = setTimeout(() => {
      const settingsObj = JSON.parse(serializedExportSettings);
      setPreviewLoading(true);
      const tasks: Promise<void>[] = [];

      if (needPuzzle) {
        tasks.push(
          apiFetchSvg(`/api/puzzles/${puzzleId}/export`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({
              kind: puzzleKind,
              format: "svg",
              page: 0,
              force: true,
              title_override: livePuzzleTitle,
              solution_title_override: liveSolutionTitle,
              settings: settingsObj,
            }),
          })
            .then((svg) => {
              if (previewReqIdRef.current === reqId) {
                lastPuzzleSvgKeyRef.current = renderKey;
                setPuzzleSvg(svg);
              }
            })
            .catch(() => {
              // Ignore aborted or transient preview requests
            })
        );
      }

      if (needAnswerKey) {
        const answerKeyPromise = activeProjectId
          ? apiFetchSvg(`/api/projects/${activeProjectId}/solution-preview`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              signal: controller.signal,
              body: JSON.stringify({
                chapter_index: Math.max(0, activeChapterIndex),
                solutions_per_page: solutionsPerPage,
                title_enabled: solutionTitleEnabled,
                title_mode: solutionTitleMode,
                title_template: solutionTitleTemplate,
                title_start_number: titleStartNumber,
                settings: settingsObj,
              }),
            })
          : apiFetchSvg(`/api/puzzles/${puzzleId}/export`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              signal: controller.signal,
              body: JSON.stringify({
                kind: "answer_key",
                format: "svg",
                page: 0,
                force: true,
                title_override: livePuzzleTitle,
                solution_title_override: liveSolutionTitle,
                settings: settingsObj,
              }),
            });

        tasks.push(
          answerKeyPromise
            .then((svg) => {
              if (previewReqIdRef.current === reqId) {
                lastAnswerKeySvgKeyRef.current = renderKey;
                setAnswerKeySvg(svg);
              }
            })
            .catch(() => {
              // Ignore aborted or transient preview requests
            })
        );
      }

      Promise.all(tasks).finally(() => {
        if (previewReqIdRef.current === reqId) {
          setPreviewLoading(false);
        }
      });
    }, 60);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    activeProjectId,
    puzzleId,
    puzzleUpdatedAt,
    puzzleTitle,
    step,
    previewMode,
    cluePlacement,
    solutionsPerPage,
    serializedExportSettings,
    activeChapterId,
    activeChapterName,
    activeChapterIndex,
    titleEnabled,
    titleMode,
    titleTemplate,
    titleStartNumber,
    solutionTitleEnabled,
    solutionTitleMode,
    solutionTitleTemplate,
  ]);

  // Poll clue generation job
  useEffect(() => {
    if (!activeClueJob || (activeClueJob.status !== "pending" && activeClueJob.status !== "running")) return;
    const timer = setInterval(async () => {
      try {
        const updated = await projectApi.getJob(activeClueJob.id);
        setActiveClueJob(updated);
        if (updated.status === "completed" || updated.status === "failed") {
          refreshClueSummary();
        }
      } catch {
        // ignore transient poll error
      }
    }, 600);
    return () => clearInterval(timer);
  }, [activeClueJob, refreshClueSummary]);

  const bookPdfFilename = `${
    (projectName || "crossword_book")
      .trim()
      .replace(/[^a-zA-Z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .toLowerCase() || "crossword_book"
  }.pdf`;

  const handleDownloadVerifiedBookPdf = useCallback(
    async (projId = activeProjectId) => {
      if (!projId) return;
      setError(null);
      try {
        const blob = await projectApi.downloadBookPdf(projId);
        triggerBlobDownload(blob, bookPdfFilename);
      } catch (err) {
        setError(toPlainLanguageError(err));
        await refreshProjectPlanAndIssues(projId);
      }
    },
    [activeProjectId, bookPdfFilename, refreshProjectPlanAndIssues]
  );

  // Poll book generation job & auto-download verified PDF
  useEffect(() => {
    if (!bookGenJob) return;
    if (bookGenJob.status === "completed") {
      if (downloadedBookJobRef.current !== bookGenJob.id) {
        downloadedBookJobRef.current = bookGenJob.id;
        refreshProjectPlanAndIssues(activeProjectId);
        handleDownloadVerifiedBookPdf(activeProjectId);
      }
      return;
    }
    if (bookGenJob.status === "failed" || bookGenJob.status === "cancelled") {
      refreshProjectPlanAndIssues(activeProjectId);
      reloadActiveProject();
      return;
    }
    const timer = setInterval(async () => {
      try {
        const updated = await projectApi.getJob(bookGenJob.id);
        setBookGenJob(updated);
      } catch {
        // ignore
      }
    }, 600);
    return () => clearInterval(timer);
  }, [bookGenJob, activeProjectId, refreshProjectPlanAndIssues, handleDownloadVerifiedBookPdf, reloadActiveProject]);

  // Project Library actions (Step 1)
  const handleCreateNewProject = async () => {
    setError(null);
    try {
      const created = await projectApi.create({
        name: `Crossword Book ${projects.length + 1}`,
        project_type: "crossword",
        trim_size: projectTrimSize,
      });
      await refreshProjects(created.id);
      setStagedBatch(null);
      setPuzzle(null);
      setNotice("New project created.");
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleOpenProject = async (id: number) => {
    setError(null);
    await refreshProjects(id);
  };

  const handleDuplicateProject = async (id: number) => {
    setError(null);
    try {
      const dup = await projectApi.duplicate(id);
      await refreshProjects(dup.id);
      setNotice(`Duplicated project as "${dup.name}".`);
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleDeleteProject = async (id: number) => {
    setError(null);
    try {
      await projectApi.remove(id);
      const nextList = projects.filter((p) => p.id !== id);
      if (id === activeProjectId) {
        await refreshProjects(nextList[0]?.id);
      } else {
        setProjects(nextList);
      }
      setNotice("Project deleted.");
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleExportProjectJson = async (id = activeProjectId) => {
    if (!id) return;
    setError(null);
    try {
      const data = await projectApi.exportJson(id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      triggerBlobDownload(
        blob,
        `${(data?.name || projectName || "crossword_project").replace(/\s+/g, "_").toLowerCase()}.json`
      );
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleRestoreProjectJson = async (file: File) => {
    setError(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const restored = await projectApi.restoreJson(parsed);
      await refreshProjects(restored.id);
      setNotice(`Restored "${restored.name}" from backup.`);
    } catch (err) {
      setError(toPlainLanguageError(err, "Invalid project JSON backup file."));
    }
  };

  // Import actions (Section B)
  const handleStageFile = async (file: File) => {
    setError(null);
    setLoadingImport(true);
    setUploadProgress(20);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (importColName.trim()) fd.append("collection_name", importColName.trim());
      fd.append("first_line_is_title", firstLineIsTitle ? "true" : "false");
      setUploadProgress(60);
      const res = activeProjectId
        ? await projectApi.stageFile(activeProjectId, fd)
        : await apiRequest("/api/imports", { method: "POST", body: fd });
      setUploadProgress(100);
      setStagedBatch(res);
    } catch (err) {
      setError(toPlainLanguageError(err));
      setUploadProgress(0);
    } finally {
      setLoadingImport(false);
    }
  };

  const handleStagePaste = async () => {
    if (!pasteText.trim()) {
      setError("Paste at least one word before checking the import.");
      return;
    }
    setError(null);
    setLoadingImport(true);
    setUploadProgress(35);
    try {
      const payload = {
        text: pasteText,
        collection_name: importColName.trim() || "Pasted Words",
        first_line_is_title: firstLineIsTitle,
      };
      const res = activeProjectId
        ? await projectApi.stagePaste(activeProjectId, payload)
        : await apiRequest("/api/imports/paste", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
      setUploadProgress(100);
      setStagedBatch(res);
    } catch (err) {
      setError(toPlainLanguageError(err));
      setUploadProgress(0);
    } finally {
      setLoadingImport(false);
    }
  };

  const handleAcceptImport = async () => {
    if (!stagedBatch) return;
    setError(null);
    try {
      if (activeProjectId) {
        const res = await projectApi.acceptImport(activeProjectId, stagedBatch.id, true);
        setStagedBatch(null);
        setUploadProgress(0);
        if (res.project) loadProjectIntoState(res.project);
        setNotice("Word list imported into project chapters.");
      } else {
        const res = await apiRequest(`/api/imports/${stagedBatch.id}/commit`, { method: "POST" });
        setStagedBatch(null);
        setUploadProgress(0);
        if (res.collections?.length > 0) setActiveCollectionId(res.collections[0].id);
      }
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  // Clue actions (Section C)
  const handleStartClueGen = async (regenerate = false) => {
    if (!activeCollectionId) return;
    setError(null);
    try {
      const res = await apiRequest("/api/clues/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_id: activeCollectionId,
          mode: clueMode,
          difficulty,
          regenerate,
          verify: verifyClues,
        }),
      });
      const job = await projectApi.getJob(res.job_id);
      setActiveClueJob(job);
      refreshClueSummary(activeCollectionId);
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleSaveManualClue = async (wordId: number, advanceToNext = false) => {
    if (!editingClueText.trim()) return;
    setError(null);
    try {
      const prevItem = clueSummary?.items?.find((it: any) => it.word_id === wordId);
      if (prevItem?.active_clue?.id) {
        pushUndo({
          kind: "clue_restore",
          wordId,
          previousClueId: prevItem.active_clue.id,
          label: `clue edit for ${prevItem.answer}`,
        });
      }
      await apiRequest(`/api/words/${wordId}/clues`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: editingClueText.trim(), difficulty }),
      });
      if (advanceToNext && clueSummary?.items) {
        const idx = clueSummary.items.findIndex((it: any) => it.word_id === wordId);
        const nextItem = idx >= 0 ? clueSummary.items[idx + 1] : null;
        if (nextItem) {
          setEditingWordId(nextItem.word_id);
          setEditingClueText(nextItem.active_clue?.text || "");
        } else {
          setEditingWordId(null);
          setEditingClueText("");
        }
      } else {
        setEditingWordId(null);
        setEditingClueText("");
      }
      await refreshClueSummary();
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleRegenerateSingleClue = async (wordId: number) => {
    setError(null);
    try {
      const prevItem = clueSummary?.items?.find((it: any) => it.word_id === wordId);
      if (prevItem?.active_clue?.id) {
        pushUndo({
          kind: "clue_restore",
          wordId,
          previousClueId: prevItem.active_clue.id,
          label: `clue change for ${prevItem.answer}`,
        });
      }
      const res = await projectApi.regenerateWordClue(wordId, {
        difficulty,
        count: 3,
        verify: verifyClues,
        mode: clueMode,
      });
      setClueAltsByWord((prev) => ({ ...prev, [wordId]: res.alternatives || [] }));
      await refreshClueSummary();
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleSelectOrRestoreClue = async (wordId: number, clueId: number) => {
    setError(null);
    try {
      const prevItem = clueSummary?.items?.find((it: any) => it.word_id === wordId);
      if (prevItem?.active_clue?.id && prevItem.active_clue.id !== clueId) {
        pushUndo({
          kind: "clue_restore",
          wordId,
          previousClueId: prevItem.active_clue.id,
          label: `clue selection for ${prevItem.answer}`,
        });
      }
      await projectApi.selectWordClue(wordId, clueId);
      setClueAltsByWord((prev) => {
        const copy = { ...prev };
        delete copy[wordId];
        return copy;
      });
      await refreshClueSummary();
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleBulkApprove = async () => {
    if (!activeCollectionId) return;
    setError(null);
    try {
      await apiRequest("/api/clues/bulk-approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collection_id: activeCollectionId }),
      });
      await refreshClueSummary();
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  // Grid & Puzzle actions (Section D + Preview)
  const handleGenerateChapterPuzzle = async (seedOverride?: number) => {
    if (!activeCollectionId) return;
    setError(null);
    setGeneratingPuzzle(true);
    try {
      const effectiveSeed = seedOverride ?? (seedPinned ? seed : seed);
      const settings: any = {
        seed: effectiveSeed,
        strategy,
        symmetry,
        min_word_length: minWordLength,
      };
      if (gridMode === "custom") {
        settings.rows = customRows;
        settings.cols = customCols;
      }
      const p = await apiRequest("/api/puzzles/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_id: activeCollectionId,
          clue_mode: clueMode,
          difficulty,
          min_density: minDensity,
          auto_retry: !seedPinned,
          max_retries: 3,
          settings,
        }),
      });
      setPuzzle(p);
      await reloadActiveProject();
    } catch (err) {
      setError(toPlainLanguageError(err));
    } finally {
      setGeneratingPuzzle(false);
    }
  };

  const handleEditEntryClue = async (entryId: number, newText: string) => {
    if (!puzzle || !newText.trim()) return;
    setError(null);
    try {
      const prevEntry = puzzle.entries?.find((e: any) => e.id === entryId);
      if (prevEntry?.clue) {
        pushUndo({
          kind: "entry_clue_text",
          puzzleId: puzzle.id,
          entryId,
          previousText: prevEntry.clue,
          label: `entry clue for ${prevEntry.answer}`,
        });
      }
      const updated = await apiRequest(`/api/puzzles/${puzzle.id}/entries/${entryId}/clue`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newText.trim() }),
      });
      setPuzzle(updated);
      await refreshClueSummary();
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleRegeneratePuzzle = async (overrides?: any, undoLabel?: string) => {
    if (!puzzle) return;
    setError(null);
    setGeneratingPuzzle(true);
    try {
      if (overrides?.add_words?.length === 1 && !undoLabel) {
        pushUndo({
          kind: "puzzle_regenerate",
          puzzleId: puzzle.id,
          payload: { remove_words: [overrides.add_words[0].word] },
          label: `adding "${overrides.add_words[0].word}"`,
        });
      } else if (overrides?.remove_words?.length === 1 && !undoLabel) {
        const remAns = String(overrides.remove_words[0]).toUpperCase();
        const prevEntry = puzzle.entries?.find((e: any) => e.answer === remAns);
        pushUndo({
          kind: "puzzle_regenerate",
          puzzleId: puzzle.id,
          payload: {
            add_words: [{ word: remAns, clue: prevEntry?.clue || null }],
          },
          label: `removing "${remAns}"`,
        });
      } else if (overrides?.replace_words?.length === 1 && !undoLabel) {
        const rw = overrides.replace_words[0];
        const prevEntry = puzzle.entries?.find(
          (e: any) => e.answer === String(rw.old).toUpperCase()
        );
        pushUndo({
          kind: "puzzle_regenerate",
          puzzleId: puzzle.id,
          payload: {
            replace_words: [
              { old: rw.new, new: rw.old, clue: prevEntry?.clue || null },
            ],
          },
          label: `replacing "${rw.old}"`,
        });
      }

      const updated = await apiRequest(`/api/puzzles/${puzzle.id}/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(overrides || {}),
      });
      setPuzzle(updated);
      await reloadActiveProject();
    } catch (err) {
      setError(toPlainLanguageError(err));
    } finally {
      setGeneratingPuzzle(false);
    }
  };

  const handleInlineChapterAction = async (body: any) => {
    if (!puzzle) return;
    setError(null);
    setGeneratingPuzzle(true);
    try {
      if (activeProjectId && puzzle.collection_id) {
        const res = await projectApi.chapterAction(activeProjectId, puzzle.collection_id, body);
        setPuzzle(res.puzzle);
        setUnplacedEdits({});
        await reloadActiveProject();
      } else if (body.action === "edit_word") {
        await handleRegeneratePuzzle({
          replace_words: [{ old: body.old_word, new: body.new_word }],
          min_density: minDensity,
          auto_retry: true,
        });
      } else if (body.action === "remove_word") {
        await handleRegeneratePuzzle({
          remove_words: [body.old_word],
          min_density: minDensity,
          auto_retry: true,
        });
      } else if (body.action === "larger_grid") {
        const nextMax = (puzzle.settings?.engine?.max_size || 40) + 6;
        await handleRegeneratePuzzle({
          settings: { max_size: Math.min(60, nextMax) },
          min_density: minDensity,
          auto_retry: true,
        });
      } else {
        await handleRegeneratePuzzle({
          settings: { seed: (puzzle.winning_seed ?? puzzle.settings?.engine?.seed ?? 0) + 1 },
          min_density: minDensity,
          auto_retry: true,
        });
      }
    } catch (err) {
      setError(toPlainLanguageError(err));
    } finally {
      setGeneratingPuzzle(false);
    }
  };

  const handleUndo = async () => {
    const [top, ...rest] = undoStack;
    if (!top) return;
    setUndoStack(rest);
    setError(null);
    try {
      if (top.kind === "clue_restore") {
        await projectApi.selectWordClue(top.wordId, top.previousClueId);
        await refreshClueSummary();
      } else if (top.kind === "clue_text") {
        await apiRequest(`/api/words/${top.wordId}/clues`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: top.previousText, difficulty: top.difficulty }),
        });
        await refreshClueSummary();
      } else if (top.kind === "entry_clue_text") {
        const updated = await apiRequest(
          `/api/puzzles/${top.puzzleId}/entries/${top.entryId}/clue`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: top.previousText }),
          }
        );
        setPuzzle(updated);
      } else if (top.kind === "puzzle_regenerate") {
        const updated = await apiRequest(`/api/puzzles/${top.puzzleId}/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(top.payload),
        });
        setPuzzle(updated);
        await reloadActiveProject();
      }
      setNotice(`Undid ${top.label}.`);
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleDownloadSinglePuzzle = async (
    kind: "puzzle" | "clues" | "answer_key" | "puzzle_with_clues",
    format: "svg" | "pdf" | "png"
  ) => {
    if (!puzzle) return;
    setError(null);
    try {
      const blob = await apiDownload(`/api/puzzles/${puzzle.id}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          format,
          page: 0,
          force: true,
          settings: buildLiveExportSettings(),
        }),
      });
      triggerBlobDownload(blob, `${puzzle.title || "crossword"}_${kind}.${format}`);
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const goPrevChapter = useCallback(() => {
    if (chapters.length === 0) return;
    const prevIdx = activeChapterIndex > 0 ? activeChapterIndex - 1 : chapters.length - 1;
    setActiveCollectionId(chapters[prevIdx].id);
  }, [chapters, activeChapterIndex]);

  const goNextChapter = useCallback(() => {
    if (chapters.length === 0) return;
    const nextIdx = activeChapterIndex >= 0 && activeChapterIndex < chapters.length - 1 ? activeChapterIndex + 1 : 0;
    setActiveCollectionId(chapters[nextIdx].id);
  }, [chapters, activeChapterIndex]);

  // Step 4: Generate & Download Book PDF
  const handleGenerateAndDownloadBook = async (regenerate = false) => {
    if (!activeProjectId) return;
    setError(null);
    try {
      await projectApi.patch(activeProjectId, {
        name: projectName.trim() || "Untitled Crossword Book",
        project_type: projectType,
        trim_size: projectTrimSize,
        settings: buildAutosaveSettings(),
      });
      const started = await projectApi.generateAndDownload(activeProjectId, regenerate);
      downloadedBookJobRef.current = null;
      const jobState = await projectApi.getJob(started.job_id);
      setBookGenJob(jobState);
    } catch (err) {
      setError(toPlainLanguageError(err));
      await refreshProjectPlanAndIssues(activeProjectId);
    }
  };

  const handleCancelBookJob = async () => {
    if (!bookGenJob) return;
    setError(null);
    try {
      const updated = await projectApi.cancelJob(bookGenJob.id);
      setBookGenJob(updated);
    } catch (err) {
      setError(toPlainLanguageError(err));
    }
  };

  const handleRetryFailedChapters = async () => {
    if (!activeProjectId) return;
    setError(null);
    setRetryingFailedChapters(true);
    try {
      const res = await projectApi.retryFailedChapters(activeProjectId);
      if (res?.project) {
        loadProjectIntoState(res.project);
      }
      await refreshProjectPlanAndIssues(activeProjectId);
    } catch (err) {
      setError(toPlainLanguageError(err));
    } finally {
      setRetryingFailedChapters(false);
    }
  };

  return {
    step,
    setStep,
    canGoToStep,
    isStep1Valid,
    isStep2Valid,
    isStep3Valid,
    error,
    setError,
    notice,
    setNotice,
    projects,
    activeProjectId,
    chapters,
    activeCollectionId,
    setActiveCollectionId,
    activeChapter,
    activeChapterIndex,
    autosaveStatus,
    autosavedAt,
    projectName,
    setProjectName,
    projectType,
    setProjectType,
    projectTrimSize,
    setProjectTrimSize,
    customWidth,
    setCustomWidth,
    customHeight,
    setCustomHeight,
    customUnit,
    setCustomUnit,
    trimValidation,
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
    pasteText,
    setPasteText,
    importColName,
    setImportColName,
    stagedBatch,
    setStagedBatch,
    loadingImport,
    uploadProgress,
    clueMode,
    setClueMode,
    difficulty,
    setDifficulty,
    verifyClues,
    setVerifyClues,
    requireAllCluesApproved,
    setRequireAllCluesApproved,
    clueSummary,
    clueStatusFilter,
    setClueStatusFilter,
    clueAltsByWord,
    activeClueJob,
    editingWordId,
    setEditingWordId,
    editingClueText,
    setEditingClueText,
    gridMode,
    setGridMode,
    customRows,
    setCustomRows,
    customCols,
    setCustomCols,
    symmetry,
    setSymmetry,
    strategy,
    setStrategy,
    seed,
    setSeed,
    seedPinned,
    setSeedPinned,
    minWordLength,
    setMinWordLength,
    minDensity,
    setMinDensity,
    generatingPuzzle,
    availableFonts,
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
    titleEnabled,
    setTitleEnabled,
    titleMode,
    setTitleMode,
    firstLineIsTitle,
    setFirstLineIsTitle,
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
    puzzle,
    previewMode,
    setPreviewMode,
    previewZoom,
    setPreviewZoom,
    showMarginGuides,
    setShowMarginGuides,
    puzzleSvg,
    answerKeySvg,
    previewLoading,
    showAdvanced,
    setShowAdvanced,
    unplacedEdits,
    setUnplacedEdits,
    bookPagePlan,
    blockingIssues,
    blockingWarnings,
    bookGenJob,
    retryingFailedChapters,
    bookPdfFilename,
    undoStack,
    handleUndo,
    handleCreateNewProject,
    handleOpenProject,
    handleDuplicateProject,
    handleDeleteProject,
    handleExportProjectJson,
    handleRestoreProjectJson,
    handleStageFile,
    handleStagePaste,
    handleAcceptImport,
    handleStartClueGen,
    handleSaveManualClue,
    handleRegenerateSingleClue,
    handleSelectOrRestoreClue,
    handleBulkApprove,
    handleGenerateChapterPuzzle,
    handleEditEntryClue,
    handleRegeneratePuzzle,
    handleInlineChapterAction,
    handleDownloadSinglePuzzle,
    goPrevChapter,
    goNextChapter,
    handleGenerateAndDownloadBook,
    handleDownloadVerifiedBookPdf,
    handleCancelBookJob,
    handleRetryFailedChapters,
    refreshProjectPlanAndIssues,
  };
}

export type ProjectStudioState = ReturnType<typeof useProjectStudio>;
