import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";

interface MockConfig {
  chapters?: any[];
  blockingIssues?: any[];
  warnings?: any[];
  puzzle?: any;
}

function makeChapter(overrides: Partial<any> = {}) {
  return {
    id: 101,
    name: "Chapter 1: Animals",
    chapter_index: 0,
    language: "en",
    word_count: 15,
    expected_word_count: 15,
    word_count_label: "Expected 15, found 15",
    status: "Ready",
    clue_status: "complete",
    missing_clue_words: [],
    puzzle_id: 501,
    winning_seed: 7,
    winning_strategy: "longest",
    hit_time_limit: false,
    quality: { density: 0.42, crossing_count: 14, needs_attention: false },
    ...overrides,
  };
}

function makePuzzle(overrides: Partial<any> = {}) {
  return {
    id: 501,
    collection_id: 101,
    title: "Chapter 1: Animals",
    status: "complete",
    clue_status: "complete",
    rows: 13,
    cols: 13,
    grid: ["APPLE........"],
    entries: [
      {
        id: 1,
        number: 1,
        direction: "A",
        row: 0,
        col: 0,
        answer: "APPLE",
        display: "apple",
        length: 5,
        clue: "Crisp orchard fruit",
      },
    ],
    unplaced: [],
    needs_attention: false,
    quality_status: "Ready",
    quality: { density: 0.42, crossing_count: 14 },
    stats: { symmetry_ratio: 0.5 },
    validation: {
      valid: true,
      checks: {
        entries_are_maximal_runs: true,
        no_isolated_cells: true,
        all_letters_connected: true,
      },
    },
    diagnostics: {
      raw_checks: {
        entries_are_maximal_runs: true,
        no_isolated_cells: true,
      },
    },
    plain_errors: [],
    winning_seed: 42,
    winning_strategy: "longest",
    hit_time_limit: false,
    settings: { engine: { seed: 42, strategy: "longest" } },
    ...overrides,
  };
}

function makeProject(cfg: MockConfig = {}) {
  const chapters = cfg.chapters ?? [makeChapter()];
  const blocking_issues = cfg.blockingIssues ?? [];
  const warnings = cfg.warnings ?? [];
  return {
    id: 1,
    name: "Safari Crosswords",
    project_type: "crossword",
    trim_size: "6x9",
    current_step: 1,
    autosaved_at: "2026-11-16T15:00:00Z",
    settings: {
      words_per_chapter: 15,
      min_word_length: 3,
      enumeration_display: "formatted",
      trim: { preset: "6x9", custom_width: 6, custom_height: 9, custom_unit: "in" },
      page: {
        guideline_mode: "kdp",
        margin_top: 36,
        margin_bottom: 36,
        margin_left: 36,
        margin_right: 36,
        independent_margins: false,
        gutter: 18,
        start_puzzles_on_right_hand_page: false,
        show_page_numbers: true,
      },
      clues: {
        mode: "hybrid",
        difficulty: "medium",
        verify: false,
        capitalization: "sentence",
        ending_punctuation: "keep",
        show_length_hint: true,
        require_all_clues_approved: false,
      },
      grid: {
        mode: "auto",
        rows: 15,
        cols: 15,
        symmetry: "off",
        strategy: "auto",
        seed: 1,
        min_word_length: 3,
        min_density: 0.25,
      },
      appearance: {
        cell_size: 24,
        line_width: 0.75,
        line_unit: "pt",
        outer_border: true,
        cell_fill: "#FFFFFF",
        empty_cell_style: "black",
        number_size: 6.5,
        number_position: "top_left",
        number_font: "Open Sans",
        number_color: "#000000",
        font_family: "Open Sans",
        capital_letters: true,
      },
      clue_layout: {
        layout_mode: "columns",
        heading_style: "uppercase",
        font_family: "Open Sans",
        font_size: 9.5,
        color: "#000000",
        spacing: 2,
        sort: "number",
        show_length_hint: true,
        placement: "same_page",
      },
      solution: {
        per_page: 4,
        highlight_style: "bold",
        copy_appearance: true,
        font_family: "Open Sans",
        font_size: 10,
        color: "#000000",
      },
      title: {
        enabled: true,
        template: "Chapter {PUZZLE_NUMBER}: {CHAPTER_TITLE}",
        start_number: 1,
        font_family: "Open Sans",
        font_size: 16,
        color: "#000000",
        alignment: "center",
      },
    },
    chapters,
    blocking_issues,
    warnings,
    can_generate_and_download: blocking_issues.length === 0 && chapters.length > 0,
    page_plan: {
      front_matter_blank_pages: 0,
      puzzle_pages: Math.max(1, chapters.length),
      solution_pages: 1,
      solutions_per_page: 4,
      trailing_blank_pages: chapters.length % 2 === 0 ? 1 : 0,
      blank_pages: chapters.length % 2 === 0 ? 1 : 0,
      total_pages:
        Math.max(1, chapters.length) + 1 + (chapters.length % 2 === 0 ? 1 : 0),
      start_puzzles_on_right_hand_page: false,
      width_pt: 432,
      height_pt: 648,
      chapters: chapters.map((ch, idx) => ({
        chapter_id: ch.id,
        chapter_number: idx + 1,
        chapter_name: ch.name,
        title: ch.name,
        start_page: idx + 1,
        puzzle_pages: 1,
        word_count: ch.word_count,
      })),
    },
  };
}

