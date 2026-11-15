# Hub web app

Before using ui-sdk, follow the ui-sdk skill (`.claude/skills/ui-sdk/` at the repo root) and read
`node_modules/@ui-sdk/react/docs/llms.txt`. To build a new component, also search
`node_modules/@ui-sdk/react/docs/core.md` by heading, and read `rendering.md` next to it.

- Screens use UI SDK only through the wrappers in `src/ui/` (a lint rule enforces it). Check each wrapper's parts
  against its component page in `docs/components/`.
- The agent bridge starts in `src/ui/agent.ts`; `src/ui/agent.test.tsx` is the agent test.
