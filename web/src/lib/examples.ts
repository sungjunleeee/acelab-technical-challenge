// Curated example briefs for the rotating placeholder + "examples" dialog.
// Mix of well-formed and short to show users the range the agent handles.

export const EXAMPLE_BRIEFS: { label: string; brief: string }[] = [
  {
    label: 'Hospital corridor',
    brief:
      'High-traffic hospital corridor that needs to meet infection control standards, LEED Silver minimum, and a calming aesthetic. Budget is mid-range.',
  },
  {
    label: 'Warm residential kitchen',
    brief:
      'Warm residential kitchen, FSC-certified cabinetry, child-safe finishes.',
  },
  {
    label: 'Recording studio',
    brief:
      'Recording studio control room, prioritize acoustic absorption and zero-VOC.',
  },
  {
    label: 'Open-plan tech office',
    brief:
      'Open-plan tech office floor, want to spec Mannington carpet, must be Cradle-to-Cradle.',
  },
  {
    label: 'Modern bathroom',
    brief: 'A nice modern bathroom.',
  },
  {
    label: 'Jargon-dense H&S spec',
    brief:
      'H&S corridor specs, IIC > 50, ASTM E84 Class A, no PVC, GBI Tier 2.',
  },
  {
    label: 'School cafeteria',
    brief:
      'Ultra-luxury feel but tight budget for a school cafeteria.',
  },
]

export function pickRandomExample(
  current?: string,
): { label: string; brief: string } {
  if (EXAMPLE_BRIEFS.length === 1) return EXAMPLE_BRIEFS[0]
  let next = EXAMPLE_BRIEFS[Math.floor(Math.random() * EXAMPLE_BRIEFS.length)]
  // Avoid landing on the same one twice in a row.
  while (current && next.brief === current) {
    next = EXAMPLE_BRIEFS[Math.floor(Math.random() * EXAMPLE_BRIEFS.length)]
  }
  return next
}
