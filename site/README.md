# mdbindery site

Static landing page and technical reference for `mdbindery` (`v0.2.0`, with EPUB and optional PDF export). Includes search metadata, coding-agent resources, and deployment helpers in `site/`.

## Files

- `index.html` — Semantic HTML5 landing page, JSON-LD (`SoftwareApplication`, `HowTo`, `FAQPage`, `WebSite`), Open Graph / Twitter Card metadata, Content-Security-Policy, progressive-enhancement install tabs (all panels readable without JS), EPUB/PDF validation overview, AI agent skill links, and live filter for all 59 `MB001`–`MB904` check codes.
- `styles.css` — Responsive dark/light theme stylesheet with primary controls above the 4.5:1 text-contrast threshold, `prefers-reduced-motion`, and sticky-header anchor offsets. Zero external font or CDN requests.
- `app.js` — Local script allowed by the CSP for theme toggle, WAI-ARIA tabs, clipboard copy buttons with selection fallback and `aria-live` announcements, and check-code filtering.
- `llms.txt` — Concise `llmstxt.org` index for AI agents and LLMs.
- `llms-full.txt` — Single-file reference containing CLI commands, flags, exit codes, `mdbindery.yaml` schema (`config.DEFAULTS` & `FILE_KEYS`), format-specific validation gates, and all 59 `MB` check codes.
- `agents.json` & `.well-known/agent.json` — Project-specific JSON capability manifest and discovery pointer.
- `robots.txt` — Catch-all crawl policy and `Sitemap:` pointer. Note: under a GitHub Pages project subpath (`https://sagol.github.io/mdbindery/`), crawlers read host-level `https://sagol.github.io/robots.txt`; `site/robots.txt` applies only when served from a custom domain root. Submit `https://sagol.github.io/mdbindery/sitemap.xml` directly in search consoles.
- `validate.py` — Checks configuration examples, runnable CLI snippets, diagnostic identifiers, JSON/JSON-LD, and local references against the current source.
- `stage.py` — Shared public-asset list and staging command for both deployment methods.
- `sitemap.xml` — XML sitemap for `https://sagol.github.io/mdbindery/`.
- `favicon.svg`, `og-image.svg`, `og-image.png`, `site.webmanifest`, `.nojekyll`.

## Local preview

Run local HTTP server from repository root:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open `http://localhost:8000`.

## Validate and stage

Use Python 3.9+ with the project dependencies installed. From the repository root:

```bash
python3 -m pip install .
python3 site/validate.py
node --check site/app.js
bash -n site/deploy-gh-pages.sh
python3 site/stage.py _site
```

Staging requires an empty destination and copies only `stage.PUBLIC_FILES`. The README, scripts, and workflow template are excluded. Preview `_site/` to review the published files.

The validator parses command examples without executing them. It checks the HTML and LLM configuration examples against the current schema, not the existence of example book files. It also checks diagnostic identifiers, local links, fragment IDs, ARIA/copy targets, the web manifest, sitemap XML, and JSON-LD. It does not check external URLs, every prose claim, or screen-reader behavior. Keep the optional PDF dependencies explicit. EPUB-only validation and byte-reproducibility claims must stay labeled.

Before release, inspect 320, 390, 768, and 1280 px layouts in both themes. Check keyboard tabs, filtering, clipboard rejection, no-JS instructions, reduced motion, and zoom. Full accessibility conformance needs a broader review than these checks.

## Publish to GitHub Pages

### GitHub Actions

1. Copy `site/github-pages-workflow.yml` to `.github/workflows/pages.yml`.
   - Uses commit-pinned actions (`checkout`, `configure-pages`, `upload-pages-artifact`, `deploy-pages`), separates read-only artifact preparation from deployment permissions, validates documentation against the CLI, and stages only public web assets (`_site/`).
   - Pull requests validate and stage without publishing. Source/schema changes also trigger validation after the template is installed.
2. In GitHub repository **Settings -> Pages -> Build and deployment**, set **Source** to `GitHub Actions`.

### Branch deployment (`gh-pages`)

1. Commit `site/` on `main`:
   ```bash
   git add site
   git commit -m "feat(site): add static documentation and landing site"
   git push origin main
   ```
2. Publish the committed public assets to `gh-pages`. Requires Python 3.9+, git, tar, and a configured git author identity. The script rejects dirty `site/` files, multiple push URLs, and destinations other than the exact GitHub repository `sagol/mdbindery` (HTTPS or Git SSH). It queries the push destination and uses `--force-with-lease`, including on first publication:
   ```bash
   bash site/deploy-gh-pages.sh
   ```
   The script stages from the captured commit, uses a temporary index, and creates no local branch. Publication replaces the `gh-pages` snapshot only if its remote head still matches the value observed before pushing. Both deployment methods use the same public-asset list.

3. In GitHub repository **Settings -> Pages -> Build and deployment**:
   - **Source**: `Deploy from a branch`
   - **Branch**: `gh-pages` / `/ (root)`

## Analytics

The page loads Google Analytics with measurement ID `G-GBGKWE1SCM`. The CSP allows the Google tag and Analytics endpoints using [Google’s configuration for Analytics without Ads features](https://developers.google.com/tag-platform/security/guides/csp#google_analytics). The inline initialization script is allowed by its SHA-256 hash; update that hash whenever the script content or whitespace changes.
