// The border-and-shine pulse (.nav-pulse in app.css): one place that plays it, from the first sidebar click to files
// that change on disk. Its colour and length can be set per element with --pulse-color and --pulse-ms.

/** plays the pulse on an element, and plays it again from the start if it is already running */
export function restartPulse(el: Element) {
  el.classList.remove('nav-pulse')
  void (el as HTMLElement).offsetWidth // lets the browser see it was removed, so the animation restarts
  el.classList.add('nav-pulse')
}

/** `use:pulseWhen={token}`: plays the pulse every time the token goes up (0 means never). */
export function pulseWhen(node: HTMLElement, token: number) {
  if (token) restartPulse(node)
  return {
    update(next: number) {
      if (next) restartPulse(node)
    },
  }
}
