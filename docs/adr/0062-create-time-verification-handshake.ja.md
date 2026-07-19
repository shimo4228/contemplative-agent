# ADR-0062: 作成時コンテンツ検証ハンドシェイク（LLM/コード併用ソルバ）と、可視化を条件とする記録ゲート

## Status

accepted

2026-06-28 amendment: 検証ソルバは、bounded LLM 推論の前に、LLM が出した短い数式をコード側で検算する
guarded extraction を試す。作成時ハンドシェイクと検証成功後にのみ記録するゲートは不変。同日の第2 amendment
として、solver 評価用の base64 challenge/outcome corpus である
`logs/verification-audit.jsonl` を追加する。

2026-06-28 第3 amendment: guarded LLM extraction の前段に決定論コードパーサ
（`verification_parse.code_parse_challenge`）を追加する（solver 順序: `code_parse` → `llm_extract`
→ `llm_reason`）。guarded EXPR/FINAL 経路は「LLM の数式と最終答が算術的に一致する」ことしか証明せず、
数式が難読化チャレンジ文を忠実に表すかは検証しないため、自己無撞着だが誤った提案（例:「twenty five +
twelve」に対し `20 + 12 = 32`）が通過していた（監査 corpus に live 失敗 2 件）。新パーサは有限 CAPTCHA
文法の算術と数詞復元を whole-token フラグメント一致で所有し（部分一致しないため "antenna" 等の carrier 名詞が
"ten" を注入しない）、precision-first で曖昧時（operand ≠2 / 演算不明 / 演算衝突）は `None` に棄権して
不変の LLM チェーンへフォールスルーする。出力の信頼境界は不変（コードで検算可能な数値のみ送信）であり、
security boundary 変更ではない機構 amendment のため新 ADR は不要。

2026-07-01 第4 amendment: `logs/verification-audit.jsonl`（2026-06-28〜07-01 の実チャレンジ 252件）で、
guarded `llm_extract` 経路が依然 16.1% 誤答、算術検算を一切持たない `llm_reason` フォールバックは 66.7% 誤答
と判明した。自己整合性ガード（`_reasoning_answer_is_self_consistent`）を追加し、自由記述の reasoning trace
から行頭の箇条書き記号・行末の `= <結果>` 節を除去した上で二項式に厳密一致する行を探し、guarded 経路が既に
使う `_compute_expression_answer` で再計算する。計算結果が FINAL と食い違えば、誤答を送信せず `None` に
fail-closed する。`temperature=0.0` のため単純な再生成 retry は同じ誤答を再現するだけで無意味であり、この
チェックは生成済みテキストへの後付け検算（追加の LLM 呼び出しなし）なのでレイテンシに影響せず、下記の
チャレンジ窓リスクを悪化させない。このガードは算術的自己整合性のみを証明し、数式の演算子が難読化文の
意図と一致するかは証明しない — 第3 amendment が `llm_extract` について既に記す限界と同一 — ため、演算子
取り違え（例: "45 と 20 の total" の正解が 65 なのに、自己整合した `45 - 20 = 25` を FINAL に述べる）は
依然通過する。`VerificationSolveResult.abstain_reason`（デフォルト `None`、追加のみ）を新設し、この理由と
将来の棄権理由を、新しいログスキーマなしで既存の audit `error` 列に流し込む。

