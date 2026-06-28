# ADR-0006: Docker ネットワーク分離

## Status
superseded-by ADR-0070（Docker を main から削除。git revert で復元可能）

## Date
2026-03-14

## Context
Ollama LLM をローカルホスト以外（Docker コンテナ）で動かす必要があった。しかし Ollama にはビルトインの認証機構がなく、ネットワークに露出すると任意のプロンプトを注入される。また、エージェントが外部 API（Moltbook）と通信する際に Ollama コンテナがインターネットに直接アクセスできる状態は不要。

## Decision
Docker Compose で2つのネットワークを構成:

- `internal`: agent ↔ ollama 通信専用（`internal: true`、インターネットアクセス不可）
- `external`: agent → Moltbook API 通信用

```
agent:    internal + external ネットワーク
ollama:   internal ネットワークのみ
```

追加の措置:
- 非root ユーザー (UID 1000)
- `OLLAMA_TRUSTED_HOSTS` env var でホスト名許可リスト拡張（Docker サービス名対応）
- `OLLAMA_MODEL` はフォーマット検証済み（インジェクション防止）
- setup.sh で初回のみ一時的にインターネット接続してモデルをダウンロード

## Alternatives Considered
- **Ollama をホスト側で動かし、agent のみ Docker 化**: ネットワーク分離の意味が薄れる。ホスト側の Ollama がインターネットに露出するリスクは残る
- **全コンテナを同一ネットワーク**: シンプルだが Ollama がインターネットに到達可能になる
- **VPN / mTLS**: 小規模プロジェクトには過剰

## Consequences
- Ollama は外部から完全に隔離。プロンプトインジェクションのネットワーク経路を遮断
- モデルのダウンロードは setup.sh の初回のみ（運用中はオフライン）
- `docker-compose.override.yml` で既存データディレクトリをバインドマウント可能
- healthcheck でコンテナの正常性を監視
