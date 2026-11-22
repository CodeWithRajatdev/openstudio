export const DEFAULT_CONFIG = {
  sizing_mode: 'auto', rows: 15, cols: 15, max_rows: 40, max_cols: 40,
  horizontal: true, vertical: true, diagonal: true, reverse: false,
  attempts_per_size: 40, density_factor: 1.8,
  normalize: {
    remove_spaces: true, remove_hyphens: true, remove_apostrophes: true,
    strip_accents: true, allow_digits: false
  },
}

export const DIFFICULTY = {
  easy: { horizontal: true, vertical: false, diagonal: false, reverse: false, density_factor: 2.4 },
  medium: { horizontal: true, vertical: true, diagonal: true, reverse: false, density_factor: 1.9 },
  hard: { horizontal: true, vertical: true, diagonal: true, reverse: true, density_factor: 1.5 },
}

export const DEFAULT_LAYOUT = {
  page_width: 215.9, page_height: 279.4,
  // A. Page Settings
  margin: 15, margin_mode: 'edges', extra_margins: false,
  margin_top: 0, margin_right: 0, margin_bottom: 0, margin_left: 0,
  // C. Puzzle Settings
  cell_size: 9, min_cell_size: 3.5,
  grid_line_width: 0.25, grid_line_color: '#222222',
  cell_color: null, border_width: 0, border_color: '#000000',
  letter_color: '#000000', letter_size_ratio: 0.5,
  grid_font: 'Open Sans', grid_font_weight: 'normal', grid_font_style: 'normal',
  uppercase_letters: true,
  puzzles_per_page: 1, puzzle_align: 'center', puzzle_valign: 'top',
  // F. Title Settings
  title_enabled: true, title_mode: 'custom',
  title_text: 'Puzzle #PUZZLE_NUMBER', title_start_number: 1,
  title_font: 'Open Sans', title_size: 8, title_weight: 'bold', title_style: 'normal',
  title_color: '#000000', title_align: 'center', title_gap: 5,
  // D. Clues Settings
  clue_type: 'columns', clue_sort: 'short_long', clue_align: 'center',
  clue_font: 'Open Sans', clue_font_size: 4.2, clue_size_ratio: 0.03,
  clue_weight: 'normal', clue_style: 'normal', clue_color: '#000000',
  clue_line_height: 1.6, clue_columns: 3, clue_uppercase: true, clue_gap: 6,
  // E. Solution Settings
  solution_font: null, solution_font_weight: null, solution_font_style: null,
  solution_letter_size_ratio: null, solution_letter_color: null, solution_uppercase: null,
  solution_line_width: null, solution_line_color: null, solution_cell_color: null,
  solution_border_width: null, solution_border_color: null,
  solution_title_enabled: true, solution_title_text: 'Answer Key: TITLE',
  solution_title_font: null, solution_title_size: null,
  solution_title_weight: null, solution_title_style: null, solution_title_color: null,
  solution_align: 'center', solution_flow: 'row',
  highlight_color: '#d62839', highlight_width: null,
  // Page furniture
  background: null, footer_text: null, footer_size: 3.2,
  page_numbers: false, page_number_position: 'right',
  page_number_size: 3.2, page_number_color: '#444444',
}

export const DEFAULT_ANSWERS = {
  style: 'rounded_rect', perPage: 4,
}

export const WORD_COUNT_PRESETS = [5, 8, 10, 12, 15, 18, 20, 25, 30]

export const FONT_CHOICES = [
  ['Open Sans', 'Open Sans (Default)'],
  ['Arial', 'Arial'],
  ['Verdana', 'Verdana'],
  ['Trebuchet MS', 'Trebuchet MS'],
  ['Georgia', 'Georgia (Serif)'],
  ['Times New Roman', 'Times New Roman (Serif)'],
  ['Courier New', 'Courier New (Monospace)'],
  ['Comic Sans MS', 'Comic Sans MS'],
]

export const FONT_STYLES = [
  ['normal:normal', 'Regular'],
  ['bold:normal', 'Bold'],
  ['normal:italic', 'Italic'],
  ['bold:italic', 'Bold Italic'],
]

export const encodeFontStyle = (weight = 'normal', style = 'normal') =>
  `${weight === 'bold' ? 'bold' : 'normal'}:${style === 'italic' ? 'italic' : 'normal'}`

export const decodeFontStyle = (val = 'normal:normal') => {
  const [weight = 'normal', style = 'normal'] = String(val).split(':')
  return { weight: weight === 'bold' ? 'bold' : 'normal', style: style === 'italic' ? 'italic' : 'normal' }
}

// 1 BookBolt px = 0.0625 mm (so 4 px = 0.25 mm default grid line width)
export const PX_MM = 0.0625
export const mmToPx = (mm) => Math.round(((Number(mm) || 0) / PX_MM) * 10) / 10
export const pxToMm = (px) => Math.round((Number(px) || 0) * PX_MM * 1000) / 1000

export const HIGHLIGHTS = [
  ['rounded_rect', 'Rounded rectangle'], ['circle', 'Circle / ellipse'],
  ['line', 'Straight line'], ['highlight', 'Highlight overlay'],
]

export const CLUE_TYPES = [
  ['columns', 'Columns'],
  ['rows', 'Rows (left-to-right)'],
  ['inline', 'Inline paragraph'],
]

export const CLUE_SORTS = [
  ['short_long', 'Short to Long'],
  ['long_short', 'Long to Short'],
  ['alpha', 'Alphabetical (A–Z)'],
  ['random', 'Random'],
  ['file', 'Original file order'],
]

export const ALIGNMENTS = [
  ['left', 'Left'],
  ['center', 'Center'],
  ['right', 'Right'],
]

export const VALIGNMENTS = [
  ['top', 'Top'],
  ['middle', 'Middle'],
  ['bottom', 'Bottom'],
]

export const SAMPLE_CHAPTERS = [
  ['Chapter 1: Fruits', 'APPLE MANGO ORANGE BANANA GRAPE LEMON PEACH CHERRY PAPAYA GUAVA KIWI PLUM'],
  ['Chapter 2: Animals', 'TIGER LION ZEBRA ELEPHANT GIRAFFE MONKEY RABBIT PANDA DOLPHIN EAGLE FALCON TURTLE'],
  ['Chapter 3: Space', 'PLANET GALAXY COMET ROCKET ORBIT METEOR NEBULA SATELLITE ECLIPSE ASTEROID UNIVERSE TELESCOPE'],
]

// Standard interior trim sizes (millimetres).
export const BOOK_SIZES = [
  { id: '8.5x11', label: '8.5 × 11 in', w: 215.9, h: 279.4 },
  { id: '8x10', label: '8 × 10 in', w: 203.2, h: 254 },
  { id: '8.5x8.5', label: '8.5 × 8.5 in', w: 215.9, h: 215.9 },
  { id: '6x9', label: '6 × 9 in', w: 152.4, h: 228.6 },
  { id: '7x10', label: '7 × 10 in', w: 177.8, h: 254 },
  { id: '7.5x9.25', label: '7.5 × 9.25 in', w: 190.5, h: 234.95 },
  { id: '5.5x8.5', label: '5.5 × 8.5 in', w: 139.7, h: 215.9 },
  { id: '5.25x8', label: '5.25 × 8 in', w: 133.35, h: 203.2 },
  { id: '5x8', label: '5 × 8 in', w: 127, h: 203.2 },
]