2026-07-01 第5 amendment: 同じ監査コーパスで、決定論パーサの演算動詞辞書に実在の非対称性
（`decreases` はあるが `increases` が無い、`slows` はあるが `accelerates` が無い）が見つかり、かつ裸の
接続詞 "and" を一切扱わないため、コーパスで支配的な `llm_extract` 失敗パターン ——「X newtons and
Y newtons, what is total force?」—— がそもそも `code_parse` に到達していなかった。`increases`/
`increased`/`accelerates`/`accelerate` を、既存の対語と同じリスクプロファイル（構造的曖昧さの無い単一
動詞トークン）で新規登録した。裸の "and" を暗黙の加算シグナルとして扱うのはより危険 — コーパスは "and" を
基準量と乗数カウントの接続（"...and has three claws..."）や積を問う質問（"...and applies X, what is the
product?"）にも使う — なので、以下 4 ガードを**すべて**課す: (1) 動詞・記号による演算が1つも見つかって
いないこと（"and" が既存キューと組み合わさって第2の矛盾する演算を捏造することは絶対に無い）、(2) "and"
トークンが2オペランドの間に位置すること（本モジュールの他の全キューと同じ between 不変条件）、(3) 第2
オペランド以降に "total" cue 語が出現すること（product/multiplied を問う質問は "total" と言わないため
排除できる）、(4) 各オペランド直後の atom が両者で同一の collapse 後文字列であること（典型的には反復
される単位語。チャレンジ自身の2出現を比較するだけで、単位語辞書を持たずに難読化のスペルゆれ
——"newtons"/"neutons"/"notons"—— を吸収でき、第2の「オペランド」が実は乗数であるカウント修飾語的
読みを排除できる）。実コーパス252件全件を通した変更前後の `code_parse_challenge` 再実行では、回帰ゼロ
（既存の解決済み回答は全て不変）、新規に解決された59件中の危険な不一致もゼロ（48件は既存の正解と一致、
11件は既存の誤答を修正、0件が既存の正解と食い違う）ことを確認した。両追加ともパーサの既存の
abstain-first 姿勢と出力の信頼境界は不変のため、先行2件の amendment と同様、機構変更であり
security-boundary 変更ではない。

2026-07-07 第6 amendment: `verification_parse.py` を、失敗の都度の継ぎ足しではなく、成長した監査
コーパス（620 レコード / unique 601 challenge、2026-06-28〜07-06）から導出してゼロから書き直した。
コーパスが示した事実: (a) 失敗は決定論パーサが棄権して LLM チェーンに渡した分に集中する
（`code_parse` は担当 58% 中誤答 1.7%、対して `llm_extract` 19.0%、`llm_reason` 74.1%）、(b) 決定論
経路自身も 4 件の誤答を提出しており、根本原因は 1 つ — ホモフォン誤綴りの数詞（"fife"、"twenny"、
"thrirty"）が何にもマッチせず不可視になり、残った 2 数を文法が自信を持って誤パースした。書き直しでは
継ぎ足し文法を以下のコーパス由来パイプラインに置換した: `0`→`o` の leet 正規化; 断片 merge の上限を
collapse 後トークン長（+ 断片数キャップ）に変更（二重字化の下では raw 長の上限は無意味）; 数詞の
編集距離 1 fuzzy 復元は正準綴りと比較（長さフロア、prose ストップワード —— "fight"/"right" は "eight"
から 1 編集で 601 件中 45 件に出現 ——、および 2 通り以上の読みが成立したらパース全体を棄権する
poison 規則）、演算動詞は正準形または collapse 形と比較; 隣接する重複数詞の dedup（"thirty two two"、
"forty forty five" — 数詞を 2 度書く難読化手口）; 厳密にインターリーブした N 段チェーンの左畳み込み
（各ステップに非負ガード。"forty + seven ... increases by seven" = 54）; 位置で分類する trailing cue
（オペランド間の演算語は演算子、最終オペランド以降では total/sum/combined が暗黙加算、
product/times/multiplied が暗黙乗算、第 2 オペランド直後の "less"/"times" は後置演算子、末尾の
浮遊 `+` 記号はノイズ）; 暗黙加算の単位ガードを「隣接トークンの完全一致」から「pairwise 編集距離
≤ 1（難読化は同じ単位語を出現ごとに違う綴りにする）または疑問語への連続」に緩和（"and has three
claws" のカウント修飾語トラップは引き続き拒否）。除算動詞は明示語のみに削減 — コーパスに除算問題は
0 件で、旧 "splits"/"shared" エントリは情景 prose（"a claw struggle splits on territory"）を除算と
誤読していた。意図的な仕様変更 2 点: 完全インターリーブの 3+ オペランドチェーンをパース対象化
（従来は無条件棄権）、"X and Y, what is the product?" を乗算として解決（従来は棄権と固定）。検証:
オフラインのリプレイハーネス（`docs/evidence/adr-0062-parser-rewrite/`）で、サーバ受理済み 550 件の
回答 + 手動で解いた 40 ラベルを ground truth に、hard gate「601 件で誤答提出ゼロ」PASS、カバレッジ
58% → 82.9%（498/601 パース、全件正解）、4 件の誤答回帰を base64 fixture 化した 121 テスト全 green。
サーバが算術的に唯一自然な回答を拒否した 2 レコード（0.33%）はサーバ側 anomaly としてハーネスに
記録した。abstain-first 姿勢、3 段 solver 順序、audit テレメトリ、出力の信頼境界は不変 — 第 3
amendment の前例に従い機構 amendment とする。

