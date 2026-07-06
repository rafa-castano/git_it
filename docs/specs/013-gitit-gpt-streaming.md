# Feature Spec: 013 — GitItGPT Response Streaming

Status: Implemented
Owner: TBD
Primary agent: AI Development Flow Agent (supporting: Security Agent, Quality Agent)
Created: 2026-07-01
Updated: 2026-07-01

## Summary

Stream the GitItGPT (spec 012) assistant's **final answer** token-by-token to the
Ask tab as it is generated, instead of waiting for the full text and returning it
in one response. This reverses spec 012's explicit non-goal ("No streaming (SSE)
in this cut — full-response only. (Future spec.)").

Tool-calling turns (the model deciding to call `search_commits`, `get_patterns`,
etc.) remain synchronous and invisible, exactly as today — only the turn that
produces the final text answer streams.

## Problem

The existing `POST /api/repos/{repository_id}/chat` waits for the entire bounded
agentic loop to finish — including the final LLM turn's full text generation —
before returning anything. For longer answers this means the user stares at a
"thinking" indicator for the whole generation time, then the full answer appears
at once. Streaming the final turn's tokens as they arrive gives faster perceived
response and matches the UX of every mainstream chat product.

## Goals

1. Add a Server-Sent Events (SSE) endpoint,
   `POST /api/repos/{repository_id}/chat/stream`, that streams the final answer's
   text as it is generated.
2. Extend the `ChatLLM` contract with a streaming capability; a scripted fake
   drives deterministic, network-free tests exactly as spec 012 established.
3. Reuse the existing bounded tool-calling loop unchanged in shape: tool-calling
   turns are resolved synchronously and invisibly; only the turn with no tool
   calls (the final answer) streams its text deltas to the client as they arrive.
4. Signal success and failure explicitly within the SSE stream (`event: done`,
   `event: error`), since the HTTP status/headers are already committed once
   streaming starts and cannot change mid-stream.
5. Ask tab: replace the "thinking" indicator with live-updating text as the first
   delta of the final answer arrives; render as sanitized Markdown (ADR 013).

## Non-goals

- **No streaming of tool-calling activity** — tool-decision turns stay invisible,
  exactly as today's "thinking" indicator covers them. (Explicitly rejected by
  the user in favor of the simpler scope: only the final answer streams.)
- **No change to the existing non-streaming `POST /chat` endpoint** — it remains
  exactly as spec 012 shipped it, for compatibility and existing tests. The
  frontend switches to the new streaming endpoint; nothing else calls the old
  one differently.
- **No change to the turn cap, repo-scoping, read-only dispatch, or
  prompt-injection hardening** — all spec 012 AC-2/AC-3/AC-4 guarantees apply
  unchanged to the streaming path (it reuses the exact same dispatch and system
  prompt).
- **No reconnect/resume-on-drop support** — if the connection drops mid-stream,
  the partial text already rendered stays; the user re-asks. A future spec could
  add resumability.

## Users

Same as spec 012: the learner/engineer asking questions in the Ask tab, and the
maintainer who needs the same read-only/budget/injection guarantees to hold for
the streaming path.

## User stories

```md
As a user asking GitItGPT a question,
I want to see the answer appear as it's generated,
so that I don't stare at a "thinking" indicator for the full generation time.
```

```md
As a maintainer,
I want the streaming path to reuse the exact same repo-scoped, read-only,
turn-capped, injection-hardened tool-calling loop as the non-streaming path,
so that streaming does not open a second, less-guarded way to reach the model.
```

## Acceptance criteria

### AC-1 — `ChatLLM` streaming contract
- `ChatLLM` gains a streaming method (e.g. `respond_stream(system, messages,
  tools) -> Iterator[StreamPart]`) alongside the existing non-streaming
  `respond(...)`, which is left untouched.
- A `StreamPart` carries either a text delta (`text_delta: str`) for a
  content-only turn, or is silent (no delta emitted) while a turn is
  accumulating tool-call data; the iterator's last part carries the fully
  assembled `LLMTurn` (same shape `chat()` already uses) so the service can
  decide whether to dispatch tools or stop.
- A scripted fake `ChatLLM` implementing `respond_stream` (yielding a
  pre-programmed sequence of text deltas, then a final assembled `LLMTurn`)
  drives deterministic tests with no network, mirroring spec 012's testing
  approach for `respond(...)`.

