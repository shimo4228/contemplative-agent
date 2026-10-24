# Sibling conformance gate run — 2026-10-24

Command: `./scripts/check-sibling-backends.sh` (run from main at the commit named in `main=`; siblings checked out at origin/main as of that date).
Level: static only (the kit's runtime stage is not shipped — ADR-0088).

```
[sibling] ok      contemplative_agent_mlx.backends.mlx:MlxLmBackend sha=eb76250 main=v2.13.0-41-gaec9d8a level=static kit=2
[sibling] ok      contemplative_agent_cloud.backends.anthropic:AnthropicBackend sha=00e4d3e main=v2.13.0-41-gaec9d8a level=static kit=2
[sibling] ok      contemplative_agent_cloud.backends.openai:OpenAIBackend sha=00e4d3e main=v2.13.0-41-gaec9d8a level=static kit=2
[sibling] 3 checked, 0 absent, all conforming
exit=0
```