2026-07-09 第7 amendment: 第6 amendment 後の失敗ラウンド（816 レコード / unique 792 challenge。
チャレンジの構成が文法で表現できない乗算的言い回しへシフトしたため成功率は 85.8% で横ばい）から
文法を拡張した。失敗の復号で 3 クラスが判明: 演算選択の誤り（`code_parse` も LLM も "increases by
a factor seven"、"doubled by two"、"it has two claws"、"each detects two" を加算と読んだ）、LLM
経路の分割数詞誤読（"tW/eN tY tHrEe" を 20 と抽出し "three" を落とす）、少数の不可避なサーバ側
クラス。変更点（各項ともサーバ受理済みの同型 twin —— 注記があれば同数値 —— で裏付け）: 乗算
マーカー語（factor/doubled/each）は空の gap を埋めるか、同一 gap 内の汎用 change-verb
（"increases"/"accelerates"。内部 op コードを分離）に勝つ。ただし最終オペランドに隣接しない
trailing マーカーは情景ノイズのまま（"...physicx factors" = 47.00 受理）; 隣接する "times" tail は
単一 change-verb gap を上書き（"increases it by three times" = 96.00、twin 受理）; 第 2 オペランド
直後の爪カウントは乗算（"three claws" — コーパス受理例は全件積で加算例ゼロ。第6 amendment の
「カウント修飾語トラップ」棄権はこの形に限り更新）; 明示的な算術指示（"what is the sum of
these"、"please add them"）は暗黙加算の like-unit ガードを免除（乗算読みはサーバに 2 度拒否
された）; "slows" と trailing "combined" cue の矛盾、および同一主体の裸の所持カウント（"it has
twoo, whats total"）は棄権 — どちらの読みもコーパスに実在し、誤パースは None より悪い; 数詞の
fuzzy マッチングに、merge 後トークン ≥ 6 字に限り COLLAPSE 済み正準綴りとの編集距離 1 比較を追加
（"fowr teen" → "fowrten" → fourteen。演算動詞と同じ扱い）。リプレイハーネスは負の ground truth
（サーバが拒否した回答はその challenge にとって恒久的に誤り — 手動ラベル不要）と、解決不能と
判明した challenge の null-answer ラベル（5 件: 算術的に強制される回答をサーバが拒否した 4 件 —
うち 2 件は第6 amendment の「算術によるラベル」caveat から再分類 —、"accelerates by four" の
サーバ非一貫 1 件）を得た。LLM プロンプトには分割数詞の de-noise 例と乗算/加算 cue リストを追加。
レビューラウンドはコーパス単独では見えない 3 つの継ぎ目を固めた: 非隣接の trailing マーカーは
implicit 経路でもノイズ（explicit chain だけでなく）、同一主体の所持 lookback は atom 境界に
依存しない（fuzzy 数詞 merge が動詞の断片を吸収しうる — "ha s two"）、先頭位置マーカーと
implicit 後置減算×"combined" cue は棄権。検証: 792 challenge で hard gate PASS（正解 654、誤答
ゼロ、カバレッジ 81.4% → 83.2%。新規則による既知正解の退行はゼロまで潰した）、失敗ラウンドを
base64 fixture 化した 151 テスト全 green。solver 順序、audit テレメトリ、出力の信頼境界は不変 —
機構 amendment とする。

