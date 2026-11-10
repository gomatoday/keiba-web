# 南関東競馬分析 v4.8（Web版）

出走表HTML → 分析 → 全券種の期待値と4案の仮想購入 → 結果ページから結果登録 → 記録・集計（v4.8 の判定）を、ブラウザ内で行う。データは外部に送信しない。実際の馬券は購入しない。

- index.html：分析画面（1レースずつ・まとめて分析）
- kekka.html：結果入力。結果ページ（成績・払戻金）からの登録が原則（着順・全券種の払戻・全馬の人気を読む）。手入力は例外（同着のあるレースは不可）
- data.html：記録とバックアップ（IndexedDB の keiba_v48。v4.7 の記録 keiba_v47 には触れない）、LEDGER行・POP行の書き出し、LEDGER行の照合、集計（aggregate）
- test.html：PC版との一致テスト（分析・考察・記録・集計・結果読み取り・まとめて分析。正解データ golden_v4.8 を使う）

計算に使うファイル（build.py が bundle.js に1バイトも変えずに埋め込む。変更しない）
- keiba_v48.py：分析計算v4.8.py と同一。v4.7 の計算を実行してから、v4.8 の確率・期待値・4案を出す
- kosatsu_v48.py：考察計算v4.8.py と同一。主評価（対 v4.7）・参考（対 ref45）・副評価(a)(b)(c)、LEDGER行、aggregate
- v48_model.py・v48_params.json：v4.8 の特徴量と確率の式、係数（304レースの設計用データで作って固定）
- keiba_v47.py：分析計算v4.7.py と同一（v4.8 の比較相手と7項目の寄与の計算に使う）
- feat_extract.py：候補抽出.py と同一（出走表から候補項目を抜き出す）
- result_html.py（v4.7 と同じ）・pop_html.py・result_v48.py：結果ページの読み取り（入力の補助。考察の計算は持たない）
- runner.py：受け渡し役（予測ロジックを持たない）

その他
- build.py：上のファイルを bundle.js に埋め込み、version.json（指紋の正本）を作る（.py や係数を差し替えたら必ず実行）
- Pyodide 0.29.5（Python 3.13）に固定。beautifulsoup4・lxml を使う

注意: ブラウザ内の記録は、開いている場所（パソコンのファイル／GitHub Pages）ごとに別々になる。移るときはバックアップから復元する。
