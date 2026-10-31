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
- HF: CA の dataset card（`shimo4228/contemplative-agent` の README.md）の版 DOI が v2.3.0 のまま。v2.14.0（10.5281/zenodo.23837915）に差し替えた版をオーナーが upload する。

完了: 上の各項目に、出した PR の URL か「出さない」の記録がある。
