# ADR-0062: 作成時コンテンツ検証ハンドシェイク（LLM 推論による求解）と、可視化を条件とする記録ゲート

## Status

accepted

## Date

2026-06-26

## Context

Moltbook は現在、`is_verified=false` のエージェントに対し、作成したコンテンツ（投稿・コメント・サブモルト）がプラットフォーム上で可視化される前に、難読化された数学チャレンジを解くことを要求する。作成レスポンス（HTTP 201）は `verification` オブジェクト `{challenge_text, verification_code, expires_at}` を約5分の有効期限つきで返し、エージェントは `challenge_text` を解いて `POST /api/v1/verify {verification_code, answer}` を送るまで `verification_status` が `pending` から `verified` に遷移しない。Trusted agent と admin はこの手順をバイパスする（作成レスポンスに `verification` オブジェクトを含まず、コンテンツは即座に可視化される）。本エージェントは `is_verified=false` であり、毎回の作成呼び出しでハンドシェイクを完了する必要がある。

既存コードは検証を扱っているように見えて、実際には沈黙のうちに発火を停止していた。確認可能なログ範囲（2026-05-22〜2026-06-25）で、すべての投稿（`posts_count=349`）とすべてのコメントが `verification_status=pending` のまま — 公開プロフィールから不可視、他エージェントからも取得不能 — であった一方、`POST /posts` と `POST /comments` は一貫して HTTP 201 を返し、サーバ側のカウンタは正常に増加していた。コードは自分が作成したコンテンツの `verification_status` を一度も読まなかったため、API の成功シグナルと Web 上の可視状態との乖離は検出されず、障害は完全にサイレントだった。

根本原因は、既存の検証コードと現行 API との間の3層のドリフトである。第1層は配線: 唯一の solve-and-submit 呼び出しがフィード読み取りループ内に置かれ、`post.get("verification_challenge")`（現行 API がフィード項目に決して載せないフィールド）をキーにしていた。ログ範囲全体で0回しか発火せず、`verification` オブジェクトを実際に運ぶ作成レスポンス側の経路は一度も検査されなかった。第2層はフィールド名: コードは `challenge.get("text")` と `challenge.get("id")` を読み、`{challenge_id, answer}` を送っていたが、現行 API は `challenge_text` と `verification_code` を返し、`{verification_code, answer}` を期待する。仮に配線が正しくても、すべてのフィールド参照は `None` を返していた。第3層はソルバ: 決定論的な難読化解除・解析ルーチンは均一な文字二重化形式（例: `"ttwweennttyy"` → `"twenty"`）向けに書かれており、大小交互・散乱記号（`[]^/-`）・分断された語間隔を組み合わせた現行形式（例: `"A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy"`）では `"Failed to parse"` を返した。いずれの層も単独では有効な `/verify` 送信を生成できなかった。

## Decision

1. **solve→POST `/verify` ハンドシェイクを全コンテンツ作成経路に配線する。** `post_pipeline._publish_post`、`feed_manager` のコメント経路、`reply_handler` がそれぞれ作成レスポンスから `verification` オブジェクトを読み、コンストラクタで注入された共有コールバック `Agent._handle_verification`（既存のコールバック注入パターン）を呼ぶ。`post_comment` はルートレベルの `verification` キーを返り値の comment dict に畳み込み、API が `"comment"` 配下にネストしてもレスポンスルートに置いてもゲートが発火するようにする。

2. **記録を可視化条件でゲートする。** 未検証の投稿・コメントは不可視であり、5分のチャレンジ窓が過ぎると回復不能になる。dedup マーカー（`mark_posted`, `own_post_ids`）、エピソード書き込み、`memory.record_post` / `memory.record_commented`、`NoveltyGate.record`、`actions_taken` は検証成功後にのみ実行する。レート制限カウンタ（`scheduler.record_post` / `scheduler.record_comment`）は `POST` 直後のままにする — サーバは検証結果に関わらずクォータを消費するため。Trusted-bypass レスポンス（`verification` オブジェクトを持たないもの）は素通りし、従来どおり記録する。

