# API Reference

All endpoints are served under `/api/repos`. Protected endpoints require an `Authorization: Bearer <GIT_IT_API_KEY>` header.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/repos` | No | List all ingested repositories |
| `POST` | `/api/repos/ingest` | Yes | Start ingesting a repository by URL |
| `GET` | `/api/repos/{id}/commits` | No | Paginated commit list with analysis data |
| `POST` | `/api/repos/{id}/analyze` | Yes | Trigger LLM commit analysis |
| `GET` | `/api/repos/{id}/analyze/estimate` | No | Estimate LLM call count and cost before analyzing |
| `GET` | `/api/repos/{id}/analyze/status` | No | Poll analysis progress |
| `GET` | `/api/repos/{id}/patterns` | No | Detect engineering patterns |
| `GET` | `/api/repos/{id}/case-study` | No | Retrieve generated case study narrative |
| `GET` | `/api/repos/{id}/contributors` | No | List contributors with commit stats |

## Key request schemas

### `IngestRequest`

```json
{ "url": "https://github.com/owner/repo" }
```

Also accepts short form `"owner/repo"` — expanded to `https://github.com/owner/repo` automatically.

### `AnalyzeRequest`

```json
{
  "limit": 10,
  "model": "anthropic/claude-haiku-4-5-20251001"
}
```

`model` accepts any [LiteLLM provider string](https://docs.litellm.ai/docs/providers). The model must be in the configured allowlist.

## Key response schemas

### `IngestResponse`

```json
{
  "repository_id": "repo-abc123",
  "canonical_url": "https://github.com/owner/repo",
  "status": "INGESTING"
}
```

Ingestion runs in the background. Poll `GET /api/repos` to check when `status` changes to `COMPLETED`.

### `CommitsResponse`

```json
{
  "repository_id": "repo-abc123",
  "commits": [
    {
      "sha": "a1b2c3d",
      "message": "feat: add user auth",
      "committed_at": "2024-01-15T10:30:00",
      "category": "feature",
      "importance": "high",
      "summary": "Adds JWT-based authentication...",
      "affected_components": ["auth", "api"]
    }
  ],
  "total": 1
}
```

Query parameters: `limit` (default 20), `order` (`newest` or `oldest`).

### `AnalyzeEstimateResponse`

```json
{
  "total_commits": 250,
  "analyzed_commits": 50,
  "unanalyzed_commits": 200,
  "estimated_llm_calls": 20,
  "estimated_cost_usd": 0.016
}
```

### `AnalyzeStatusResponse`

```json
{
  "running": true,
  "done": 8,
  "total": 20,
  "pct": 40
}
```

## Rate limiting

Protected write endpoints are rate-limited per IP:

- `POST /api/repos/ingest` — 5 requests per minute
- `POST /api/repos/{id}/analyze` — 10 requests per minute

Exceeding the limit returns `HTTP 429 Too Many Requests`.
