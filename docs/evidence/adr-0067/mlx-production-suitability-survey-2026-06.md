# mlx_lm.server 本番運用適性 — 上流障害モードのサーベイ (2026-06)

> **この文書の位置づけ（ADR-0067 の補正ヘッダ）**
>
> これは mlx-lm エコシステムの上流障害モードを web 調査でまとめた **literature survey** である。
> 結論（無人本番は Ollama が正しい）は本環境の実測（[a-b-telemetry-2026-06-27.md](a-b-telemetry-2026-06-27.md)、
> [prefill-degradation-2026-06-27.md](prefill-degradation-2026-06-27.md)）と一致する。ただし本サーベイの
> caveat の一部は **本プロジェクトの環境には当てはまらない**。ADR-0067 本文に凍結しないよう、以下を明示的に補正する:
>
> 1. **モデル同一性（VLM caveat）は本環境では不成立。** 本サーベイは「`mlx-community/Qwen3.5-9B-4bit` は
>    マルチモーダル VLM で、model_type `qwen3_5` は mlx_lm.server で『Unsupported』として load 失敗しうる」
>    と警告する。しかし本環境の telemetry には実 model id `mlx-community/Qwen3.5-9B-4bit` のコールが
>    **21,143 件（12 時間、03:24Z〜15:08Z）記録されており、モデルは load して動いた**。本環境の故障は
>    load 失敗ではなく **runtime 劣化（circuit-breaker カスケード）**である。サーベイの web 調査が現実の別
>    Qwen3.5 系（マルチモーダル）と本プロジェクトが使う 4bit テキスト重みを混同した可能性が高い。
> 2. **truncation = EOS-runaway 説は本環境では不成立。** 本サーベイは障害モード 1 で truncation を MLX 固有
>    の EOS-runaway と関連づけるが、本環境の `verify_solve` A/B では MLX truncation は **n=5 のノイズで
>    solver 設計の既存性質**であり MLX 固有でないと判定済み。ADR-0067 は truncation でなく circuit-breaker
>    カスケードに立脚する。
> 3. **数値の出所。** 本サーベイ中の「21,143 / 26 ok」「19,520 / 2 ok」「48 error / 20,667」等は in-flight の
>    部分スナップショット。本環境の確定値は全期間再計算した **21,224 / 107 ok (0.50%)**（a-b-telemetry 参照）。
>
> 以下、サーベイ原文を保存する。上流 issue（#615 / #854 / #883 / #1292 等）の整理と wired-vs-pageable の
> 機序説明は、ADR-0067 の reversal threshold とメカニズム理解の根拠として有用。

---

## TL;DR

- **結論**：現時点（2026 年 6 月、mlx-lm v0.31.3）では、約 7.6k トークンのシステムプロンプトと連続生成を伴う無人本番運用に mlx_lm.server は**不適格**であり、上流の修正が出揃うまでは **Ollama（llama.cpp）が正しい選択**である。mlx-lm 公式の SERVER.md 自身が「The MLX LM server is not recommended for production as it only implements basic security checks」と明記し、maintainer awni も Discussion #371 で「mlx_lm.server is mostly intended to be used as a local HTTP endpoint. We don't currently have plans to expand beyond that」と述べている。
- **最重要の根本原因**：「停止しない」問題は単一原因ではなく、(a) 4bit 量子化による EOS 確率の低下、(b) mlx-lm 側の EOS/停止処理の既知欠陥、(c) 投機的デコード（MTP）での EOS 誤受理、(d) OpenAI 互換層が `stop` を受理するが内部実装にバグがある、の複合。最も確実な緩和は `stop: ["<|im_end|>"]` の明示送信、`--prompt-cache-bytes` による上限設定、量子化ビット数の引き上げ、そして in-process `mlx_lm.generate` の利用。
- **重大な前提のずれ（※本環境では不成立。上記補正ヘッダ参照）**：指定モデル `mlx-community/Qwen3.5-9B-4bit` は統合マルチモーダル（VLM）モデルの可能性があり、`qwen3_5` は mlx_lm.server で「Unsupported model type」として読み込み失敗する事例が報告されている。