### AC-2 — `ChatService.chat_stream(...)`
- Runs the identical bounded loop `chat()` already runs (turn cap, dispatch,
  repo-scoping) for every turn; turns whose assembled `LLMTurn` has tool calls
  are dispatched exactly as `chat()` does today — synchronously, invisibly, no
  delta forwarded to the caller.
- The turn whose assembled `LLMTurn` has no tool calls (the final answer) is the
  one turn whose text deltas are yielded to the caller as they arrive.
- Turn cap behaviour is unchanged: if the cap is hit before any turn produces a
  final (non-tool-calling) answer, the existing cap-note text is yielded as the
  (only) delta, then the stream ends — no silent hang.
- A regression test proves: (a) deltas from tool-calling turns are never
  yielded to the caller, (b) the concatenation of all yielded deltas for the
  final turn equals the same text `chat()` would have returned for the
  equivalent scripted turns, (c) repo-scoping/read-only dispatch/turn cap are
  identically enforced (reusing spec 012's existing regression tests' scenarios
  adapted to the streaming entry point).

### AC-3 — SSE endpoint
- `POST /api/repos/{repository_id}/chat/stream` accepts the same
  `{"message": str, "history": [...]}` body as the existing `/chat` endpoint,
  requires the same API key (`require_api_key`), and carries the same rate
  limit (20/minute).
- Response `Content-Type: text/event-stream`; each text delta is sent as an SSE
  `data:` frame; the stream ends with `event: done` on success or
  `event: error` (carrying a safe, generic message — never a raw exception) on
  failure. No secret or internal exception text ever reaches the client, mid-
  stream or otherwise (same non-negotiable as spec 012 AC-5).
- Unknown repository behaves like the non-streaming endpoint: tools return
  structured empty data, the assistant streams an answer saying it has no data;
  the connection still completes with `event: done` (not an error).

### AC-4 — Frontend: live-updating Ask transcript
- Submitting a question calls the new streaming endpoint; the "thinking"
  indicator (ADR-013-era feature) shows until the first text delta of the final
  answer arrives, then is replaced by a bubble that grows as deltas arrive.
- The growing bubble is re-rendered as sanitized Markdown (`renderMarkdown()`,
  ADR 013) on each delta (full re-parse of the accumulated text so far — no
  incremental-Markdown diffing); this is an explicit, documented assumption
  (see Open questions) rather than a hidden one.
- On `event: error`, the partial bubble (if any) stays, and the existing
  non-blocking `#ask-error` banner shows the same generic message as today's
  non-streaming failure path.
- On a dropped connection (network failure mid-stream, no `event: done` or
  `event: error` ever arrives), the UI treats it the same as an `event: error`
  after 30 seconds of silence — never hangs forever waiting on a silently-dead
  stream.

## Domain concepts

| Concept | Definition |
|---|---|
| Stream part | One increment from the streaming LLM call: either a text delta, or (as the final part) the fully assembled `LLMTurn` |
| Content-only turn | A turn whose assembled `LLMTurn` has no tool calls — the final answer, streamed to the client |
| Tool-calling turn | A turn whose assembled `LLMTurn` has tool calls — resolved synchronously and invisibly, exactly as `chat()` already does |
| SSE frame | One `data: ...\n\n` (or `event: ...\ndata: ...\n\n`) unit in the HTTP response body |

## Inputs and outputs

### Request
```json
POST /api/repos/{repository_id}/chat/stream
{ "message": "when did they start adding tests?",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}] }
```

### Response (`text/event-stream`)
```
data: {"text_delta": "Test"}

data: {"text_delta": " commits"}

data: {"text_delta": " first appear..."}

event: done
data: {}
```

On failure:
```
data: {"text_delta": "Base"}

event: error
data: {"message": "The assistant is temporarily unavailable."}
```

## Evidence requirements

Unchanged from spec 012: every claim in the streamed answer must be grounded in
real tool results (SHAs, dates, counts). A test verifies that when the scripted
fake LLM's tool-calling turn requests `search_commits`, the real seeded commits
are dispatched and available to the model before the final (streamed) turn is
requested — the streaming path must not skip or shortcut evidence-gathering.

## Failure modes

