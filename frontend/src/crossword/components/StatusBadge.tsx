interface StatusBadgeProps {
  status: string;
}

const BADGE_CLASSES: Record<string, string> = {
  Ready: "bg-emerald-100 text-emerald-800 border-emerald-200",
  approved: "bg-emerald-100 text-emerald-800 border-emerald-200",
  complete: "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Missing clues": "bg-amber-100 text-amber-800 border-amber-200",
  needs_review: "bg-amber-100 text-amber-800 border-amber-200",
  incomplete: "bg-amber-100 text-amber-800 border-amber-200",
  "Needs attention": "bg-orange-100 text-orange-800 border-orange-200",
  "Words won't fit": "bg-red-100 text-red-800 border-red-200",
  Invalid: "bg-red-100 text-red-800 border-red-200",
  missing: "bg-red-100 text-red-800 border-red-200",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const cls =
    BADGE_CLASSES[status] || "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${cls}`}
    >
      {status}
    </span>
  );
}
