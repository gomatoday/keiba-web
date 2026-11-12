# -*- coding: utf-8 -*-
"""odds_runner.py  オッズ入り出走表の抽出画面（odds.html）の受け渡し役（Pyodide上で動く）。
計算はすべて既存のファイルが行う: 分析＝keiba_v49.py（runner._run_predict 経由。v4.9 の分析と同じ）、結果ページ＝result_v49.py（runner.result_parse）、
オッズ＝odds_html.py。このファイルは呼び出しと受け渡しだけを行い、予測ロジックを持たない。v4.9 の記録（keiba_v49）には書き込まない。"""
import json, hashlib, re
import runner
import odds_html


def _sha(path):
    return hashlib.sha256(re.sub(r"\s+", "", open(path, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def info():
    return json.dumps({"odds_html": odds_html.VERSION, "code_odds": _sha("/app/odds_html.py"), "code_odds_runner": _sha("/app/odds_runner.py")}, ensure_ascii=False)


def card(path, check_blank):
    """オッズ入り出走表1件: 分析（v4.9）・オッズの読み取り・（指定時）オッズを消したHTMLでの分析との一致。"""
    b = open(path, "rb").read()
    od = odds_html.parse(b, runner._eng.E47.decode_html)
    rc, out, rec = runner._run_predict(path)
    r = {"race_id": (rec or {}).get("race_id") or od["race_id"], "rc": rc, "rec": rec, "odds": od, "blank": "未確認"}
    if rc == 0 and rec is None:
        r["analysis"] = "見送り"
    elif rc == 0:
        r["analysis"] = rec.get("mode")
    else:
        r["analysis"] = "エラー・停止"
    lines = [x for x in out.strip().split("\n") if x.strip()]
    r["note"] = "" if rec else " ".join(lines[-3:])[:300]
    if check_blank:
        s = odds_html.blank_odds(b, runner._eng.E47.decode_html)
        if s is None:
            r["blank"] = "確認できず"
        else:
            p2 = "/work/odds_blank.html"
            with open(p2, "w", encoding="utf-8") as f:
                f.write(s)
            od2 = odds_html.parse(open(p2, "rb").read(), runner._eng.E47.decode_html)
            rc2, out2, rec2 = runner._run_predict(p2)
            if od2["n"] != 0:
                r["blank"] = "確認できず（オッズを消しきれない）"
            else:
                r["blank"] = "一致" if (rc2 == rc and out2 == out and rec2 == rec) else "不一致"
    return json.dumps(r, ensure_ascii=False)


def result(path):
    return runner.result_parse(path)
