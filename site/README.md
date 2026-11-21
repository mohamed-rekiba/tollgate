# Tollgate website

The page at https://mohamed-rekiba.github.io/tollgate/. It is one page, built with Vite, Vue 3, Tailwind CSS, and shadcn-vue components.

## Why it is built this way

The hero picture is the repository's own `docs/diagrams/how-it-works-dark.svg`, imported as it is. The diagram skill draws it from `docs/diagrams/src/how-it-works.json`, so the site and the README always show the same picture. Every fact on the page comes from the README and the plan: the commands in `src/content.ts`, the tiers in `src/sections/LanesSection.vue`.

## Start

```sh
cd site
npm install
npm run dev      # http://localhost:5173/tollgate/
npm run build    # writes dist/
```

## When it is published

The workflow `.github/workflows/pages.yml` builds and publishes the site on each push to main that changes `site/` or `docs/diagrams/`. In the repository settings, Pages must use "GitHub Actions" as its source.