| Mode | Behaviour |
|---|---|
| LLM call fails before any delta was sent | `event: error` with a generic message; no partial bubble to worry about |
| LLM call fails after some deltas were already sent | Partial text stays rendered; `event: error` follows; the error banner shows, consistent with today's non-streaming failure UX |
| Turn cap reached with no final answer yet | The existing cap-note text streams as if it were the final answer, then `event: done` |
| Unknown repository | Tools return structured empty; assistant streams a "no data" answer; `event: done` (not an error) |
| Client disconnects mid-stream | Server-side generation may continue to completion or stop early depending on ASGI cancellation — either way, no dangling resources; nothing is written to any store (still fully in-memory, per-request) |
| Connection drops without a terminal event | Frontend treats 30s of silence as an explicit error |

## Security considerations

- **No new attack surface beyond spec 012's**: the streaming path dispatches the
  exact same read-only, repo-scoped tool functions, under the exact same system
  prompt and turn cap. Nothing new is exposed to the model or to tool dispatch.
- **No secret leakage mid-stream**: errors surfaced via `event: error` carry only
  a generic message, exactly like the non-streaming endpoint's 503 body — the
  raw exception is logged (type name only), never streamed to the client.
- **Sanitization still applies**: every re-render of the growing bubble goes
  through `renderMarkdown()` (`marked.parse()` + `DOMPurify.sanitize()`, ADR
  013) — streaming does not bypass the sanitization boundary.

## Privacy considerations

Unchanged from spec 012 — the same commit/analysis content is sent to the
configured LLM provider, now via a streaming API call instead of a blocking one.

## Observability

Unchanged from spec 012's per-request logging (repository_id, tool call count,
turns used, duration); streaming duration is measured from request start to the
terminal SSE event.

## Tests required

| Test | Location |
|---|---|
| Scripted-fake `respond_stream` drives `ChatService.chat_stream` end to end (tool turn → dispatch → final streamed turn) | `tests/unit/test_chat_service.py` |
| Tool-calling turn deltas are never yielded to the caller | `tests/unit/test_chat_service.py` |
| Turn cap reached mid-loop still terminates the stream with the cap note | `tests/unit/test_chat_service.py` |
| `LiteLLMChatClient.respond_stream` maps litellm's `stream=True` chunks to `StreamPart`s (monkeypatched, no network) | `tests/unit/test_litellm_chat_client.py` |
| `POST /api/repos/{id}/chat/stream` returns `text/event-stream`, requires API key, unknown repo completes with `event: done` | `tests/unit/test_api_chat.py` (or a new `test_api_chat_stream.py`) |
| `event: error` on LLM failure never leaks the raw exception | same |
| Frontend markup/JS static assertions (existing project pattern — no JS unit-test runner) | `tests/unit/test_api_static.py` |

All production code follows TDD: failing test first.

## Evaluation required

- Manual (Playwright, per this project's UI-testing mandate): ask a real
  question against a real analyzed repository and observe the answer appear
  incrementally rather than all at once; confirm the "thinking" indicator is
  replaced by the growing bubble at the first delta; confirm Markdown renders
  correctly once the stream completes, in both themes.

## Documentation impact

- `docs/specs/013-gitit-gpt-streaming.md` (this file).
- `docs/specs/012-gitit-gpt-chat.md`: remove/update the "No streaming (SSE)" line
  under Non-goals to point at this spec.
- `docs/getting-started.md` Ask subsection.
- `docs/prompt-contracts/gitit-gpt-system-prompt.md`: no change to the prompt
  itself, but note the output is now delivered incrementally.

## ADR impact

**New ADR**: "Stream the GitItGPT final answer over SSE." Captures: the
turn-classification-from-first-chunk design (a turn commits to tool-calls or
content from its first streamed chunk, never both), the choice to keep tool-
calling turns synchronous/invisible, SSE as the transport with explicit
`done`/`error` framing, and the decision to keep the non-streaming endpoint
as-is rather than replace it.

## Open questions

1. **Assumption, not asked**: the growing bubble is re-rendered via a full
   Markdown re-parse of the accumulated text on every delta (simplest, matches
   this codebase's existing no-incremental-diffing style) rather than
   incremental-safe Markdown streaming (which would need a streaming-aware
   Markdown parser). Flagging this now — acceptable unless it visibly flickers
   or is too slow once implemented and manually verified.
2. ~~Silence timeout for "connection dropped without a terminal event"~~ —
   **Resolved**: 30 seconds of no data before the frontend treats the stream as
   failed (confirmed).
