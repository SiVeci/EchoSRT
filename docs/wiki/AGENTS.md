# AGENTS.md

## What this repo is

This is the **EchoSRT GitHub Wiki** — documentation only. There is no source code, build system, tests, or lint commands here. The actual application source lives at `github.com/SiVeci/EchoSRT`.

EchoSRT is a subtitle translation pipeline: FastAPI (Python) + Vue 3 (CDN, zero-build) + FFmpeg + faster-whisper + LLM.

## Language

All docs are in Chinese. Write new content in Chinese to match existing pages.

## Doc structure

```
getting-started/   — install, quickstart, config reference
user-guide/        — audio extraction, speech recognition, LLM translation, media library
architecture/      — system overview, pipeline engine, WebSocket, state management
api-reference/     — REST API, WebSocket API, JS frontend API
deployment/        — Docker, GPU setup, NAS guides, proxy config
development/       — project structure, contribution guide, changelog
```

## Conventions

- `_Sidebar.md` must be updated when adding, moving, or renaming pages. It uses `[[Chinese page name]]` link format.
- Headings use inline SVG icons from `icons/`: `<img src="icons/xxx.svg" width="20" height="20" style="vertical-align:-3px">`
- Mermaid diagrams are used extensively in architecture docs.
- Internal cross-references use `[[Chinese page name]]` wiki-link syntax.
- Config reference lives in `getting-started/配置详解.md` — update it when config schema changes.
- `development/更新日志.md` is the changelog — add entries for each version.
