# RFCs

この repo の提案と作業項目の公開台帳 — 1 エントリ 1 ファイル `NNNN-slug.md`、ID は
`RFC-NNNN`。フル RFC の提案から小さな作業項目まで同居する。**state は各ファイルの
frontmatter が唯一の正本**。

起票の手順と規約（足切り・採番・様式・公開規約）の正本は
[skill: rfc-writer](https://github.com/shimo4228/claude-harness/blob/main/skills/rfc-writer/SKILL.md)、状態語彙は
[skill: task-stocktake](https://github.com/shimo4228/claude-harness/blob/main/skills/task-stocktake/SKILL.md)、判断は
[claude-harness ADR-0049](https://github.com/shimo4228/claude-harness/blob/main/docs/adr/0049-unify-task-ledger-into-public-rfcs.md)。規約本文をこの README には書かない
（複製は drift する）。

| # | Title |
|---|---|
| [0001](0001-apple-foundation-models-backend.md) | Apple Foundation Models を生成 backend として挿すか |
| [0002](0002-axiom-removal-ab-experiment.md) | 公理除去 A/B 実験（distill 面の足場待ち） |
| [0003](0003-count-tokens-time-bound.md) | `count_tokens` に時間上限が無い |
| [0004](0004-distill-fragment-pattern-rate.md) | distill の断片パターン率 |
| [0005](0005-embedding-scaffold-expiry.md) | 機構層 embedding 依存の失効条件 |
| [0006](0006-heartbeat-end-state-criteria.md) | heartbeat 終了条件の具体化 |
| [0007](0007-finish-reason-truncation-gate.md) | `finish_reason` 非報告 backend で truncation ゲートが no-op になる |
| [0008](0008-instrument-read-at-event-boundaries.md) | 計器の読みを「比較が壊れる境界」で記録する |
| [0009](0009-ollama-real-token-counting.md) | Ollama に実トークン計数を挿す（上流待ち） |
| [0010](0010-weekly-report-content-redesign.md) | 週次レポート A–E の中身の再設計 |
| [0011](0011-submolt-scope-sweep-reading.md) | submolt スコープ sweep の読みと撤去判断 |
| [0012](0012-shadow-constitution-reading-consumption.md) | shadow 憲法計器の読み値を次回改正ゲートで消費する |
| [0013](0013-skill-family-promotion-to-rules.md) | skill family の共通姿勢を rule へ昇格する |
| [0014](0014-skill-selection-instrument-reading.md) | skill 選択計器の定期読み |
| [0015](0015-skill-name-hallucination-vs-catalog-size.md) | skill 名の幻覚率と catalog サイズの相関 |
| [0016](0016-restore-surprise-instrument.md) | surprise 計器の復元（ADR-0097 D1 の部分 supersede 候補） |
| [0017](0017-insight-extraction-redesign.md) | insight 抽出の再設計 — 頻度キー抽出に飽和と新規性の器官を与える |
| [0018](0018-self-post-seed-voice-label.md) | 自己投稿 seed ブロックに公開してよい voice ラベルを付ける |
| [0019](0019-weekly-session-value-layer-read.md) | 週次無人セッションの Read 許可に値層 4 パスを足す |
| [0020](0020-eval-baseline-staleness-standing.md) | eval baseline の STALE 警告が常設化している |
| [0021](0021-skill-stocktake-family-saturation.md) | skill-stocktake の再設計 — family 飽和の統合と weekly 定期化、天井は selector 幻覚率 |
| [0022](0022-wikiskill-fidelity-check.md) | WikiSkill 論文との整合性チェック（fresh context）+ replay paper アームの是正（≤ 8 件・15k 字 cap・Proposer turn 上限） |
| [0023](0023-novelty-gate-retrieval-and-rare-lane.md) | insight の novelty gate を候補検索（BM25 + nomic）に置き換え、希少レーンを持つ |
| [0024](0024-skill-extraction-free-body-split-calls.md) | skill 抽出の型を解く — 本文自由記述、frontmatter は別コール、長さは保存時拒否 |
| [0025](0025-retire-wiki-mechanism.md) | wiki 機構の退役（RFC-0017 D4〜D10 / RFC-0022 の閉鎖。gemma で平坦化、opus では機能） |
| [0026](0026-weekly-sample-splice.md) | 週次観察文書の `## Sample` 節を LLM の写経でなく pipeline の決定論的な差し込みにする |
| [0027](0027-experience-driven-skill-revision.md) | 経験に基づくスキル更新 — 再確認・修正・新規を区別する |
| [0028](0028-skill-outcome-recording.md) | skill の outcome 記録 — 環境の反応（返信 / upvote / スレッド継続）を comment id と selection log に結ぶ |
| [0029](0029-publish-failure-reason-code.md) | publish 失敗の理由コード — outcome 行に HTTP status と client 由来の reason code を足す（message 本文は入れない、ADR-0075 / 0083） |
| [0030](0030-rotate-log-lsof-path.md) | rotate-log.sh の open-writer ガードが backup job の launchd PATH（/usr/sbin 無し）で無効化されている |
| [0031](0031-knowledge-embedding-sidecar.md) | knowledge.json から 768 次元 embedding を別ストアへ出す（load 4.8s / save 2.7s / 189MB の根） |
| [0032](0032-feed-score-cache-per-cycle.md) | 同じ投稿がフィード TTL 内に ~10 回 LLM 採点される — 判定の重複を残すか消すか |
| [0033](0033-value-layer-due-check-load-gate.md) | value_layer_due_check の 180MB ロードゲートが恒真化し、毎週 ~1.5GB を払っている |
| [0034](0034-novelty-audit-kind-discriminator.md) | insight-novelty.jsonl に kind 判別子が無く、リプレイが deferral 行を verdict "None" と数える |
| [0035](0035-test-agent-names-in-follow-ranking.md) | fixture 名の除外リストが production の follow ランキングに埋まっている |
| [0036](0036-session-end-cycle-spin.md) | セッション終了直前に待ちが飛び、ループが毎秒 GET /home を叩いて空転する |
| [0037](0037-instrument-series-projection.md) | census の 30 行サンプルをセッション 1 行の表 + 週内外れ値 + 畳んだ窓に置き換え、時間の形をした未知の異常を週次で拾う |
| [0038](0038-reply-parent-rejected-requeue.md) | プラットフォームが恒久拒否した返信先（404 parent_rejected）が返信キューから出られず、毎セッション再生成される |
| [0039](0039-surprise-ref-window-pre-run.md) | insight の surprise 読み値が、run の窓 ≥ 1,000 行で全候補ぶん消える（mask と切り詰めの順序） |
| [0040](0040-jev-system-one-local-decision-backend.md) | Jev・ローカル判断モデルへの判断専用コールの置換と decision trace 蒸留の検討 |
| [0041](0041-memory-to-skill-pipeline-redesign.md) | 摂取経路（distill → insight → skills）を knowledge のスキーマから根本再設計する — 継ぎ当て RFC を 1 つの判断に束ねる |
| [0042](0042-insight-entrance-narrowing.md) | insight の入口を小さな変更で絞る — 判定コールの temperature 0 と enum 拘束、抽出前の名乗り、抽出後の重複判定 1 段（RFC-0041 の代わり） |
| [0043](0043-skillsel-offline-arm-replay.md) | skill selection を学習なし 5 arm（自由生成 / enum 拘束 / logits 読み / GLiClass / opus-5 天井）で offline 再生し、enum 修理の起票と蒸留へ進むかを読み 1 回で決める（RFC-0040 の子） |
| [0044](0044-skill-selector-temperature-zero.md) | skill selection の判断コールを temperature 0 にする（offline 150 行で幻覚 21〜29% → 7.3%、選択数と天井との一致は不変）。enum 拘束は第 2 段として受入条件つきで判断（RFC-0043 の帰結） |
| [0045](0045-relevance-judgment-jev-proximity-replay.md) | relevance 判定を Jev との近さで読む — ローカル判定器の第 2 面（submolt-scope 2,698 行の offline 再生） |
| [0046](0046-relevance-gate-score4-logprobs-shadow.md) | relevance gate を 4 段 Score の logprobs 読みに替える修理 — shadow → enforce の 2 段（RFC-0045 読み 3 の帰結、AUC 0.944 対 0.82、モデル交代なし） |
