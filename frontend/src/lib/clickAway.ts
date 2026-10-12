// Clicking on empty space "lets go": a selection, or the task open in the panel. What counts as empty space is anything
// that is not a control, not a card, not part of the task panel, and not on top of a dialog or an open dropdown.

const BUSY = [
	'a', 'button', 'input', 'select', 'textarea', 'label', 'summary',
	'[role="button"]', '[role="tab"]', '[role="switch"]', '[role="checkbox"]', '[role="slider"]',
	'[role="menu"]', '[role="menuitem"]', '[role="listbox"]', '[role="option"]', '[role="toolbar"]',
	'[role="dialog"]', '[role="alertdialog"]', '[role="tooltip"]',
	'[data-task-panel]', // the task details panel
	'[data-keep-selection]', // anything else that must not let go (the board's scrollbar)
].join(',')

// Things that sit on top of the page while they are open. A click while one is open belongs to it, even when it lands on
// the page: it dismisses the dropdown (a click on empty space in the task panel must not also close the task).
const OPEN_LAYER = [
	'[role="dialog"]',
	'[role="alertdialog"]',
	'[role="listbox"]:not([data-state="closed"])',
	'[role="menu"]:not([data-state="closed"])',
	'[data-slot="popover-content"]:not([data-state="closed"])',
].join(',')

/** Whether this target is empty space. While a dialog or a dropdown is open nothing is: the click belongs to it. */
export function onEmptySpace(target: EventTarget | null): boolean {
	if (!(target instanceof Element) || !target.isConnected) return false
	if (document.querySelector(OPEN_LAYER)) return false
	return target.closest(BUSY) === null
}

/**
 * Calls `handler` for a click that both started and ended on empty space, so that dragging to select text inside the
 * panel and letting go outside it does not count. Returns what stops listening.
 */
export function onClickAway(handler: () => void): () => void {
	let startedOnEmpty = false
	const down = (e: PointerEvent) => (startedOnEmpty = onEmptySpace(e.target))
	const click = (e: MouseEvent) => {
		const was = startedOnEmpty
		startedOnEmpty = false
		if (was && onEmptySpace(e.target)) handler()
	}
	window.addEventListener('pointerdown', down, true)
	window.addEventListener('click', click, true)
	return () => {
		window.removeEventListener('pointerdown', down, true)
		window.removeEventListener('click', click, true)
	}
}
