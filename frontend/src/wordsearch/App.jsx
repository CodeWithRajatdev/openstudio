import React from 'react'
import { BookOpen } from 'lucide-react'
import { useApp } from './store.jsx'
import Stepper from './components/Stepper.jsx'
import { Step1Project, Step2TrimSize } from './components/Wizard.jsx'
import PuzzleSettings from './pages/PuzzleSettings.jsx'
import ReviewProject from './pages/ReviewProject.jsx'

export default function App() {
  const { state } = useApp()
  const step = state.step || 1

  let Screen = Step1Project
  if (step === 2) Screen = Step2TrimSize
  else if (step === 3) Screen = PuzzleSettings
  else if (step >= 4) Screen = ReviewProject

  return (
    <div className="min-h-screen bg-slate-50">
      <div className={`mx-auto px-6 py-8 ${step === 3 ? 'max-w-[1600px]' : 'max-w-5xl'}`}>
        <header className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="text-indigo-600" size={24} />
            <div>
              <div className="text-base font-bold leading-tight">Woodpecker</div>
              <div className="text-xs text-slate-500">Word Search Studio</div>
            </div>
          </div>
          <div className="text-right text-xs text-slate-500">
            <div className="font-medium text-slate-700">{state.projectName}</div>
            {state.chapters.length > 0 && (
              <div>
                {state.chapters.length} chapters · {state.chapters.reduce((n, c) => n + c.words.length, 0)} words
              </div>
            )}
          </div>
        </header>

        <Stepper current={step} />
        <main className="min-w-0">
          <Screen />
        </main>
      </div>
    </div>
  )
}