2026-07-15 第8 amendment: 第7 amendment 後の失敗ラウンド（2026-07-10 以降 448 レコード、拒否 31 件
= 6.9%。うち 5 件は `code_parse` 自身の誤答 — hard gate が防ぐべきクラスそのもの）から solver を
強化した。失敗の復号は 3 系統に分かれた。(1) パーサ round-8 文法（live 誤答 1 件につき 1 規則）:
COLLAPSE 済み数詞から編集距離 1 の 4-5 字トークン（"thyree"/"qthreee"）は round-7 の
collapsed-fuzzy 床未満で黙って落ちていた — 今後はパース全体を毒化（棄権。値としての回復は
replay コーパスで誤マッチゼロが示されるまで見送り）; "five point five" は新 `point` lexeme で
小数オペランドに合成（この lexeme が無かったことで `_dedup_numbers` が 2 つの five を誤併合しても
いた）。合成できない point はオペランド隣接なら棄権、遠ければ情景ノイズ; 乗算マーカーは隣接
転置 1 回でも一致（"duoubbles" → "duobles" vs "doubles" — Damerau 1 / Levenshtein 2 で round-7
fuzzy には不可視）; 言い直された複合量（"swims at twenty three … speed is twenty three, and
speeds up by seven"）は gap にイベントが無い場合オペランドレベルで縮約 — `_dedup_numbers` の
オペランド版 — し、破損した言い直し動詞 "speed is"（merge 後 "speedis"、"speeds" から 1 編集）を
fuzzy stopwords に追加して gap を偽演算で埋めさせない。(2) 拒否回答メモリ: live コーパスに
sha 同一の challenge 再出題で同じ拒否済み回答をそのまま再送した組が存在した。各 solve は audit
ログのサーバ拒否レコードを参照し（単一の情報源、第 2 ストア無し。append-only 前提の byte offset
差分読み、読めなければ fail-open）、code_parse / llm_extract の拒否済み候補は次のパスへ
フォールスルー、全パスが拒否済み値に達したら棄権（`answer_previously_rejected`）して確実な 400 に
failure-tracker 予算を燃やさない。(3) LLM の distractor 規律: 31 件中 26 件は LLM 経路の単位混同
（"total force" 質問に速度を加算/乗算、"total" を減算で回答）— 両プロンプト（と再同期した
コード内フォールバック既定値）は、質問が名指しする量の単位に数の選択を固定し、round-7 の明示
ペア指示例外（"sum of these" は異単位でも加算）を保持し、"total" は決して減算しないと明記し、
live 失敗由来の worked example を 1 つ持つ。LLM 経路の効果は次の live ラウンドで測定する（replay
ハーネスは code_parse のみ対象）。レビューラウンド（python-reviewer + codex cross-model）は失敗
コーパス単独では見えない 4 つの継ぎ目を閉じた: サーバの incorrect-answer メッセージを持つ
レコードのみを拒否と数える（verify_success=false は transport 失敗でも書かれ、その回答は正しい
可能性がある）; 複数桁または重複した小数部（"point five five"）は .5 に合成せず棄権; 言い直し
縮約は copula（"speed IS twenty three"）を要求し、情景 prose 中の 2 つの真に別個な等値量は決して
併合しない; audit ログは solve ごとの全再パースでなく差分読み（verify のたびに追記されるため
mtime キャッシュは無効化され続けていた）。検証: 1272 challenge で hard gate PASS（正解 1045、誤答ゼロ、
カバレッジ 82.5%）。round-7 パーサを同一コーパスで replay すると誤答 5 — round 8 は 5 件全てを
解消しつつカバレッジは純増（82.4% → 82.5%）。5 誤答を base64 fixture 化した 174 テスト全 green。
solver 順序、audit テレメトリ、出力の信頼境界は不変 — 第 3 amendment の前例に従い機構 amendment
とする。

