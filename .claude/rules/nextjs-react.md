---
paths:
  - "website/**"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/app/**"
  - "**/components/**"
---

# Next.js 15+ & React 19 Rules (Claude Code)

- **Server-First Components**: Treat all components in `website/app/` as React Server Components (RSC) by default. Use `'use client'` strictly at leaf nodes for DOM event handlers (`onClick`, `onChange`), React hooks (`useState`, `useEffect`), or browser APIs.
- **Data Fetching**: Fetch data directly in Server Components using `await`. Avoid sequential async waterfalls by executing parallel fetches with `Promise.all()`.
- **Streaming**: Wrap dynamic page sections in `<Suspense fallback={<Skeleton />}>` to enable incremental streaming.
- **Server Actions**: Always validate incoming action payloads using Zod schemas before database execution or external dispatch.
- **Styling & Assets**:
  - Use Tailwind CSS 4 semantic variables (`bg-background`, `text-foreground`, `border-border`).
  - Use `next/image` with explicit `width` and `height` to prevent Cumulative Layout Shift (CLS < 0.05).
  - Use `next/font` for zero-shift font loading.
