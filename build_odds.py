# -*- coding: utf-8 -*-
"""odds_bundle.js を作る（オッズ入り出走表の抽出画面 odds.html 用）。odds_html.py・odds_runner.py を1バイトも変えずにbase64で埋め込む。
v4.9 の bundle.js・version.json には触れない（v4.9 の分析・考察・判定と指紋は変わらない）。
使い方: python build_odds.py"""
import base64, json, hashlib, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("odds_html.py", "odds_runner.py")


def code_sha(name):
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.join(HERE, name), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


version = {"code_odds": code_sha("odds_html.py"), "code_odds_runner": code_sha("odds_runner.py"),
           "full_sha256": {n: hashlib.sha256(open(os.path.join(HERE, n), "rb").read()).hexdigest() for n in FILES}}
files = {n: base64.b64encode(open(os.path.join(HERE, n), "rb").read()).decode("ascii") for n in FILES}
with open(os.path.join(HERE, "odds_bundle.js"), "w", encoding="utf-8") as f:
    f.write("// build_odds.py が自動で作るファイル。手で編集しない。\n")
    f.write("const ODDS_BUNDLE = " + json.dumps({"version": version, "files": files}, ensure_ascii=False) + ";\n")
print(json.dumps(version, ensure_ascii=False, indent=1))