2026-07-20 第9 amendment: 自由推論フォールバック（`llm_reason`）を退役。`code_parse` と guarded な
`llm_extract` を過ぎたら、solver は推測せず理由コード付きで abstain する。過去の機構 amendment と
異なり、本 amendment は **solver 順序を変更する**: チェーンは code_parse → llm_extract → abstain に
なる。証拠（T-VER6 再計測、round-7 運用 10 日 / 921 レコード）: `llm_reason` はトラフィックの 2.3%
（21 件、毎日 1〜5 件で流入は枯れていない）を verify 成功率 38%（8/21）で処理 — コイントス未満の
推測で、8 件の成功のために誤答 13 件を送信（全誤答の 25% を占めて全成功の 0.9% を得る）し、
rejected-answer メモリと platform から見える誤答 footprint を膨らませていた。一方 `code_parse` は
98.8%（734/743、シェア 80.7%）、`llm_extract` は 81.4%（127/156、round 6 の 63.2% から改善）で、
guarded 経路が負荷を担えている。機構: guarded 経路がいずれも提出可能な答えを出さない場合、solver は
`abstain_reason="reason_fallback_disabled"` を返す（候補は出たが全て rejected の場合は従来通り
`answer_previously_rejected` — 2 つのコードは別の読みに使う）。理由は不変の agent 配線経由で audit
ログの既存 `error` 列に乗り、abstain は従来通り failure tracker に数えられるため、challenge 文法の
持続的 drift は推測で踏み抜かれず loud にセッションを停止させる。退役機構は同一変更で撤去
（推論 system プロンプト `config/prompts/verification_solve_reason_system.md` + `PromptTemplates`
フィールドとコード内デフォルト、FINAL 行自己整合性ガード、5000 トークン推論予算。本 amendment の
commit の git revert で復元可能）。復活基準（予約）: `reason_fallback_disabled` の日次件数が高止まり
し `llm_extract` の改善で吸収できない場合、last resort は再計算ゲート付き guarded 経路として再設計
する — 自由形式の推測は復活させない（台帳 T-VER-ABSTAIN で追跡、約 2 週間後に読む）。

## Date

2026-06-26

## Context

Moltbook は現在、`is_verified=false` のエージェントに対し、作成したコンテンツ（投稿・コメント・サブモルト）がプラットフォーム上で可視化される前に、難読化された数学チャレンジを解くことを要求する。作成レスポンス（HTTP 201）は `verification` オブジェクト `{challenge_text, verification_code, expires_at}` を約5分の有効期限つきで返し、エージェントは `challenge_text` を解いて `POST /api/v1/verify {verification_code, answer}` を送るまで `verification_status` が `pending` から `verified` に遷移しない。Trusted agent と admin はこの手順をバイパスする（作成レスポンスに `verification` オブジェクトを含まず、コンテンツは即座に可視化される）。本エージェントは `is_verified=false` であり、毎回の作成呼び出しでハンドシェイクを完了する必要がある。

既存コードは検証を扱っているように見えて、実際には沈黙のうちに発火を停止していた。確認可能なログ範囲（2026-05-22〜2026-06-25）で、すべての投稿（`posts_count=349`）とすべてのコメントが `verification_status=pending` のまま — 公開プロフィールから不可視、他エージェントからも取得不能 — であった一方、`POST /posts` と `POST /comments` は一貫して HTTP 201 を返し、サーバ側のカウンタは正常に増加していた。コードは自分が作成したコンテンツの `verification_status` を一度も読まなかったため、API の成功シグナルと Web 上の可視状態との乖離は検出されず、障害は完全にサイレントだった。

根本原因は、既存の検証コードと現行 API との間の3層のドリフトである。第1層は配線: 唯一の solve-and-submit 呼び出しがフィード読み取りループ内に置かれ、`post.get("verification_challenge")`（現行 API がフィード項目に決して載せないフィールド）をキーにしていた。ログ範囲全体で0回しか発火せず、`verification` オブジェクトを実際に運ぶ作成レスポンス側の経路は一度も検査されなかった。第2層はフィールド名: コードは `challenge.get("text")` と `challenge.get("id")` を読み、`{challenge_id, answer}` を送っていたが、現行 API は `challenge_text` と `verification_code` を返し、`{verification_code, answer}` を期待する。仮に配線が正しくても、すべてのフィールド参照は `None` を返していた。第3層はソルバ: 決定論的な難読化解除・解析ルーチンは均一な文字二重化形式（例: `"ttwweennttyy"` → `"twenty"`）向けに書かれており、大小交互・散乱記号（`[]^/-`）・分断された語間隔を組み合わせた現行形式（例: `"A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy"`）では `"Failed to parse"` を返した。いずれの層も単独では有効な `/verify` 送信を生成できなかった。

## Decision

