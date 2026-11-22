import { useState } from "react";
import {
  BookOpen,
  Copy,
  FolderOpen,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useStudio } from "../context/ProjectStudioContext";
import { Tooltip } from "../components/Tooltip";

export function ProjectStep() {
  const {
    projectName,
    setProjectName,
    projectType,
    setProjectType,
    projects,
    activeProjectId,
    isStep1Valid,
    handleCreateNewProject,
    handleOpenProject,
    handleDuplicateProject,
    handleDeleteProject,
    handleExportProjectJson,
    handleRestoreProjectJson,
  } = useStudio();

  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Identity Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-5">
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Step 1: Project Identity
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Name your book and choose a project type. Settings and imported chapters save automatically to your local library.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div>
            <div className="flex items-center mb-1.5">
              <label
                htmlFor="project-type-select"
                className="text-xs font-medium text-slate-700"
              >
                Project Type
              </label>
              <Tooltip
                label="Project Type"
                text="Crossword Book projects organize chapters into interconnected grids, clues, answer keys, and a print-ready PDF."
              />
            </div>
            <select
              id="project-type-select"
              value={projectType}
              onChange={(e) => setProjectType(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white"
            >
              <option value="crossword">Crossword Book (American-style &amp; Free-form)</option>
            </select>
          </div>

          <div>
            <div className="flex items-center mb-1.5">
              <label
                htmlFor="project-name-input"
                className="text-xs font-medium text-slate-700"
              >
                Project Name
              </label>
              <Tooltip
                label="Project Name"
                text="Used as your book's library title and the downloaded PDF filename (<project-name>.pdf)."
              />
            </div>
            <input
              id="project-name-input"
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="e.g. Classic Nature Crosswords"
              className={`w-full border rounded-lg px-3 py-2 text-sm ${
                isStep1Valid ? "border-slate-300" : "border-red-400 bg-red-50/40"
              }`}
            />
            {!isStep1Valid && (
              <p className="text-xs text-red-600 mt-1">
                Enter a project name to continue to Trim Size.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Local Project Library */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-slate-700" />
              Project Library ({projects.length})
              <Tooltip
                label="Project Library"
                text="All saved books are stored locally in your database. You can open, duplicate, delete, or export JSON backups."
              />
            </h3>
            <p className="text-xs text-slate-500">
              Switch between saved books, duplicate templates, or export/restore portable `.json` backups.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleCreateNewProject}
              className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-medium px-3 py-2 rounded-lg flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" /> New Project
            </button>

            <label className="border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium px-3 py-2 rounded-lg flex items-center gap-1.5 cursor-pointer">
              <FolderOpen className="w-3.5 h-3.5" /> Restore JSON
              <input
                type="file"
                accept=".json,application/json"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleRestoreProjectJson(file);
                  e.target.value = "";
                }}
                className="hidden"
              />
            </label>
          </div>
        </div>

        {projects.length === 0 ? (
          <div className="border-2 border-dashed border-slate-200 rounded-lg p-8 text-center text-xs text-slate-500">
            No saved projects found yet. Click <b>New Project</b> to start your first book.
          </div>
        ) : (
          <div className="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden">
            {projects.map((p) => {
              const isCurrent = p.id === activeProjectId;
              const confirmingDelete = confirmDeleteId === p.id;
              return (
                <div
                  key={p.id}
                  className={`px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-sm ${
                    isCurrent ? "bg-amber-50/50" : "bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-slate-900 flex items-center gap-2">
                      <span className="truncate">{p.name}</span>
                      {isCurrent && (
                        <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-200 text-amber-950">
                          Active
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">
                      Trim: {p.trim_size}
                      {p.chapter_count !== undefined ? ` • ${p.chapter_count} chapters` : ""}
                      {p.autosaved_at
                        ? ` • Updated ${new Date(p.autosaved_at).toLocaleDateString()}`
                        : ""}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    {!isCurrent && (
                      <button
                        type="button"
                        onClick={() => handleOpenProject(p.id)}
                        className="bg-slate-900 hover:bg-slate-800 text-white px-3 py-1.5 rounded-lg font-medium"
                      >
                        Open
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => handleDuplicateProject(p.id)}
                      title="Make an independent copy of this project"
                      className="border border-slate-300 hover:bg-slate-100 text-slate-700 px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                    >
                      <Copy className="w-3.5 h-3.5" /> Duplicate
                    </button>

                    <button
                      type="button"
                      onClick={() => handleExportProjectJson(p.id)}
                      title="Download project backup as JSON"
                      className="border border-slate-300 hover:bg-slate-100 text-slate-700 px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                    >
                      <Save className="w-3.5 h-3.5" /> Save JSON
                    </button>

                    {confirmingDelete ? (
                      <div className="flex items-center gap-1.5 bg-red-50 border border-red-200 rounded-lg px-2 py-1">
                        <span className="text-red-800 font-medium">Delete?</span>
                        <button
                          type="button"
                          onClick={() => {
                            setConfirmDeleteId(null);
                            handleDeleteProject(p.id);
                          }}
                          className="bg-red-600 hover:bg-red-700 text-white px-2 py-0.5 rounded font-medium"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(null)}
                          className="text-slate-600 hover:text-slate-900 px-1.5 py-0.5"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteId(p.id)}
                        title="Delete project from library"
                        className="border border-red-200 hover:bg-red-50 text-red-600 px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" /> Delete
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