function setupFetchMock(cfg: MockConfig = {}) {
  let projectState = makeProject(cfg);
  const puzzleState = cfg.puzzle ?? makePuzzle();
  const patchSpy = vi.fn();

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method || "GET").toUpperCase();

    const jsonResp = (data: any, status = 200) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
      });

    if (url.endsWith("/api/projects") && method === "GET") {
      return jsonResp([projectState]);
    }
    if (url.match(/\/api\/projects\/\d+$/) && method === "GET") {
      return jsonResp(projectState);
    }
    if (url.match(/\/api\/projects\/\d+$/) && method === "PATCH") {
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      patchSpy(body);
      projectState = {
        ...projectState,
        name: body.name ?? projectState.name,
        trim_size: body.trim_size ?? projectState.trim_size,
        settings: {
          ...projectState.settings,
          ...(body.settings || {}),
        },
        autosaved_at: "2026-11-16T15:05:00Z",
      };
      return jsonResp(projectState);
    }
    if (url.endsWith("/api/collections") && method === "GET") {
      return jsonResp(projectState.chapters);
    }
    if (url.endsWith("/api/export/fonts")) {
      return jsonResp([
        { family: "Open Sans", label: "Open Sans", license: "OFL-1.1" },
        { family: "Vera", label: "Bitstream Vera Sans", license: "Bitstream Vera" },
      ]);
    }
    if (url.match(/\/api\/projects\/\d+\/blocking-issues/)) {
      return jsonResp({
        blocking_issues: projectState.blocking_issues,
        warnings: projectState.warnings,
        page_plan: projectState.page_plan,
      });
    }
    if (url.match(/\/api\/projects\/\d+\/page-plan/)) {
      return jsonResp(projectState.page_plan);
    }
    if (url.match(/\/api\/collections\/\d+\/clues/)) {
      return jsonResp({
        collection_id: 101,
        collection_name: "Chapter 1: Animals",
        total_words: 1,
        covered_words: 1,
        clue_status: "complete",
        items: [
          {
            word_id: 1,
            answer: "APPLE",
            display: "apple",
            enumeration: "(5)",
            active_clue: {
              id: 11,
              text: "Crisp orchard fruit",
              source: "manual",
              status: "approved",
            },
            rendered_preview: "Crisp orchard fruit (5)",
            all_clues: [],
          },
        ],
      });
    }
    if (url.match(/\/api\/puzzles\/\d+$/) && method === "GET") {
      return jsonResp(puzzleState);
    }
    if (url.match(/\/api\/puzzles\/\d+\/export/)) {
      return new Response(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 432 648"><rect width="432" height="648" fill="#fff"/></svg>',
        { status: 200, headers: { "Content-Type": "image/svg+xml" } }
      );
    }
    return jsonResp({});
  });

  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, patchSpy };
}

