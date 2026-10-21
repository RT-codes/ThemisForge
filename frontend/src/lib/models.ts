// Which models an agent or a workflow step can be given, and which reasoning efforts each accepts. The list itself
// comes from the backend (backend/app/harness.py CODEX_MODELS, served with /api/harnesses); this is the logic around it.

export interface ModelInfo {
  id: string
  label: string
  efforts: string[]
  default_effort: string
}

/** every effort a model can have, weakest first; a model supports some of them */
export const EFFORT_LABELS: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High', xhigh: 'Extra high', max: 'Max', ultra: 'Ultra' }
export const effortLabel = (effort: string) => EFFORT_LABELS[effort] ?? effort

/** a model that is not in the list was typed into an agent file or Settings: it can run, so it is shown as it is */
export const modelLabel = (models: ModelInfo[], id: string) => models.find((m) => m.id === id)?.label ?? id

/** the efforts a model accepts; one that is not in the list is trusted with all of them */
export function effortsOf(models: ModelInfo[], modelId: string): string[] {
  return models.find((m) => m.id === modelId)?.efforts ?? Object.keys(EFFORT_LABELS)
}

/**
 * The effort a run really gets, as the backend works it out (effort_for in harness.py): an effort the model does not
 * accept becomes the model's own default, because model and effort can come from different layers.
 */
export function effectiveEffort(models: ModelInfo[], modelId: string, effort: string): string {
  const known = models.find((m) => m.id === modelId)
  return known && !known.efforts.includes(effort) ? known.default_effort : effort
}

/** the effort to keep when the model changes: the same one while the new model accepts it, else back to inherited */
export function effortAfterModelChange(models: ModelInfo[], newModelId: string, effort: string): string {
  return !effort || effortsOf(models, newModelId).includes(effort) ? effort : ''
}
