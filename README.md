# 南関東競馬分析 v4.7（Web版 Phase 1）

出走表HTML → 分析 → 買い目（仮想購入）をブラウザ内で行う。計算は `keiba_v47.py`（分析計算v4.7.py と同一ファイル。指紋 e728bfee47ab）がPyodide上で行う。データは外部に送信しない。

- index.html：分析画面
- kekka.html：結果入力（Phase 2。考察計算v4.7.py の kosatsu をそのまま実行し、考察出力〈LEDGER行を含む〉を保存）
- data.html：記録とバックアップ（Phase 3。IndexedDBに1レース1件。全データのバックアップ・復元〈追加のみ〉、LEDGER行の書き出しと照合、集計〈aggregate。Phase 4〉）
- storage.js：端末内の記録とバックアップの処理
- test.html：Python版との一致テスト（分析＝Phase 1、考察＝Phase 2、記録＝Phase 3、集計＝Phase 4。正解データ golden_v4.7 を使う）
- keiba_v47.py：計算エンジン（変更しない）
- kosatsu_v47.py：考察計算（考察計算v4.7.py と同一ファイル。指紋 cea069919a98。変更しない）
- runner.py：受け渡し役（予測ロジックを持たない）
- build.py：keiba_v47.py・runner.py を bundle.js に埋め込み、version.json を作る（.pyを差し替えたら必ず実行）
- Pyodide 0.29.5（Python 3.13）に固定

注意: ブラウザ内の記録は、開いている場所（パソコンのファイル／GitHub Pages）ごとに別々になる。移るときはバックアップから復元する。
