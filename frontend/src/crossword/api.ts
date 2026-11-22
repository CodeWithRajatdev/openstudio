import { toPlainLanguageError } from "./utils/errors";

export const API_BASE = import.meta.env.VITE_API_URL || "";

export interface FontOption {
  family: string;
  label: string;
  license: string;
}

export interface BlockingIssue {
  type: string;
  chapter_id?: number;
  chapter_name?: string;
  words?: string[];
  clue_ids?: number[];
  count?: number;
  message: string;
}

export interface ChapterQuality {
  density?: number;
  crossing_count?: number;
  needs_attention?: boolean;
}

export interface ChapterInfo {
  id: number;
  name: string;
  chapter_index: number;
  language: string;
  word_count: number;
  expected_word_count?: number | null;
  word_count_label?: string;
  status: string;
  clue_status?: string;
  missing_clue_words?: string[];
  unapproved_clue_count?: number;
  puzzle_id?: number | null;
  winning_seed?: number | null;
  winning_strategy?: string | null;
  hit_time_limit?: boolean;
  quality?: ChapterQuality;
  plain_errors?: string[];
}

export interface PagePlanChapter {
  chapter_id: number;
  chapter_number: number;
  chapter_name: string;
  title: string;
  start_page: number;
  puzzle_pages: number;
  word_count: number;
}

export interface PagePlan {
  front_matter_blank_pages: number;
  puzzle_pages: number;
  solution_pages: number;
  solutions_per_page: number;
  trailing_blank_pages: number;
  blank_pages: number;
  total_pages: number;
  start_puzzles_on_right_hand_page: boolean;
  solutions_start_page?: number | null;
  width_pt: number;
  height_pt: number;
  chapters: PagePlanChapter[];
}

export interface JobData {
  id: string;
  type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  total: number;
  completed: number;
  failed: number;
  remaining?: number;
  payload?: any;
  result?: any;
  error?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectSummary {
  id: number;
  name: string;
  project_type: string;
  trim_size: string;
  current_step?: number;
  chapter_count?: number;
  autosaved_at?: string | null;
}

export interface ProjectData {
  id: number;
  name: string;
  project_type: string;
  trim_size: string;
  current_step?: number;
  autosaved_at?: string | null;
  settings: Record<string, any>;
  chapters: ChapterInfo[];
  blocking_issues: BlockingIssue[];
  warnings?: BlockingIssue[];
  can_generate_and_download?: boolean;
  page_plan?: PagePlan | null;
}

async function _throwApiError(res: Response): Promise<never> {
  let rawMessage = "";
  try {
    const err = await res.json();
    if (typeof err?.detail === "string") {
      rawMessage = err.detail;
    } else if (err?.detail && typeof err.detail === "object") {
      rawMessage = err.detail.message || JSON.stringify(err.detail);
    } else if (typeof err === "string") {
      rawMessage = err;
    }
  } catch {
    rawMessage = await res.text().catch(() => "");
  }
  const friendly = toPlainLanguageError(
    rawMessage,
    "The request could not be completed. Please check your inputs and try again."
  );
  throw new Error(friendly);
}

export async function apiRequest<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) await _throwApiError(res);
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export async function apiDownload(path: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) await _throwApiError(res);
  return res.blob();
}

export async function apiFetchSvg(path: string, init?: RequestInit): Promise<string> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) await _throwApiError(res);
  return res.text();
}

export const projectApi = {
  list: () => apiRequest<ProjectSummary[]>("/api/projects"),
  create: (body: { name: string; project_type?: string; trim_size?: string; settings?: any }) =>
    apiRequest<ProjectData>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  get: (id: number) => apiRequest<ProjectData>(`/api/projects/${id}`),
  patch: (id: number, body: any) =>
    apiRequest<ProjectData>(`/api/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    apiRequest<void>(`/api/projects/${id}`, {
      method: "DELETE",
    }),
  duplicate: async (id: number): Promise<ProjectData> => {
    const exported = await projectApi.exportJson(id);
    return projectApi.restoreJson({
      ...exported,
      name: `${exported?.name || "Crossword Book"} (Copy)`,
    });
  },
  exportJson: (id: number) => apiRequest<any>(`/api/projects/${id}/export-json`),
  restoreJson: (payload: any) =>
    apiRequest<ProjectData>("/api/projects/import-json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  stagePaste: (
    id: number,
    body: { text: string; collection_name?: string; first_line_is_title?: boolean }
  ) =>
    apiRequest<any>(`/api/projects/${id}/imports/paste`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  stageFile: (id: number, fd: FormData) =>
    apiRequest<any>(`/api/projects/${id}/imports`, { method: "POST", body: fd }),
  acceptImport: (id: number, batchId: string, replaceExisting = true) =>
    apiRequest<any>(`/api/projects/${id}/imports/${batchId}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ replace_existing: replaceExisting }),
    }),
  chapterAction: (id: number, chapterId: number, body: any) =>
    apiRequest<any>(`/api/projects/${id}/chapters/${chapterId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  blockingIssues: (id: number) =>
    apiRequest<{
      blocking_issues: BlockingIssue[];
      warnings?: BlockingIssue[];
      page_plan?: PagePlan;
    }>(`/api/projects/${id}/blocking-issues`),
  regenerateWordClue: (wordId: number, body: any) =>
    apiRequest<any>(`/api/words/${wordId}/clues/regenerate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  selectWordClue: (wordId: number, clueId: number) =>
    apiRequest<any>(`/api/words/${wordId}/clues/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clue_id: clueId }),
    }),
  exportFonts: () => apiRequest<FontOption[]>("/api/export/fonts"),
  pagePlan: (id: number) => apiRequest<PagePlan>(`/api/projects/${id}/page-plan`),
  generateAndDownload: (id: number, regenerate = false) =>
    apiRequest<any>(`/api/projects/${id}/generate-and-download?regenerate=${regenerate}`, {
      method: "POST",
    }),
  downloadBookPdf: (id: number) => apiDownload(`/api/projects/${id}/download-pdf`),
  retryFailedChapters: (id: number) =>
    apiRequest<{ retried_chapters: number; project: ProjectData }>(
      `/api/projects/${id}/retry-failed-chapters`,
      { method: "POST" }
    ),
  getJob: (jobId: string | number) => apiRequest<JobData>(`/api/jobs/${jobId}`),
  cancelJob: (jobId: string | number) =>
    apiRequest<JobData>(`/api/jobs/${jobId}/cancel`, {
      method: "POST",
    }),
};
