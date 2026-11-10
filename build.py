# -*- coding: utf-8 -*-
"""bundle.js と version.json を作る。計算に使う .py と係数（v49_params.json・v48_params.json）を、1バイトも変えずにbase64で埋め込む
（ブラウザで index.html を直接開いても動くようにするため）。指紋は分析計算・考察計算と同じ式で計算する。
使い方: python build.py"""
import base64, json, hashlib, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
PYODIDE = "0.29.5"
FILES = ("keiba_v49.py", "kosatsu_v49.py", "v49_model.py", "v49_params.json", "v48_model.py", "v48_params.json", "keiba_v47.py", "feat_extract.py",
         "result_html.py", "pop_html.py", "result_v49.py", "runner.py")


def code_sha(name):
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.join(HERE, name), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def full_sha(name):
    return hashlib.sha256(open(os.path.join(HERE, name), "rb").read()).hexdigest()


version = {
    "version": "v4.9",
    "code": code_sha("keiba_v49.py"),
    "engine_file": "keiba_v49.py（分析計算v4.9.py と同一内容）",
    "code_k": code_sha("kosatsu_v49.py"),
    "kosatsu_file": "kosatsu_v49.py（考察計算v4.9.py と同一内容）",
    "code_m": code_sha("v49_model.py"),
    "code_p": code_sha("v49_params.json"),
    "code_a47": code_sha("keiba_v47.py"),
    "code_f": code_sha("feat_extract.py"),
    "code_m48": code_sha("v48_model.py"),
    "code_p48": code_sha("v48_params.json"),
    "full_sha256": {n: full_sha(n) for n in FILES},
    "pyodide": PYODIDE,
    "pyodide_url": "https://cdn.jsdelivr.net/pyodide/v%s/full/" % PYODIDE,
    "python_minor": "3.13",
}
files = {n: base64.b64encode(open(os.path.join(HERE, n), "rb").read()).decode("ascii") for n in FILES}
json.dump(version, open(os.path.join(HERE, "version.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with open(os.path.join(HERE, "bundle.js"), "w", encoding="utf-8") as f:
    f.write("// build.py が自動で作るファイル。手で編集しない。\n")
    f.write("const BUNDLE = " + json.dumps({"version": version, "files": files}, ensure_ascii=False) + ";\n")
print(json.dumps({k: v for k, v in version.items() if k != "full_sha256"}, ensure_ascii=False, indent=1))