## Key Findings（障害モード別の要約）

1. **EOS runaway（停止トークンを出さない）**：部分的に既知。mlx-lm/mlx-examples に EOS 関連の既知バグが複数（#973, #524, mlx-engine #12）。maintainer angeloskath は #973 を再現できていない。MTP 変種では #1292 として明確に再現し、投機的デコードが EOS を誤受理する逆方向（早期停止）の症状も確認。
2. **メモリ枯渇 → サーキットブレーカー連鎖**：既知の未解決問題（いずれも OPEN）。#854（Metal OOM で HTTP エラーを返さずプロセスごとクラッシュ）、#883（無制限の KV キャッシュ増大でカーネルパニック）。
3. **プリフィルの非線形クリフ**：メカニズムは Metal の wired メモリ＋ユニファイドメモリのメモリ圧で説明可能。Ollama 側の強い傍証（#16051：cold prefill が warm より 60〜400 倍遅い）あり。
4. **プロンプトキャッシュのチャーン**：設計どおりの挙動（バグではない）。サーバの LRUPromptCache は trie 構造で sequence 数・バイト数による LRU 追い出し。異なるシステムプロンプトの呼び出し者が 2 スロットを奪い合えば 0% ヒットは想定内。
5. **wired vs pageable メモリ**：一次情報および MLX 設計で裏付け。MLX は重みを共有/anonymous メモリに置き wired 化しスワップ不可、llama.cpp は GGUF を mmap でファイルバック（pageable）するため圧迫時の振る舞いが根本的に異なる。

## Details

### 障害モード 1：EOS runaway

EOS を出さず延々と生成する問題は mlx エコシステムで繰り返し報告されている。

- **mlx-lm #973**「TokenizerWrapper が eos_token_ids 配列を落とし会話用停止トークンが壊れる」。ただし maintainer はクリーン環境で再現せず、事実上 not-reproducible の公算。
- **mlx-examples #524**「The implementation of stop_criteria in mlx_lm.server is inherently flawed. Stop sequences only get matched when the newest tokens generated perfectly match a stop sequence.」停止列照合に構造的欠陥。
- **lmstudio-ai/mlx-engine #12**「(一部の) MLX モデルがほとんどの場合停止しない」。

根本原因仮説：(i) 4bit 量子化が EOS/`<|im_end|>` 確率を抑制（#1011 で 4bit ~5 ラウンド・8bit ~13 ラウンドで構造化 tool_use を喪失）、(ii) OpenAI 互換層が chat-template の EOS で停止しない（mlx-engine #337）、(iii) 投機的デコード/MTP（#1292、Qwen3.6 MTP で 1〜72 トークン早期停止）。

緩和：`stop: ["<|im_end|>"]` 明示送信（#524 により完全保証なし）、8bit（緩和するが根絶しない可能性、bf16 は 16GB に載らない）、in-process `mlx_lm.generate`（サーバ層迂回が最有力、ただし #1015 で generate() 自体に OOM 復旧パスなし）。

### 障害モード 2：メモリ枯渇 → サーキットブレーカー連鎖（既知の未解決、いずれも OPEN）

- **#854**：KV キャッシュが GPU メモリを超えると `[METAL] Command buffer execution failed: Insufficient Memory` でプロセスごと abort。起票者は「The server should catch the Metal out-of-memory error and return an HTTP 503 (or 500)」と要望。
- **#883**：`panic(...): 'completeMemory() prepare count underflow' @IOGPUMemory.cpp:550`。「the memory was wired (locked in RAM), macOS's Jetsam OOM killer couldn't reclaim it ... the wired memory bypassed the normal memory pressure monitoring system entirely」。
- **#1015**：persistent subprocess で ~14 時間後に Metal buffer cache が断片化し SIGABRT。`mx.clear_cache()` は解放するがデフラグしない。
- 部分緩和：PR #906 が `--prompt-cache-bytes` を追加。`--max-kv-size`（#615, OPEN）がサーバに無いことが根本。

