# Security Review Checklist

- What untrusted inputs are processed?
- Can repository content influence tool calls?
- Is untrusted code executed?
- Are URLs validated?
- Are credentials least-privilege?
- Are secrets redacted from logs?
- Are MCP permissions documented?
- Is filesystem access scoped?
- Are LLM outputs schema-validated?
- Are dependencies scanned?
- Is there a safe failure mode?
- Are security-related claims evidence-grounded?
