# ADR 014: Stream the GitItGPT Final Answer over SSE

Status: Accepted
Date: 2026-07-01
Decision makers: TBD

## Context

Spec 012 shipped GitItGPT as a full-response chat: the client waits for the
entire bounded agentic loop — including the final LLM turn's complete text
generation — before anything is returned. For longer answers the user watches a
static "thinking" indicator for the whole generation time. Spec 013 asks for the
final answer to stream token-by-token instead, matching mainstream chat UX.

The technical difficulty: `ChatService`'s loop (spec 012 AC-2) alternates
tool-calling turns (invisible, synchronous, dispatched against
`git_it.tools.registry`) and a final content-only turn. Streaming naively would
require knowing, before a turn's response is complete, whether it will end up
being a tool-calling turn (never shown to the user) or the final answer (shown
live) — but that classification is only fully known once the turn's LLM call
finishes.

## Decision

**A turn commits to one mode from its first streamed chunk.** In practice
(litellm/Anthropic tool-calling streams), a turn's chunks are either all
content deltas or all tool-call deltas — never a mix within one turn. This lets
`ChatService.chat_stream()` forward each turn's text deltas to the caller AS
THEY ARRIVE, because by contract (documented on `ChatLLM.respond_stream` and
`StreamPart`) an implementation must never emit a text delta for a turn whose
assembled `LLMTurn` ends up carrying tool calls.

Given that contract:

- `ChatLLM` gains `respond_stream(system, messages, tools) -> Iterator[StreamPart]`
  alongside the existing `respond(...)` (spec 012, untouched). `StreamPart`
  carries either a `text_delta` or, as its last item, the fully assembled
  `LLMTurn` (same shape `respond()` returns).
- `ChatService.chat_stream()` reuses the identical bounded loop, dispatch, and
  repo-scoping as `chat()` — the only difference is text deltas are yielded
  live for the turn that turns out to have no tool calls.
- `LiteLLMChatClient.respond_stream()` calls `litellm.completion(..., stream=True)`
  and accumulates OpenAI-style incremental tool-call deltas (by index) while
  forwarding content deltas immediately.
- A new endpoint, `POST /api/repos/{repository_id}/chat/stream`, returns
  `text/event-stream`: `data:` frames carry `{"text_delta": ...}`, terminated by
  `event: done` or `event: error` (never a distinct HTTP error status, since
  headers/status are already committed once the stream opens). The existing
  non-streaming `POST /chat` is untouched, for compatibility.
- Frontend: `fetch()` + `response.body.getReader()` (not `EventSource`, which
  cannot send a POST body) parses SSE frames manually, replaces the "thinking"
  indicator with a live bubble on the first delta, and re-renders the
  accumulated text as sanitized Markdown (`renderMarkdown()`, ADR 013) on every
  delta. A 30-second silence timer (`AbortController`) treats a dropped
  connection as a failure rather than hanging forever.

## Consequences

### Positive

- Faster perceived response — verified live: a longer answer's text visibly grew
  across successive checks (1298 → 2601 characters) rather than appearing all
  at once.
- Zero change to the read-only, repo-scoped, turn-capped, injection-hardened
  guarantees of spec 012 — the streaming path reuses the exact same dispatch,
  system prompt, and turn cap; it only changes how the final turn's text
  reaches the client.
- The non-streaming endpoint stays available and untouched, so nothing that
  already depends on it (tests, any other future caller) needs to change.

### Negative

- A turn-commits-to-one-mode assumption is a real-world API behavior, not
  something `ChatService` can enforce in-process — a provider that violated it
  (mixed content+tool-call deltas in one turn) would leak partial text for what
  turns out to be a tool-calling turn. Mitigated by documenting the contract
  explicitly on `ChatLLM.respond_stream`/`StreamPart` and relying on
  litellm/Anthropic's actual behavior (verified live, not just unit-tested).
- Error handling is weaker than a normal HTTP error: a mid-stream failure can
  only be signalled via an SSE `event: error` frame inside a 200 response, not a
  distinct status code — any client that doesn't parse SSE framing would
  misread a failed request as successful.
- The frontend now hand-parses SSE (buffering, frame splitting) instead of using
  `res.json()`; more custom code than the non-streaming path, with no
  browser-native SSE-over-POST primitive to lean on.

### Neutral

- No data model change. No change to spec 012's non-goals other than lifting
  the streaming one.

## Alternatives considered

- **Stream every turn, including tool-calling activity** (e.g., surfacing
  "Searching commits…" live): rejected by the user in favor of the simpler
  scope — tool-calling turns stay invisible, exactly as the existing "thinking"
  indicator already covers them.
- **Replace the non-streaming endpoint entirely**: rejected — keeps existing
  tests and any other caller working unchanged; the frontend is the only
  caller and it now defaults to the streaming endpoint.
- **`EventSource` for the streaming transport**: rejected — `EventSource` only
  supports GET requests with no body, and the chat request needs a JSON body
  (message + history). `fetch()` + `ReadableStream` reading is the standard
  workaround for POST-based SSE.
- **Plain incremental text instead of SSE framing**: rejected in the spec's
  grilling — SSE's explicit `event:` framing gives a clean, typed way to signal
  `done` vs `error` inside a stream whose HTTP status is already committed;
  plain text would need an ad-hoc convention for the same thing.

## Security impact

- No new attack surface: the streaming path dispatches the exact same
  read-only, repo-scoped tools under the exact same system prompt and turn cap
  as spec 012's non-streaming path.
- No secret leakage mid-stream: `event: error` carries only a generic message;
  the raw exception is logged (type name only), matching the non-streaming
  endpoint's existing 503 behavior.
- Sanitization still applies on every re-render of the growing bubble
  (`renderMarkdown()`, ADR 013) — streaming does not bypass the sanitization
  boundary.

## Quality impact

- TDD across four batches, all red→green (627 baseline at spec 012 close →
  658 by the end of this spec):
  - Batch 01: `ChatLLM.respond_stream` contract + `ChatService.chat_stream`
    (`tests/unit/test_chat_service.py`).
  - Batch 02: `LiteLLMChatClient.respond_stream` (`tests/unit/test_litellm_chat_client.py`).
  - Batch 03: `POST /chat/stream` SSE endpoint (`tests/unit/test_api_chat.py`).
  - Batch 04: frontend SSE consumption (`tests/unit/test_api_static.py` — this
    codebase's established static-assertion pattern for frontend, no JS
    unit-test runner).
- Manual verification (Playwright, per this project's UI-testing mandate): a
  real, longer question against a real analyzed repository, confirming the
  answer bubble's text length grew across successive live checks rather than
  appearing atomically; confirmed in both themes; console free of new errors.

## Documentation impact

- `docs/specs/013-gitit-gpt-streaming.md` (Status: Implemented).
- `docs/getting-started.md` Ask subsection.
- `docs/specs/index.md`, `docs/adr/index.md` rows.

## Links

- docs/specs/013-gitit-gpt-streaming.md
- ADR 012 (the agentic loop this extends)
- ADR 013 (the sanitized-Markdown rendering the growing bubble reuses)
