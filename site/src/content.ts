// Every fact on the page comes from the repository's README and plan.
export const REPO = 'https://github.com/tollgate-ai/tollgate'
export const blob = (path: string) => `${REPO}/blob/main/${path}`

export const INSTALL = [
  '/plugin marketplace add tollgate-ai/tollgate',
  '/plugin install tollgate@tollgate-ai',
  '/tollgate:init',
]

export const COMMANDS = [
  ['/tollgate:init', 'Sets up one project: the settings, the workflow, and the branch rules.'],
  ['/tollgate:task', 'Starts a task from your request, in the background.'],
  ['/tollgate:status', 'Shows two short lists: Done, and Still to do.'],
  ['/tollgate:inbox', 'Lists what waits for your decision, across projects.'],
  ['/tollgate:retro', "Shows a finished task's numbers and at most 3 lessons."],
  ['/tollgate:home', 'Keeps many projects in one private repository.'],
  ['/tollgate:docs', 'Writes docs, commits, and pull requests by the writing rules.'],
  ['/tollgate:diagram', 'Draws a diagram as an SVG file, in light and dark.'],
] as const
