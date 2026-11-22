import React, { createContext, useContext } from "react";
import { ProjectStudioState, useProjectStudio } from "../hooks/useProjectStudio";

const ProjectStudioContext = createContext<ProjectStudioState | null>(null);

export function ProjectStudioProvider({ children }: { children: React.ReactNode }) {
  const value = useProjectStudio();
  return (
    <ProjectStudioContext.Provider value={value}>
      {children}
    </ProjectStudioContext.Provider>
  );
}

export function useStudio(): ProjectStudioState {
  const ctx = useContext(ProjectStudioContext);
  if (!ctx) {
    throw new Error("useStudio must be used inside a ProjectStudioProvider");
  }
  return ctx;
}