describe("Phase 5: 4-Step Crossword Book Studio", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("enforces Step N of 4 navigation guards and removes the legacy Bulk screen", async () => {
    setupFetchMock({ chapters: [] });
    const user = userEvent.setup();
    render(<App />);

    // Must display "Step 1 of 4" and NOT have a Bulk Generation step
    expect(await screen.findByText(/Step 1 of 4/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bulk Generation/i })).not.toBeInTheDocument();

    const nameInput = screen.getByLabelText(/Project Name/i) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Safari Crosswords"));

    // Clearing project name makes Step 1 invalid -> Next disabled and Step 2 pill disabled
    await user.clear(nameInput);
    const nextBtn = screen.getByRole("button", { name: /^Next/i });
    expect(nextBtn).toBeDisabled();
    expect(screen.getByRole("button", { name: /2\.\s*Trim Size/i })).toBeDisabled();

    // Typing a valid project name enables advancing to Step 2
    await user.type(nameInput, "Ocean Crosswords");
    expect(nextBtn).toBeEnabled();
    await user.click(nextBtn);
    expect(await screen.findByText(/Step 2 of 4/i)).toBeInTheDocument();

    // Advance to Step 3
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    expect(await screen.findByText(/Step 3 of 4/i)).toBeInTheDocument();

    // With 0 chapters, Step 4 cannot be entered yet
    const step4Next = screen.getByRole("button", { name: /^Next/i });
    expect(step4Next).toBeDisabled();
    expect(screen.getByRole("button", { name: /4\.\s*Review/i })).toBeDisabled();
  });

  it("shows visible autosave indicator and debounced saves on edit", async () => {
    const { patchSpy } = setupFetchMock();
    render(<App />);

    const nameInput = (await screen.findByLabelText(/Project Name/i)) as HTMLInputElement;
    await waitFor(() => expect(nameInput.value).toBe("Safari Crosswords"));
    expect(screen.getByTestId("autosave-indicator")).toHaveTextContent(/Autosaved|Autosave ready/i);

    fireEvent.change(nameInput, { target: { value: "Updated Book Title" } });
    expect(screen.getByTestId("autosave-indicator")).toHaveTextContent(/Saving/i);

    await waitFor(() => expect(patchSpy).toHaveBeenCalled(), { timeout: 2500 });
    await waitFor(() =>
      expect(screen.getByTestId("autosave-indicator")).toHaveTextContent(/Autosaved/i)
    );
  });

  it("converts custom trim dimensions across in/mm/cm and validates bounds", async () => {
    setupFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/Step 1 of 4/i);
    await waitFor(() =>
      expect((screen.getByLabelText(/Project Name/i) as HTMLInputElement).value).toBe(
        "Safari Crosswords"
      )
    );
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await screen.findByText(/Step 2 of 4/i);

    await user.click(screen.getByRole("button", { name: /Custom Size/i }));
    const widthInput = screen.getByLabelText(/Custom Width/i) as HTMLInputElement;
    const heightInput = screen.getByLabelText(/Custom Height/i) as HTMLInputElement;
    const unitSelect = screen.getByLabelText(/Dimension Unit/i) as HTMLSelectElement;

    fireEvent.change(widthInput, { target: { value: "6" } });
    fireEvent.change(heightInput, { target: { value: "9" } });

    // Switch to mm -> 6 in = 152.4 mm, 9 in = 228.6 mm
    await user.selectOptions(unitSelect, "mm");
    expect(Number(widthInput.value)).toBeCloseTo(152.4, 1);
    expect(Number(heightInput.value)).toBeCloseTo(228.6, 1);

    // Switch to cm -> 15.24 cm × 22.86 cm
    await user.selectOptions(unitSelect, "cm");
    expect(Number(widthInput.value)).toBeCloseTo(15.24, 1);

    // Switch back to in and test invalid bound (< 3 in)
    await user.selectOptions(unitSelect, "in");
    fireEvent.change(widthInput, { target: { value: "2" } });
    expect(screen.getByText(/between 3\.0 and 12\.0 inches/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Next/i })).toBeDisabled();
  });

  it("hides raw validator checks behind the Advanced toggle in Step 3 live preview", async () => {
    setupFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/Step 1 of 4/i);
    await waitFor(() =>
      expect((screen.getByLabelText(/Project Name/i) as HTMLInputElement).value).toBe(
        "Safari Crosswords"
      )
    );
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await screen.findByText(/Step 3 of 4/i);

    // Wait for chapter puzzle diagnostics to load
    await screen.findByText(/Valid crossword grid/i);

    // Raw validator names and internal fields must NOT appear before expanding Advanced
    expect(screen.queryByText(/entries_are_maximal_runs/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no_isolated_cells/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hit_time_limit/i)).not.toBeInTheDocument();

    // Open Advanced toggle
    await user.click(screen.getByRole("button", { name: /Advanced/i }));
    expect(await screen.findByText(/entries_are_maximal_runs/i)).toBeInTheDocument();
    expect(screen.getByText(/no_isolated_cells/i)).toBeInTheDocument();
    expect(screen.getByText(/Winning seed/i)).toBeInTheDocument();
  });

  it("renders chapter status badges and disables Generate and Download while blocking list is non-empty", async () => {
    setupFetchMock({
      chapters: [
        makeChapter({ id: 101, name: "Ch 1", status: "Ready", clue_status: "complete" }),
        makeChapter({ id: 102, name: "Ch 2", status: "Missing clues", clue_status: "incomplete" }),
        makeChapter({ id: 103, name: "Ch 3", status: "Words won't fit", clue_status: "complete" }),
        makeChapter({ id: 104, name: "Ch 4", status: "Needs attention", clue_status: "complete" }),
        makeChapter({ id: 105, name: "Ch 5", status: "Invalid", clue_status: "incomplete" }),
      ],
      blockingIssues: [
        {
          type: "missing_clues",
          chapter_id: 102,
          chapter_name: "Ch 2",
          message: "Ch 2 is missing clues for: ZEBRA.",
        },
        {
          type: "needs_attention",
          chapter_id: 104,
          chapter_name: "Ch 4",
          message: "Ch 4 needs attention (unplaced words).",
        },
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/Step 1 of 4/i);
    await waitFor(() =>
      expect((screen.getByLabelText(/Project Name/i) as HTMLInputElement).value).toBe(
        "Safari Crosswords"
      )
    );
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    expect(await screen.findByText(/Step 4 of 4/i)).toBeInTheDocument();

    const reviewRegion = screen.getByTestId("review-step");
    expect(within(reviewRegion).getByText("Ready")).toBeInTheDocument();
    expect(within(reviewRegion).getByText("Missing clues")).toBeInTheDocument();
    expect(within(reviewRegion).getByText("Words won't fit")).toBeInTheDocument();
    expect(within(reviewRegion).getByText("Needs attention")).toBeInTheDocument();
    expect(within(reviewRegion).getByText("Invalid")).toBeInTheDocument();

    expect(
      within(reviewRegion).getByText(/Ch 2 is missing clues for: ZEBRA\./i)
    ).toBeInTheDocument();

    const downloadBtn = within(reviewRegion).getByRole("button", {
      name: /Generate and Download/i,
    });
    expect(downloadBtn).toBeDisabled();
  });

  it("enables Generate and Download in Step 4 when blocking issues list is empty", async () => {
    setupFetchMock({
      chapters: [makeChapter()],
      blockingIssues: [],
    });
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/Step 1 of 4/i);
    await waitFor(() =>
      expect((screen.getByLabelText(/Project Name/i) as HTMLInputElement).value).toBe(
        "Safari Crosswords"
      )
    );
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    expect(await screen.findByText(/Step 4 of 4/i)).toBeInTheDocument();

    const downloadBtn = screen.getByRole("button", { name: /Generate and Download/i });
    expect(downloadBtn).toBeEnabled();
  });

  it("debounces rapid font/styling changes and only fetches the active preview mode", async () => {
    const { fetchMock } = setupFetchMock();
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText(/Step 1 of 4/i);
    await waitFor(() =>
      expect((screen.getByLabelText(/Project Name/i) as HTMLInputElement).value).toBe(
        "Safari Crosswords"
      )
    );
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await user.click(screen.getByRole("button", { name: /^Next/i }));
    await screen.findByText(/Valid crossword grid/i);

    const getExportCalls = () =>
      fetchMock.mock.calls.filter(([input]) =>
        String(input).match(/\/api\/puzzles\/\d+\/export/)
      );

    // Wait for initial single-mode preview fetch (only puzzle_with_clues, NOT answer_key)
    await waitFor(() => expect(getExportCalls().length).toBeGreaterThanOrEqual(1));
    const initialBodies = getExportCalls().map(([, init]) => JSON.parse(String(init?.body || "{}")));
    expect(initialBodies.every((b) => b.kind === "puzzle_with_clues")).toBe(true);

    // Expand Section E (Puzzle Appearance) and rapidly toggle Grid Font
    await user.click(screen.getByRole("button", { name: /Puzzle Appearance/i }));
    const fontSelects = screen.getAllByRole("combobox");
    const gridFontSelect = fontSelects.find((el) =>
      Array.from((el as HTMLSelectElement).options).some((o) => o.value === "Vera")
    ) as HTMLSelectElement;
    expect(gridFontSelect).toBeTruthy();

    const callsBefore = getExportCalls().length;
    fireEvent.change(gridFontSelect, { target: { value: "Vera" } });
    fireEvent.change(gridFontSelect, { target: { value: "Open Sans" } });
    fireEvent.change(gridFontSelect, { target: { value: "Vera" } });

    // Rapid burst should collapse into a single debounced export request with Vera
    await waitFor(() => expect(getExportCalls().length).toBeGreaterThan(callsBefore));
    const latestBody = JSON.parse(
      String(getExportCalls()[getExportCalls().length - 1][1]?.body || "{}")
    );
    expect(latestBody.settings.font_family).toBe("Vera");
    expect(getExportCalls().length - callsBefore).toBe(1);
  });
});
