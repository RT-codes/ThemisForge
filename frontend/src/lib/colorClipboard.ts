// Copying and pasting colours in the theme editor. A copy goes to the system clipboard (so a colour can be pasted into
// another app, or the other way round) and is also remembered here: the system clipboard is only reachable on secure pages
// (Themis is often opened over plain http on a LAN) and only with the browser's permission, and picking a swatch from the
// palette must work either way.

import { get, writable } from 'svelte/store'
import { isColor } from './colors.ts'

/** The colour last copied inside Themis, or picked up from the palette */
export const copiedColour = writable<string | null>(null)

export async function copyColour(value: string) {
	copiedColour.set(value)
	try {
		await navigator.clipboard.writeText(value)
	} catch {
		// the colour is still remembered above
	}
}

/** The colour to paste: what the system clipboard holds if that is a colour, else the one copied inside Themis; null when
 *  there is neither */
export async function pasteColour(): Promise<string | null> {
	try {
		const text = (await navigator.clipboard.readText()).trim()
		if (isColor(text)) return text
	} catch {
		// no clipboard access: use the remembered colour
	}
	const remembered = get(copiedColour)
	return remembered && isColor(remembered) ? remembered : null
}
