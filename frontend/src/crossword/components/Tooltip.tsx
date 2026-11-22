import { HelpCircle } from "lucide-react";

interface TooltipProps {
  text: string;
  label?: string;
}

export function Tooltip({ text }: TooltipProps) {
  return (
    <span className="relative inline-flex items-center group ml-1 align-middle">
      <button
        type="button"
        aria-label="More information"
        title={text}
        className="text-slate-400 hover:text-slate-600 focus:outline-none focus:text-slate-700"
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 transition-opacity absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 w-60 rounded-lg bg-slate-900 text-white text-[11px] leading-snug p-2.5 shadow-lg z-30 font-normal normal-case"
      >
        {text}
      </span>
    </span>
  );
}