1. **solve→POST `/verify` ハンドシェイクを全コンテンツ作成経路に配線する。** `post_pipeline._publish_post`、`feed_manager` のコメント経路、`reply_handler` がそれぞれ作成レスポンスから `verification` オブジェクトを読み、コンストラクタで注入された共有コールバック `Agent._handle_verification`（既存のコールバック注入パターン）を呼ぶ。`post_comment` はルートレベルの `verification` キーを返り値の comment dict に畳み込み、API が `"comment"` 配下にネストしてもレスポンスルートに置いてもゲートが発火するようにする。

2. **記録を可視化条件でゲートする。** 未検証の投稿・コメントは不可視であり、5分のチャレンジ窓が過ぎると回復不能になる。dedup マーカー（`mark_posted`, `own_post_ids`）、エピソード書き込み、`memory.record_post` / `memory.record_commented`、`NoveltyGate.record`、`actions_taken` は検証成功後にのみ実行する。レート制限カウンタ（`scheduler.record_post` / `scheduler.record_comment`）は `POST` 直後のままにする — サーバは検証結果に関わらずクォータを消費するため。Trusted-bypass レスポンス（`verification` オブジェクトを持たないもの）は素通りし、従来どおり記録する。

3. **求解は LLM の意味抽出 + コード所有の検証で行う。** `solve_challenge` は `challenge_text` を untrusted content として包み、まず LLM に短い `EXPR: <number> <op> <number>` / `FINAL: <answer>` ペアを出させる。Python が `Decimal` で式を計算し、計算結果の小数2桁表現が LLM の `FINAL` と一致する場合だけ採用する。この fast path が失敗した場合のみ、bounded reasoning prompt（`temperature=0.0`, `drop_truncated=True`, 寛大な `num_predict` cap）へ fallback し、ラベル付き最終回答を抽出する。信頼境界は引き続き出力側にある: コード guard または bounded fallback を通過した parseable number だけがプラットフォームに送られ、untrusted な `challenge_text` 経由の命令は `None` へ fail-closed する。

4. **死んだフィードベースの検証経路を除去する。** `verification_challenge` のフィード分岐と `run_cycle` を通る配線を削除する。これらはログ履歴で0回しか発火しておらず、現行 API に対して発火し得ない。

5. **`client._request` チョークポイントに構造のみの API 計装を追加する。** 各 API 呼び出しは `logs/api-audit.jsonl` に1レコードを追記する: HTTP メソッド、正規化エンドポイント（数値 ID を `{id}` に置換）、HTTP ステータス、envelope のキー名、ホワイトリスト化した content-status フィールド（`verification_status`, `is_spam`, `is_deleted`; bool キャスト or サニタイズ済み）、soft-fail フラグ（HTTP 2xx だが本文 `success:false`）、サニタイズ済みサーバエラー文、`rate-remaining`。依存する envelope キーが欠落した場合に schema-drift `WARNING` を発火する（成功応答=2xx のみ。エラー応答の本文は error envelope なので照合しない）。本文の自由文は記録しないため、untrusted な外部コンテンツを運ぶエピソードログと異なり、このログは直接読んでも安全である。

6. **専用の verification challenge audit corpus を追加する。** `Agent._handle_verification` は、challenge を持つ各 solve attempt について `logs/verification-audit.jsonl` に best-effort で1レコードを書く: `challenge_b64`, `challenge_sha256`, `verification_code_sha256`, answer, `solver_path`, `solve_success`, `verify_success`, sanitized error。challenge text は自由文としてではなく base64 で保存するため、直接ログを眺めても corpus が prompt 命令として読まれにくい。これを decode する評価 harness は、decode 後のテキストを必ず untrusted content として再ラップする。

7. **返信を `parent_id` でスレッド化する。** API は返信に `parent_id` を要求するが、従来は送られておらず、返信がトップレベルコメントとして投稿されていた。すべての返信 `POST /comments` 呼び出しでこのフィールドを含めるようにする。

## Alternatives Considered

### 決定論的な難読化解除・解析ソルバを拡張する

既存の均一文字二重化ハンドラに加え、大小交互＋散乱記号形式のケースを追加する。却下: 2つの形式は相反する正規化を要求する — 繰り返し文字の畳み込みは `"ttwweennttyy"` から `"twenty"` を復元するが、大小交互版では `"three"` → `"thre"` を破壊する。演算動詞の語彙は開放的であり、実際のチャレンジは未知の末尾ジャンク（`"<um> lxObqS tHiS"`）を運んできた — regex パイプラインなら詰まるが、LLM はプロンプトなしで捨てた。

