BridgeWork Brand Tokens

Palette (derived from the logo):
- Primary: #FF6A00 (orange)
- Secondary: #FF2A6D (magenta)
- Accent: #FFD300 (yellow)
- Light: #FF9E66
- Dark variants: #D45800, #E21F5A

Usage guidelines:
- Use `--brand-primary` for primary actions and emphasis.
- Use `--brand-secondary` for complementary interactive elements.
- Use `--brand-accent` for highlights and badges requiring attention.
- Buttons use a subtle gradient between `--brand-primary` and `--brand-secondary`.
- Ensure high contrast for text on brand backgrounds (use dark text where needed).

Files updated:
- `app/static/css/app.css` - design tokens updated to logo palette.
- `app/static/css/monday.css` - mapped tokens to the brand colors for consistent components.
- `app/static/css/brand-overrides.css` - button, card, form and navbar overrides using tokens.
- `app/templates/components/_navbar.html` - navbar styles updated to use brand accent and improved look.

Next steps:
- Visual QA across key pages (login, dashboard, projects, tasks, modal dialogs).
- Accessibility check for contrast and keyboard focus states.
- Iterate on spacing and component details based on screenshots.
