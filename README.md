# rigsr-relay

**R**elay **I**nfrastructure for **G**it-Based **S**ession **R**outing

Communication layer to work with ChatGPT agents more dynamically via n8n and Beads.

## Overview

rigsr-relay is the communication backbone for the RIGSR agent system. It provides a structured, model-agnostic relay layer between n8n workflows and chat-based AI agents using GitHub as the shared medium.

The relay format is the contract — not the model. Any agent with repository access can participate regardless of provider.

## Repository Structure

```
rigsr-relay/
├── prompts/          — agent system prompts
├── context/          — context reference files
├── relay/
│   ├── inbox/        — n8n writes relay files here
│   └── outbox/       — agents write responses here
├── index/
│   ├── tags/         — function, rule, decision, context_shift tags
│   └── markers/      — session pointer files
└── logs/             — session logs (excluded from public repo)
```

## Relay File Format

All relay files are JSON with the following fields:

```json
{
  "relay_id":    "{from}{to}{year}{julian}{sequence}",
  "type":        "relay | message | archive",
  "from":        "originating agent id",
  "to":          "target agent id",
  "task":        "specific ask",
  "message":     "content body",
  "context":     "filename reference to context/ or null",
  "history":     "session ID + marker ID reference or null",
  "bead_id":     "bead ID if task-related (optional)",
  "task_update": "object: bead_id, status, note (optional)",
  "timestamp":   "ISO 8601",
  "status":      "pending | complete | archived"
}
```

## Message Lifecycle

```
n8n writes to inbox/        → status: pending
Agent responds to outbox/   → status: complete
Saul archives and indexes   → status: archived
```

## Agent Communication Flow

```
n8n writes relay to inbox/
        ↓
Chat agent reads via GitHub connector
        ↓
Chat agent writes response to outbox/
        ↓
n8n detects outbox write via GitHub webhook
        ↓
Routes to next agent or closes relay chain
```

## Log Capture

Session logs are captured in three tiers:

1. **Primary** — relay files capture all exchanges automatically
2. **Secondary** — share links written to logs/share_links/ on session end, pulled via archive.py if primary has gaps
3. **Last resort** — manual share link pull

Logs are excluded from this public repository via .gitignore.

## Contributors

- WA-Ladd — concept, design, architecture
- ChatGPT (OpenAI) — coding, foundation, archiving system,
  prior implementation work
- Claude (Anthropic) — coding, design collaboration, relay
  architecture, documentation

## Acknowledgements

This project would not exist without the foundational work of:

- **[n8n](https://n8n.io)** — the workflow automation backbone
  that makes agent routing possible. n8n's flexibility and
  self-hosted model are what makes an architecture like this
  feasible for independent developers.

- **[Beads](https://github.com/gastownhall/beads)** — the
  distributed graph issue tracker that gives RIGSR agents
  persistent, structured memory. Beads is released under the
  MIT License. This project builds on top of it with deep
  gratitude to the gastownhall team.

- **[Abacus](https://github.com/blackbxdev/abacus)** — the GUI
  layer that makes Beads actually usable day to day. Thank you
  to blackbxdev for building the interface that ties it together.

## License

This project is licensed under the MIT License — see LICENSE
for details.

Beads is independently licensed under MIT by gastownhall.
This project's MIT license covers rigsr-relay only and makes
no claim over Beads, Abacus, or n8n.