### LLM による構造化抽出（`format=json {num1, op, num2}` でコード側で計算）

LLM に構造化 JSON オブジェクトを要求し、算術は Python で計算する。テスト結果で却下: 6問中3問を誤答した。`format=json` 制約は推論モデルの `<think>` ブロックを抑制し、chain-of-thought なしでは難読化された数字語を誤読する（`twenty`→10, `eighty`→8）。算術をコードで計算するのは正しい分離だが、そこに至るために推論ステップを抑制するとソルバが不安定になる。

2026-06-28 amendment note: 実装した fast path は、この却下案とは異なる。constrained JSON decoding は使わず、schema が通っただけで LLM の抽出値を採用しない。LLM は単純な数式を提案できるだけで、Python が再計算する。形式が欠ける、または不一致の場合は、その提案を送信せず bounded reasoning へ fallback する。

### 即答を強制する（「数字だけ答えよ」）

LLM に中間ステップなしで素の数値を返させる。却下: これも chain-of-thought を抑制し、難読化解除済みの平文入力でさえ誤った算術を生んだ（`20+5`→27）。自由な推論の後に出力から数値を抽出するほうが、出力形式を制約するより信頼できる。

### `client.py` 内で検証を扱う

全 API 呼び出しが通る単一の HTTP チョークポイントに solve-and-submit ロジックを置く。却下: ソルバは LLM アクセスを要するが、`client.py` は LLM 参照を持たない純粋なトランスポートである。`client.py` に LLM を import すると [ADR-0015](./0015-one-external-adapter-per-agent.md) が定める `core` ← `adapters` の依存方向を逆転させる。`verification` オブジェクトは既にパイプライン層が解析する作成レスポンスに載って戻ってくるため、そこに追加の配線は不要。

### 観測のため API レスポンス本文を全量ログする

サイレント障害を発見可能にするため、レスポンス JSON 全体を記録する。却下: レスポンス本文には他エージェントの投稿・コメントテキストが含まれ、これは untrusted でプロンプトインジェクションの経路である。その内容を Claude Code が直接読めるファイルに書くと、エピソードログの読み取りを禁じる境界（CLAUDE.md）と同じものを侵食する。構造＋ステータスのログは、インジェクション面を導入せずに診断目的（2xx だが不可視の障害、envelope のフィールドドリフトの捕捉）を達成する。

### raw challenge text を通常のログフィールドに入れる

Corpus 収集を簡単にするため、`verification-audit.jsonl` に `challenge_text` をそのまま記録する。却下: challenge は attacker-controlled な外部入力であり、prompt injection 文字列を含みうる。通常の JSON 文字列として保存すると、何気ないログ閲覧や coding-agent のデバッグセッションがそれを prose として取り込む。base64 は内容を trusted にするものではないが、直接閲覧時の accidental instruction-following を避けつつ、明示的な eval harness 向けの exact corpus は保持できる。

### 検証を人間承認ゲートに通す

検証ハンドシェイクを、回答送信前に確認を要する監督対象アクションとして扱う。却下: 検証はコンテンツ可視化のために必要なプラットフォームの anti-bot ハンドシェイクであり、社会的・編集的アクションではない。ゲートすると、作成済みの投稿を監督するのではなく恒久的に不可視のまま残してしまう。コンテンツ生成は作成 `POST` の前に既存の novelty・確認ゲートを通過済みであり、検証ハンドシェイクはそれらのゲート通過後に実行される。

## Consequences

### Positive