3. **求解は LLM 推論で行う — 決定論的解析でも制約付き抽出でもなく。** `solve_challenge` は raw な `challenge_text` を「段階的に推論せよ」プロンプトとともに LLM に渡す（`num_predict=3000` は生成長の目標ではなく寛大な上限、`drop_truncated=True` で打ち切り時は fail-closed）。解は生成出力中の最後の数値トークンを特定し、小数2桁に整形して得る。信頼境界は出力側にある: プラットフォームへ送られるのは `float` 解釈可能な数値のみであり、untrusted な `challenge_text` 経由で注入された命令は実行されず `None` へ fail-closed する。

4. **死んだフィードベースの検証経路を除去する。** `verification_challenge` のフィード分岐と `run_cycle` を通る配線を削除する。これらはログ履歴で0回しか発火しておらず、現行 API に対して発火し得ない。

5. **`client._request` チョークポイントに構造のみの API 計装を追加する。** 各 API 呼び出しは `logs/api-audit.jsonl` に1レコードを追記する: HTTP メソッド、正規化エンドポイント（数値 ID を `{id}` に置換）、HTTP ステータス、envelope のキー名、ホワイトリスト化した content-status フィールド（`verification_status`, `is_spam`, `is_deleted`; bool キャスト or サニタイズ済み）、soft-fail フラグ（HTTP 2xx だが本文 `success:false`）、サニタイズ済みサーバエラー文、`rate-remaining`。依存する envelope キーが欠落した場合に schema-drift `WARNING` を発火する（成功応答=2xx のみ。エラー応答の本文は error envelope なので照合しない）。本文の自由文は記録しないため、untrusted な外部コンテンツを運ぶエピソードログと異なり、このログは直接読んでも安全である。

6. **返信を `parent_id` でスレッド化する。** API は返信に `parent_id` を要求するが、従来は送られておらず、返信がトップレベルコメントとして投稿されていた。すべての返信 `POST /comments` 呼び出しでこのフィールドを含めるようにする。

## Alternatives Considered

### 決定論的な難読化解除・解析ソルバを拡張する

既存の均一文字二重化ハンドラに加え、大小交互＋散乱記号形式のケースを追加する。却下: 2つの形式は相反する正規化を要求する — 繰り返し文字の畳み込みは `"ttwweennttyy"` から `"twenty"` を復元するが、大小交互版では `"three"` → `"thre"` を破壊する。演算動詞の語彙は開放的であり、実際のチャレンジは未知の末尾ジャンク（`"<um> lxObqS tHiS"`）を運んできた — regex パイプラインなら詰まるが、LLM はプロンプトなしで捨てた。

### LLM による構造化抽出（`format=json {num1, op, num2}` でコード側で計算）

LLM に構造化 JSON オブジェクトを要求し、算術は Python で計算する。テスト結果で却下: 6問中3問を誤答した。`format=json` 制約は推論モデルの `<think>` ブロックを抑制し、chain-of-thought なしでは難読化された数字語を誤読する（`twenty`→10, `eighty`→8）。算術をコードで計算するのは正しい分離だが、そこに至るために推論ステップを抑制するとソルバが不安定になる。

### 即答を強制する（「数字だけ答えよ」）

LLM に中間ステップなしで素の数値を返させる。却下: これも chain-of-thought を抑制し、難読化解除済みの平文入力でさえ誤った算術を生んだ（`20+5`→27）。自由な推論の後に出力から数値を抽出するほうが、出力形式を制約するより信頼できる。

### `client.py` 内で検証を扱う

全 API 呼び出しが通る単一の HTTP チョークポイントに solve-and-submit ロジックを置く。却下: ソルバは LLM アクセスを要するが、`client.py` は LLM 参照を持たない純粋なトランスポートである。`client.py` に LLM を import すると [ADR-0015](./0015-one-external-adapter-per-agent.md) が定める `core` ← `adapters` の依存方向を逆転させる。`verification` オブジェクトは既にパイプライン層が解析する作成レスポンスに載って戻ってくるため、そこに追加の配線は不要。

### 観測のため API レスポンス本文を全量ログする

サイレント障害を発見可能にするため、レスポンス JSON 全体を記録する。却下: レスポンス本文には他エージェントの投稿・コメントテキストが含まれ、これは untrusted でプロンプトインジェクションの経路である。その内容を Claude Code が直接読めるファイルに書くと、エピソードログの読み取りを禁じる境界（CLAUDE.md）と同じものを侵食する。構造＋ステータスのログは、インジェクション面を導入せずに診断目的（2xx だが不可視の障害、envelope のフィールドドリフトの捕捉）を達成する。

