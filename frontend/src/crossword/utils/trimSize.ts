export type TrimPresetId = "6x9" | "8x10" | "8.5x8.5" | "letter" | "a4" | "custom";
export type TrimUnit = "in" | "mm" | "cm";

export interface TrimPresetSpec {
  id: Exclude<TrimPresetId, "custom">;
  label: string;
  subtitle: string;
  widthIn: number;
  heightIn: number;
  widthMm: number;
  heightMm: number;
}

export const TRIM_PRESETS: TrimPresetSpec[] = [
  {
    id: "6x9",
    label: "6 × 9 in (Trade Paperback)",
    subtitle: "Most popular KDP pocket & trade puzzle book size",
    widthIn: 6.0,
    heightIn: 9.0,
    widthMm: 152.4,
    heightMm: 228.6,
  },
  {
    id: "8x10",
    label: "8 × 10 in (Workbook)",
    subtitle: "Roomy puzzles & easy-to-read large print clues",
    widthIn: 8.0,
    heightIn: 10.0,
    widthMm: 203.2,
    heightMm: 254.0,
  },
  {
    id: "8.5x8.5",
    label: "8.5 × 8.5 in (Square)",
    subtitle: "Balanced square layout for grid-focused books",
    widthIn: 8.5,
    heightIn: 8.5,
    widthMm: 215.9,
    heightMm: 215.9,
  },
  {
    id: "letter",
    label: "US Letter (8.5 × 11 in)",
    subtitle: "Standard North American workbook & classroom format",
    widthIn: 8.5,
    heightIn: 11.0,
    widthMm: 215.9,
    heightMm: 279.4,
  },
  {
    id: "a4",
    label: "A4 (210 × 297 mm)",
    subtitle: "International ISO standard print page",
    widthIn: 210 / 25.4,
    heightIn: 297 / 25.4,
    widthMm: 210,
    heightMm: 297,
  },
];

const INCHES_PER_UNIT: Record<TrimUnit, number> = {
  in: 1,
  mm: 1 / 25.4,
  cm: 1 / 2.54,
};

export function toInches(value: number, unit: TrimUnit): number {
  return value * INCHES_PER_UNIT[unit];
}

export function fromInches(inches: number, unit: TrimUnit): number {
  return inches / INCHES_PER_UNIT[unit];
}

export function convertDimension(value: number, fromUnit: TrimUnit, toUnit: TrimUnit): number {
  if (!Number.isFinite(value)) return 0;
  if (fromUnit === toUnit) return value;
  const converted = fromInches(toInches(value, fromUnit), toUnit);
  return Math.round(converted * 100) / 100;
}

export interface TrimValidationResult {
  valid: boolean;
  error: string | null;
  widthIn: number;
  heightIn: number;
  widthMm: number;
  heightMm: number;
  widthCm: number;
  heightCm: number;
  widthPt: number;
  heightPt: number;
}

export const MIN_TRIM_IN = 3.0;
export const MAX_TRIM_IN = 12.0;

export function validateTrimSize(
  preset: string,
  customWidth: number,
  customHeight: number,
  customUnit: TrimUnit
): TrimValidationResult {
  let widthIn: number;
  let heightIn: number;

  if (preset !== "custom") {
    const found = TRIM_PRESETS.find((p) => p.id === preset);
    widthIn = found ? found.widthIn : 6.0;
    heightIn = found ? found.heightIn : 9.0;
    return {
      valid: true,
      error: null,
      widthIn,
      heightIn,
      widthMm: Math.round(widthIn * 25.4 * 10) / 10,
      heightMm: Math.round(heightIn * 25.4 * 10) / 10,
      widthCm: Math.round(widthIn * 2.54 * 100) / 100,
      heightCm: Math.round(heightIn * 2.54 * 100) / 100,
      widthPt: Math.round(widthIn * 72 * 10) / 10,
      heightPt: Math.round(heightIn * 72 * 10) / 10,
    };
  }

  if (!Number.isFinite(customWidth) || !Number.isFinite(customHeight) || customWidth <= 0 || customHeight <= 0) {
    return {
      valid: false,
      error: "Please enter positive numbers for both page width and height.",
      widthIn: 0,
      heightIn: 0,
      widthMm: 0,
      heightMm: 0,
      widthCm: 0,
      heightCm: 0,
      widthPt: 0,
      heightPt: 0,
    };
  }

  widthIn = toInches(customWidth, customUnit);
  heightIn = toInches(customHeight, customUnit);

  let error: string | null = null;
  if (widthIn < MIN_TRIM_IN || widthIn > MAX_TRIM_IN || heightIn < MIN_TRIM_IN || heightIn > MAX_TRIM_IN) {
    error =
      "Page width and height must be between 3.0 and 12.0 inches (76.2–304.8 mm) so grids and clues print legibly.";
  }

  return {
    valid: error === null,
    error,
    widthIn: Math.round(widthIn * 100) / 100,
    heightIn: Math.round(heightIn * 100) / 100,
    widthMm: Math.round(widthIn * 25.4 * 10) / 10,
    heightMm: Math.round(heightIn * 25.4 * 10) / 10,
    widthCm: Math.round(widthIn * 2.54 * 100) / 100,
    heightCm: Math.round(heightIn * 2.54 * 100) / 100,
    widthPt: Math.round(widthIn * 72 * 10) / 10,
    heightPt: Math.round(heightIn * 72 * 10) / 10,
  };
}
