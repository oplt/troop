# Troop — Product

`register: product`

Troop is an **ops workspace** for AI-assisted orchestration: people and agents plan work, run tasks, and approve outcomes. Design serves the job — clarity under load — not marketing spectacle.

## Users

| Persona | Opens Troop for | Cadence |
|---------|-----------------|---------|
| Operator / project lead | Advance projects, assign work, unblock tasks | Daily |
| Approver / reviewer | Clear pending agent/human approvals | Multiple times / day |
| Agent builder | Configure agents, skills, hierarchies, workflows | Weekly spikes |
| Admin | Models, integrations, platform settings, users | As needed |

Primary daily user = operator + approver. Builders and admins are secondary density.

## Jobs to be done

1. **See what needs me** — approvals, my tasks, projects at risk.
2. **Move a task forward** — open project → task → run agent / assign human → review output.
3. **Approve or reject** — scan queue → decide → next item.
4. **Shape the workforce** — agents, skills, team hierarchy, workflow templates.
5. **Trust the system** — cost, execution insights, audit trail when something fails.

**“Done” for a session:** inbox of actionable work cleared, or a specific project/task advanced with a clear next state (running, waiting approval, blocked, complete).

## Primary workflow

```
Project → Task → Run → Approve (or iterate) → Memory / artifacts
```

Secondary loops: Hierarchy/Teams builder → Agents/Skills → Marketplace; Workflows ↔ Workflow templates; Companies knowledge ↔ project memory.

## Tone

- Calm, precise, operational — engineered quiet, not playful.
- Verbs on actions (“Approve”, “Start run”); nouns on destinations.
- Prefer plain language in chrome; jargon (DAG, semantic memory, module pack) only where the surface is technical, with first-use hint.

## Anti-references

- Dashboard wallpaper of charts/stats with no “do next”.
- Flat mega-nav of every route at once.
- Marketing full-bleed photography heroes inside the authenticated app.
- Nested card stacks, purple glow, pill forests, decorative gradients.
- Inter / Roboto / system-only typography as the brand voice.

## Design registers (split)

| Doc | Role |
|-----|------|
| **PRODUCT.md** (this file) | Who, jobs, tone, IA priorities, product rules |
| **DESIGN.md** | Token inspiration (Tesla marketing site): color, radius, motion, flat elevation |
| **App chrome** | Product register: dense tools, semantic status colors allowed, progressive disclosure |

**Do not** copy DESIGN.md hero photography, 100vh gallery sections, or “Ask a Question” chat bar into the app shell. **Do** keep: Electric Blue CTA, carbon/graphite text, 4px radius, no shadows, 0.33s transitions, Display/Text split.

### Product typography (licensed substitute)

Universal Sans (in DESIGN.md) is proprietary. The app ships:

- **Display:** Space Grotesk — headings (`h1`–`h3`)
- **Text:** DM Sans — body, UI, buttons
- **Mono:** IBM Plex Mono — codes, IDs, metrics

Fallback stack after the primary family: `-apple-system, BlinkMacSystemFont, Arial, sans-serif`.

## Navigation IA (product)

Grouped destinations (not a flat list):

1. **Work** — Dashboard, Projects, My tasks, Approvals (`/approvals`)  
2. **Agents** — Agents, Skills, Marketplace, Hierarchy (`/hierarchy`)  
3. **Automate** — Workflows, Workflow templates, Integrations  
4. **Insight** — Portfolio (`/portfolio`), Cost & usage, Execution insights, Brainstorms (+ AI Studio when enabled)  
5. **Org** — Departments, Companies, Model settings  
6. **Admin** — Settings (admin only)

Default: only **Work** expanded. Insight and Org stay collapsed until the operator opens them or lands on a route in that group. Group expand/collapse persists locally.

Legacy bookmarks still work: `/activity` → `/approvals`, `/agent-portfolio` → `/portfolio`, `/hierarchy-builder` → `/hierarchy`.

### Shell shortcuts

- **Command palette:** Ctrl+K / ⌘K only (bare `K` disabled). Suggested actions, recent projects, pending approvals, runs, agents, skills, and pages; type a run id to jump to `/runs/:id`. Palette rows show product names — not raw UUID crumbs.
- **Notifications:** AppBar badge → `/notifications`.
- **Skip link:** “Skip to main content” focuses `#main-content`.
- **Module pack:** configured under Admin → Platform (not in drawer chrome).
- **Dense mobile surfaces:** Hierarchy, Project workspace, Run inspector show a mobile notice; secondary columns remain desktop-first.

## Success metrics (UX)

- New/returning operator answers “what should I do next?” from Dashboard in &lt;5s.
- Approve path from nav badge → decision ≤3 clicks.
- Project home → run/approve a task ≤3 clicks after Phase 3 detail split.
- Expanded nav: ≤7 top-level chrome items visible without scroll on 1080p (groups collapsed except Work + active).