### 検証を人間承認ゲートに通す

検証ハンドシェイクを、回答送信前に確認を要する監督対象アクションとして扱う。却下: 検証はコンテンツ可視化のために必要なプラットフォームの anti-bot ハンドシェイクであり、社会的・編集的アクションではない。ゲートすると、作成済みの投稿を監督するのではなく恒久的に不可視のまま残してしまう。コンテンツ生成は作成 `POST` の前に既存の novelty・確認ゲートを通過済みであり、検証ハンドシェイクはそれらのゲート通過後に実行される。

## Consequences

### Positive

- 投稿・コメント・返信が再び公開され、公開可視になる。本番に対する end-to-end 確認: 制御された実投稿がチャレンジ（`26+17=43`）を解いて `verification_status=verified` に遷移し、続く実ライブ自律セッションが実際の返信チャレンジを解いて `POST /verify` が HTTP 200 を返した。
- `logs/api-audit.jsonl` によりサイレント障害と API envelope ドリフトが grep 可能になる。本インシデントを起こした正確なバグクラス — HTTP 2xx でコンテンツが不可視のまま、レスポンス envelope のフィールド名ドリフト — は、数週間積み上がる代わりに数日以内に表面化していたはずである。
- 検証済み（可視）コンテンツのみが `NoveltyGate` とメモリストアに入るため、349件の pending 投稿と関連コメントが novelty・重複排除の履歴を汚染しなくなる。
- 返信がトップレベルコメントとしてではなく、親コメントの下に正しくスレッド化される。

### Negative

- 各コンテンツ作成呼び出しに、LLM がチャレンジを解く約30〜90秒のレイテンシが加わる。同じモデルが直前にコンテンツを生成しているため solve 時点では warm だが、cold または最近スワップされたモデルでは5分のチャレンジ窓に近づきうる（生成が pre-warm の役を果たす）。
- 検証ソルバはコンテンツ作成時点でローカル LLM が到達可能であることへの依存を加える。作成時に Ollama への接続が失敗すると `/verify` 呼び出しがスキップされ、作成済みコンテンツは pending のまま残る。
- 修正前の pending コンテンツ（349投稿＋同窓内に蓄積したコメント）は回復不能: チャレンジ窓は本修正のはるか前に失効しており、プラットフォームは再チャレンジ endpoint を提供しない。これは前方修正のみである。

### Neutral / Follow-ups

- ソルバプロンプトと `num_predict=3000` 予算は `qwen3.5:9b` 向けに較正されている。より弱いモデルやスワップされたモデルではプロンプトや予算の調整が必要になりうる。
- `logs/api-audit.jsonl` にはまだローテーションポリシーがない。API 呼び出しごとに1レコードを追記する。
- `verification_code` は送信前のフォーマット検証を行わなくなった: このフィールドは URL パスではなく JSON リクエストボディを通るため、非空チェックで十分である。従来の検証は古いフィールド名前提の遺物だった。

## References

- [ADR-0007](./0007-security-boundary-model.md) — セキュリティ境界モデル。全量レスポンス本文ログより構造のみの API ログを選んだ動機となった、untrusted コンテンツ面ポリシーとエピソードログ読み取り禁止。
- [ADR-0015](./0015-one-external-adapter-per-agent.md) — 1エージェント1外部アダプタ。LLM ソルバを `client.py` 内に置くことを排除した `core` ← `adapters` の import 方向。
- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — NoveltyGate。pending コンテンツが novelty 履歴を汚染しないよう、ゲートへの記録は検証成功を条件とする。
- [ADR-0043](./0043-per-post-seeding-for-self-post-generation.md) — per-post seeding と `check_topic_novelty` の除去。`own_post_ids` と関連 dedup マーカーは検証成功後にのみ記録する。
- 実装: コミット `92622e3`。
- `docs/CODEMAPS/architecture.md` Data Flow — 作成パイプラインの検証ハンドシェイクを反映するため同一コミットで更新。
- 関連 learned パターン: `llm-pipeline-layering` — 推論モデルは chain-of-thought を抑制してはならない。`format=json` が自由推論の100%に対し50%精度だった制約付き抽出タスクで経験的に検証済み。
