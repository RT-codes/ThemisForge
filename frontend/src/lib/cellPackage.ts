// Pure helpers for Settings, Cell package: the texts are stored as an edit only (empty = the built-in text), and the
// waits between retries are typed as one line of numbers.

/** The text to show in the editor: the edit, or the built-in text when nothing was changed. */
export function shownText(stored: string, builtIn: string): string {
  return stored.trim() ? stored : builtIn
}

/** What to store for an editor's text: nothing when it is the built-in text, so a better built-in one still reaches it. */
export function storedText(edited: string, builtIn: string): string {
  return edited.trim() === builtIn.trim() ? '' : edited
}

/** A rough size in tokens, so it is clear what a text costs in every prompt (about four characters each). */
export function approxTokens(text: string): number {
  return Math.ceil(text.trim().length / 4)
}

/** "30, 90, 180" to [30, 90, 180]; null when it is not a list of whole numbers of seconds. Empty is no retries. */
export function parseWaits(text: string): number[] | null {
  const parts = text.split(/[\s,]+/).filter(Boolean)
  const waits = parts.map((part) => (/^\d+$/.test(part) ? Number(part) : NaN))
  if (waits.some((wait) => Number.isNaN(wait) || wait > 3600) || waits.length > 10) return null
  return waits
}

export function formatWaits(waits: number[]): string {
  return waits.join(', ')
}
