# Tollgate website

The page at https://tollgate-ai.github.io/. It is one page, built with Vite, Vue 3, Tailwind CSS, and shadcn-vue components.

## Why it is built this way

The hero picture is the repository's own `docs/diagrams/how-it-works-dark.svg`, imported as it is. The diagram skill draws it from `docs/diagrams/src/how-it-works.json`, so the site and the README always show the same picture. Every fact on the page comes from the README and the plan: the commands in `src/content.ts`, the tiers in `src/sections/LanesSection.vue`.

## Start

```sh
cd site
npm install
npm run dev      # http://localhost:5173/
npm run build    # writes dist/
```

## When it is published

The repository tollgate-ai/tollgate-ai.github.io holds one workflow. It builds this folder from the main branch here and publishes it at https://tollgate-ai.github.io/. It runs once a day, and at once when someone presses "Run workflow" in that repository's Actions tab. So a change here shows up by the next day.
