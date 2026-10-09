# Project overview concept

Standalone dashboard concept for discussion. It is intentionally isolated from the Themis app and uses illustrative placeholder data; it does not call the app API or change the shipped UI.

## Preview locally

From the repository root:

```bash
python3 -m http.server 4178 --directory design-drafts/project-overview
```

Then open <http://localhost:4178> in a browser. Stop the preview with `Ctrl+C`.

The **Customize** menu demonstrates hiding/showing the example widgets and remembers the selection in this browser. **Reset layout** clears that local draft preference. Other project actions are visual placeholders.

The bottom **Typography styles** menu is also draft-only. Its eight font and sizing presets, button behavior, and Google Fonts stylesheet are all contained in `index.html`; the actual app has no new imports, components, dependencies, or font changes. Google Fonts are loaded from the CDN for this preview, with system fallbacks. Deleting `design-drafts/project-overview/` removes the whole concept and its typography experiment.
