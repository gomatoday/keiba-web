# -*- coding: utf-8 -*-
"""bundle.js と version.json を作る。keiba_v47.py と runner.py を、1バイトも変えずにbase64で埋め込む
（ブラウザで index.html を直接開いても動くようにするため）。指紋は分析計算v4.7.pyと同じ式で計算する。
使い方: python build.py"""
import base64, json, hashlib, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
PYODIDE = "0.29.5"


def code_sha(path):
    return hashlib.sha256(re.sub(r"\s+", "", open(path, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


eng = os.path.join(HERE, "keiba_v47.py")
version = {
    "version": "v4.7",
    "code": code_sha(eng),
    "engine_file": "keiba_v47.py（分析計算v4.7.py と同一内容）",
    "engine_sha256_full": hashlib.sha256(open(eng, "rb").read()).hexdigest(),
    "code_k": code_sha(os.path.join(HERE, "kosatsu_v47.py")),
    "kosatsu_file": "kosatsu_v47.py（考察計算v4.7.py と同一内容）",
    "runner_sha256_full": hashlib.sha256(open(os.path.join(HERE, "runner.py"), "rb").read()).hexdigest(),
    "pyodide": PYODIDE,
    "pyodide_url": "https://cdn.jsdelivr.net/pyodide/v%s/full/" % PYODIDE,
    "python_minor": "3.13",
}
files = {n: base64.b64encode(open(os.path.join(HERE, n), "rb").read()).decode("ascii") for n in ("keiba_v47.py", "kosatsu_v47.py", "runner.py")}
json.dump(version, open(os.path.join(HERE, "version.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(HERE, "bundle.js"), "w", encoding="utf-8") as f:
    f.write("// build.py が自動で作るファイル。手で編集しない。\n")
    f.write("const BUNDLE = " + json.dumps({"version": version, "files": files}, ensure_ascii=False) + ";\n")
print(json.dumps(version, ensure_ascii=False, indent=1))
