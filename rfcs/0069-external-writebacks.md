---
title: 外部 repo と外部サービスへの書き戻し（AKC / AAP / harness / otel / rules への PR、到達表の確認、SWHID の解決）
state: accepted
state_since: 2026-10-31
review-when: 各項目について、PR を出したか出さないかが記録された（期日なし）
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: repair
---

## タスク

ロードマップのうち、この repo の外にあるものへの書き戻しをまとめる。外部 repo への PR と外部サービスの確認はオーナーの操作なので、期日を置かない。

## 詳細

持つ行: P1-13.1、P1-13.3、P1-13.7、P1-11.14、P1-11.12、P1-03.5（AAP 列）、P3-06.6、P3-06.7、P3-05.14、P4-03.3、P0-06.11 の SWHID の残り。

- AKC: ADR-0028 への dated note、6 フェーズ写像の 2 面（`CLAUDE.md`、`examples/constitution_amend/README.md`）。
- AAP: 0010 の脚注、CA を記入例にする case study、open questions への書き戻し。AAP 側の表ができたら `scripts/adr_index.py` を再生成して AAP 列を埋める。
- harness: commit テンプレートの帰属 trailer。
- otel: `docs/mapping.md` の Frozen 注記（origin/main にはある。ローカル checkout が古い）。
- rules: ADR-0005 の追補（ローカルの commit を push する）。
- 到達表: data repo の NOTICE / DATACARD の 5 行のうち 4 行（Git 履歴・fork・HF・Software Heritage）が "not yet checked"。確認日を書き、`docs/runbooks/incident-response.md` にも同じ日付を書く。旧版 DOI に `real_sample.jsonl` が入っているかの確認も同じ表に書く。
- SWHID: `docs/evidence/releases.md` の各行と CITATION.cff の `swh:1:snp:` を `rel` / `dir` 形に解決する。v2.14.0 とデータ v1.1.0 の Software Heritage save request はオーナーが 2026-10-31 に送り、受理された（id 2599267 / 2599268）。Wayback も同日に保存した。visit が解決したら `swh:1:rel:` を releases.md と CITATION.cff に書く。

完了: 上の各項目に、出した PR の URL か「出さない」の記録がある。

## 2026-11-04 triage 照合 (by: judge)

verdict: hold

オーナーの操作。ただし SWHID の 1 行は今できる。

Software Heritage の visit は 2026-10-31 に完了していた（本体 14:04 UTC、データ 14:05 UTC、どちらも status full）。snapshot から tag を引くと、v2.14.0 = `swh:1:rel:3a0c6da89207a2d10e426deb319f7e9bd6375706`、データ v1.1.0 = `swh:1:rel:6ec548cfcdddd9cd3ede1655820c167ff09e4219`。`CITATION.cff` は公開メタデータなので、書き込みは digest で OK を聞く。他の行（外部 repo への PR、到達表の確認）はオーナーの操作で、期日なし。

## 2026-11-04 SWHID の行は済 (by: judge)

triage digest の承認を受けて、`docs/evidence/releases.md` の SWHID 欄を全行（本体 23 行・データ 2 行）Software Heritage API で解決して書いた。annotated tag は `swh:1:rel:`（release の名前と target commit が一致）、lightweight tag は 2026-10-31 の visit snapshot を `visit=` に持つ `swh:1:dir:` 形。`CITATION.cff` の `swh:1:snp:` 8 件は対応する `swh:1:rel:` に置き換え、v2.14.0 を足した。この RFC に残る行は外部 repo への PR と到達表の確認で、どちらもオーナーの操作。