### 障害モード 3：プリフィルの非線形クリフ

直接の mlx-lm Issue は弱いが、**ollama/ollama #16051** が強い傍証：「the first /api/chat request to a freshly loaded MLX bf16 model is 60–400× slower at the prefill stage than warm requests ... the same prompt against the GGUF Q4_K_M sibling ... completes cold prefill at 1,655 t/s — three orders of magnitude faster」。メモリが物理 RAM に収まっていても発生する点が重要。機序：メモリ圧が高まると macOS は wired 化された Metal アロケーションの周囲を圧縮/スワップしようとし、各推論がページ展開・圧縮解除コストを払う。

### 障害モード 4：プロンプトキャッシュのチャーン（設計どおり、バグではない）

DeepWiki の mlx-lm サーバ解説：「The LRUPromptCache stores KV caches in a trie structure with LRU eviction based on sequence count and byte size」。`--prompt-cache-size 2`（デフォルト 10）では、異なるシステムプロンプトの呼び出し者が 2 スロットを奪い合うと 7.6k トークンのプレフィックスは生存できず 0% ヒット → 毎回フルプリフィルは必然。LM Studio の mlx-engine は disk-backed KV キャッシュを実装済みだが mlx_lm.server は同等機能を持たない。

### 障害モード 5：wired vs pageable メモリ（一次情報および MLX 設計で裏付け）

- **llama.cpp Metal vs MLX 比較**：「llama.cpp は GGUF を mmap、カーネルがページを退避・再読込でき、物理メモリに収まらなくても OOM せずスワップで遅くなるだけ。MLX は MLX 配列にロードしデフォルトで mmap されず、物理メモリを超えるとスワップではなくハードな確保失敗」。
- 含意：軽い MLX（5.2GB）が重い Ollama（8.6GB）より他アプリと共存が悪い、という観測は、ファイルバック mmap（pageable, graceful）対 anonymous wired（reclaim 不可, ハードフェイル/パニック）という根本差で説明でき、観測と整合する。

## Recommendations（段階的）

**直ちに（本番は Ollama を継続）:** 無人・連続生成・約 7.6k システムプロンプトという要件下では Ollama（llama.cpp, GGUF Q4_K_M）を本番として維持する。

**MLX を評価継続する場合（ステージング）:** 全リクエストに `stop: ["<|im_end|>"]` を明示送信／`--prompt-cache-bytes` 設定 + `--prompt-cache-size` を distinct システムプロンプト数以上に／16GB 機では wired_limit を上げない（むしろ下げる）+ `clear_cache()` を長文生成後に定期実行／in-process `mlx_lm.generate` で A/B／8bit 検証。

**判断のしきい値（MLX 本番移行を再検討する条件）:** #615/#884（`--max-kv-size`）マージ／#854/#883 解決で OOM 時 HTTP 5xx・プロセス存続・カーネルパニック回避／標準 GQA テキスト LLM で 24 時間・数万コールの length truncation とエラーが Ollama 同等。これらが揃うまで Ollama を据え置く。

## Caveats（サーベイ自身が明示した限界）

- **モデル同一性**（※本環境では不成立、補正ヘッダ参照）。
- **数値の出所**：本サーベイ引用の各種数値は再現環境のテレメトリ（メカニズムは一次情報で裏付け、絶対値は環境固有）。本環境の確定値は a-b-telemetry を参照。
- **#973 の地位**：maintainer が再現できておらず不確実。runaway の主因は #973 単独でなく複合。
- **上流 PR のマージ状態**：#884/#906/#1306 の正確なマージ状態は間接ソース依存。確実なのは #615/#854/#883/#1292 が OPEN である点。
- **公式スタンス**：mlx_lm.server は SERVER.md・maintainer 発言ともに「ローカル用・本番非推奨」を明言。
