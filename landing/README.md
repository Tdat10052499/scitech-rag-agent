# Landing page

Static one-page site that introduces ASAP (Automated Scientific Aggregation Platform), the RAG agent: project name and slogan, how it works, features,
live demo link, evaluation results and team. Task: `docs/tasks/W8-D1-LDN-2-landing-page.md`.

- **Files:** `index.html` (HTML, CSS and JS inline) and `og-image.png` (1200 × 630 link preview).
  No build step, no `npm`, not part of CI.
- **Deploy:** GitHub Pages, by `.github/workflows/deploy-landing.yml` on every push to `main`
  that changes `landing/**`. It does not touch the Hugging Face Space or the chat app.
- **Libraries** (pinned, loaded from CDNs): GSAP 3.12.5 + ScrollTrigger (cdnjs), Lenis 1.1.13 and
  SplitType 0.3.4 (jsDelivr). Fonts: Newsreader, Inter, JetBrains Mono from Google Fonts.
- **Theme:** Auto (follows the system), Light or Dark, chosen in the nav; the choice is kept in
  `localStorage` (`asap-theme`). `prefers-reduced-motion` turns the animations off.

## Run locally

```bash
cd landing
python -m http.server 8090     # open http://localhost:8090
```

## Keep in sync

- **Colors and fonts** are copied from `frontend/src/ui/tokens.css` and `frontend/src/ui/fonts.ts`
  (approved design system, 2026-10-21). Pages publishes only this folder, so the page cannot
  import those files. When a token changes there, update the `:root` blocks here.
- **Numbers** on the page (corpus size, evaluation results, latency) come from the root `README.md`
  and `evaluation/RUNS.md` §7 (Week 7). Update both places together.
- **Examples** in the product preview, the retrieval ranking and the citation demo are illustrative,
  not recorded answers, and are labelled as such on the page.
- **Link preview** (Open Graph): the `og:url` and `og:image` tags in `index.html` hold the absolute
  Pages URL `https://tdat10052499.github.io/scitech-rag-agent/`. If the repository is renamed, the
  Pages URL changes too: update both tags. Check a preview with https://www.opengraph.xyz/ after deploy.