- 投稿・コメント・返信が再び公開され、公開可視になる。本番に対する end-to-end 確認: 制御された実投稿がチャレンジ（`26+17=43`）を解いて `verification_status=verified` に遷移し、続く実ライブ自律セッションが実際の返信チャレンジを解いて `POST /verify` が HTTP 200 を返した。
- 一般的な検証チャレンジは、長い free reasoning trace ではなく短い guarded extraction call で終わりうる。fast path が valid expression を出した場合、算術の採否は Python が所有する。
- `logs/api-audit.jsonl` によりサイレント障害と API envelope ドリフトが grep 可能になる。本インシデントを起こした正確なバグクラス — HTTP 2xx でコンテンツが不可視のまま、レスポンス envelope のフィールド名ドリフト — は、数週間積み上がる代わりに数日以内に表面化していたはずである。
- `logs/verification-audit.jsonl` により、実際に出題された challenge、solver path、answer、`/verify` outcome の前方 corpus が作られる。今後の solver 変更は、合成例や危険な episode log 直読ではなく、観測済み failure に対して評価できる。
- 検証済み（可視）コンテンツのみが `NoveltyGate` とメモリストアに入るため、349件の pending 投稿と関連コメントが novelty・重複排除の履歴を汚染しなくなる。
- 返信がトップレベルコメントとしてではなく、親コメントの下に正しくスレッド化される。

### Negative

- 各コンテンツ作成呼び出しは引き続き LLM チャレンジ求解に依存する。guarded fast path は common-case latency を下げるはずだが、fallback reasoning はなお数十秒を要しうる。cold または最近スワップされたモデルでは5分のチャレンジ窓に近づきうる（生成が pre-warm の役を果たす）。
- 検証ソルバはコンテンツ作成時点でローカル LLM が到達可能であることへの依存を加える。作成時に Ollama への接続が失敗すると `/verify` 呼び出しがスキップされ、作成済みコンテンツは pending のまま残る。
- 修正前の pending コンテンツ（349投稿＋同窓内に蓄積したコメント）は回復不能: チャレンジ窓は本修正のはるか前に失効しており、プラットフォームは再チャレンジ endpoint を提供しない。これは前方修正のみである。

### Neutral / Follow-ups

- ソルバプロンプトと token budget は元々 `qwen3.5:9b` 向けに較正されていた。ADR-0069 で本番モデルが
  `gemma4:e4b` にスワップされた後、この特定タスクで弱くなっていないかを専用のブラインド・リプレイ実験
  （2026-07-01、`docs/evidence/verify-solve-model-compare-20260701/`）で確認した: gemma は自身が過去に
  正解した95件を100%の自己一貫性で再現した一方、qwen が同じ95件をブラインドで再現できたのは72.6%に
  とどまった — gemma がこのタスクで劣っているという証拠は無く、per-task のモデル固定は不要と判断した。
  telemetry caller は `moltbook.verify_solve` のまま。
- `logs/api-audit.jsonl` にはまだローテーションポリシーがない。API 呼び出しごとに1レコードを追記する。
- `logs/verification-audit.jsonl` にはまだローテーション / retention ポリシーがない。challenge を伴う作成試行ごとに1 corpus/outcome レコードを追記する。
- `verification_code` は送信前のフォーマット検証を行わなくなった: このフィールドは URL パスではなく JSON リクエストボディを通るため、非空チェックで十分である。従来の検証は古いフィールド名前提の遺物だった。

## References

- [ADR-0007](./0007-security-boundary-model.md) — セキュリティ境界モデル。全量レスポンス本文ログより構造のみの API ログを選んだ動機となった、untrusted コンテンツ面ポリシーとエピソードログ読み取り禁止。
- [ADR-0015](./0015-one-external-adapter-per-agent.md) — 1エージェント1外部アダプタ。LLM ソルバを `client.py` 内に置くことを排除した `core` ← `adapters` の import 方向。
- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — NoveltyGate。pending コンテンツが novelty 履歴を汚染しないよう、ゲートへの記録は検証成功を条件とする。
- [ADR-0043](./0043-per-post-seeding-for-self-post-generation.md) — per-post seeding と `check_topic_novelty` の除去。`own_post_ids` と関連 dedup マーカーは検証成功後にのみ記録する。
- 実装: コミット `92622e3`。
- `docs/CODEMAPS/architecture.md` Data Flow — 作成パイプラインの検証ハンドシェイクを反映するため同一コミットで更新。
- 関連 learned パターン: `llm-pipeline-layering` — 推論モデルは chain-of-thought を抑制してはならない。`format=json` が自由推論の100%に対し50%精度だった制約付き抽出タスクで経験的に検証済み。
