# -*- coding: utf-8 -*-
"""Web版の受け渡し役（Pyodide上で動く）。計算はすべて keiba_v49.py（分析計算v4.9.py と同一）・kosatsu_v49.py（考察計算v4.9.py と同一）が行う。
keiba_v49.py は、同じ場所の keiba_v47.py（分析計算v4.7.py と同一）・feat_extract.py（候補抽出.py と同一）・v49_model.py・v49_params.json・v48_model.py・v48_params.json を読み込む。
このファイルは、ファイルの受け渡し・標準出力の取り込み・正解データとの比較だけを行い、予測ロジックを持たない。"""
import io, json, re, contextlib, importlib.util, sys

APP = "/app"
_eng = None     # keiba_v49
_kos = None     # kosatsu_v49


def _load(name):
    spec = importlib.util.spec_from_file_location(name, "%s/%s.py" % (APP, name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_engine():
    """keiba_v49.py・kosatsu_v49.py を読み込み、指紋とlxmlの有無を返す。lxmlが無いとPC版と解析器が変わるため、呼び出し側で停止する。"""
    global _eng, _kos
    if APP not in sys.path:
        sys.path.insert(0, APP)
    _eng = _load("keiba_v49")
    _kos = _load("kosatsu_v49")
    try:
        import lxml  # noqa: F401
        from bs4 import BeautifulSoup
        BeautifulSoup("<p>x</p>", "lxml")
        lx = True
    except Exception:
        lx = False
    fp = _eng.fingerprints()
    return json.dumps({"code": fp["code"], "code_m": fp["code_m"], "code_p": fp["code_p"], "code_a47": fp["code_a47"], "code_f": fp["code_f"], "code_m48": fp["code_m48"], "code_p48": fp["code_p48"],
                       "version": _eng.VERSION, "lxml": lx, "code_k": _kos.code_sha(), "version_k": _kos.RULE_VERSION,
                       "python": sys.version.split()[0]})


def _run_predict(html_path, expect=None):
    buf = io.StringIO()
    rc = None
    with contextlib.redirect_stdout(buf):
        try:
            rc = _eng.predict(html_path, expect or None)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    out = buf.getvalue()
    m = re.search(r"^REC (\{.*\})\s*$", out, re.M)
    return rc, out, (json.loads(m.group(1)) if m else None)


def analyze(html_path, expect=""):
    rc, out, rec = _run_predict(html_path, expect)
    return json.dumps({"rc": rc, "stdout": out, "rec": rec}, ensure_ascii=False)


def _first_diff(a, b):
    a, b = a.splitlines(), b.splitlines()
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "(なし)"
        y = b[i] if i < len(b) else "(なし)"
        if x != y:
            return {"line": i + 1, "web": x[:300], "python": y[:300]}
    return None


def golden_check(html_path, golden_json):
    """正解データ（PC版Pythonの出力）と、このブラウザでの実行結果を比べる。判定: 終了コード・出力全文・REC行が完全一致。"""
    g = json.loads(golden_json)
    rc, out, rec = _run_predict(html_path)
    same = out == g["stdout"]
    return json.dumps({"race_id": (g.get("rec") or {}).get("race_id") or g.get("race_id"), "ok": rc == g["rc"] and same and rec == g["rec"],
                       "rc_same": rc == g["rc"], "stdout_same": same, "rec_same": rec == g["rec"],
                       "first_stdout_diff": None if same else _first_diff(out, g["stdout"]), "golden_python": g.get("python")}, ensure_ascii=False)


# ---------------- 結果の考察（考察計算v4.9.py の kosatsu をそのまま実行） ----------------
def _run_kosatsu(bunseki_path, res_text):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = _kos.kosatsu(bunseki_path, res_text)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    out = buf.getvalue()
    m = re.search(r"^LEDGER (\{.*\})\s*$", out, re.M)
    rid = re.search(r"レースID=(\d+)", out)
    return rc, out, (json.loads(m.group(1)) if m else None), (rid.group(1) if rid else None)


def kosatsu(bunseki_path, res_text):
    rc, out, led, rid = _run_kosatsu(bunseki_path, res_text)
    return json.dumps({"rc": rc, "stdout": out, "ledger": led, "race_id": rid}, ensure_ascii=False)


def kosatsu_check(golden_json):
    """考察の正解データ（PC版Pythonの考察出力）と比べる。分析出力と結果（RES）を入力に、出力全文が完全一致すること。"""
    g = json.loads(golden_json)
    p = "/work/kosatsu_test_bunseki.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(g["bunseki_stdout"])
    rc, out, led, rid = _run_kosatsu(p, g["result"])
    same = out == g["kosatsu_stdout"]
    return json.dumps({"race_id": g["race_id"], "kind": g.get("kind"), "result": g["result"][:120], "ok": same and rc == g["rc"],
                       "rc_same": rc == g["rc"], "stdout_same": same, "first_stdout_diff": None if same else _first_diff(out, g["kosatsu_stdout"]),
                       "golden_python": g.get("python")}, ensure_ascii=False)


# ---------------- 記録のLEDGER行の照合（考察計算v4.9.py の read_ledger をそのまま使う） ----------------
def ledger_check(text):
    p = "/work/ledger_check.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        L, study, stops = _kos.read_ledger(p)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({"ok": True, "n": len(L)}, ensure_ascii=False)


# ---------------- 集計（考察計算v4.9.py の aggregate をそのまま実行） ----------------
def _run_aggregate(text):
    p = "/work/aggregate_input.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = _kos.aggregate(p)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def aggregate(text):
    rc, out = _run_aggregate(text)
    return json.dumps({"rc": rc, "stdout": out}, ensure_ascii=False)


def aggregate_check(golden_json):
    g = json.loads(golden_json)
    rc, out = _run_aggregate(g["ledger_text"])
    same = out == g["aggregate_stdout"]
    return json.dumps({"race_id": g["name"], "ok": same and rc == g["rc"], "rc_same": rc == g["rc"], "stdout_same": same,
                       "first_stdout_diff": None if same else _first_diff(out, g["aggregate_stdout"]), "golden_python": g.get("python")}, ensure_ascii=False)


# ---------------- 結果ページの読み取り（入力の補助。考察の計算には関わらない） ----------------
def result_parse(path):
    """result_v49.py で着順・券種の払戻・全馬の人気と着順を読む。res_text は考察計算に渡す "RES {...}" の1行。"""
    import result_html, pop_html, result_v49
    with open(path, "rb") as f:
        b = f.read()
    r = result_v49.parse(b, _eng.E47.decode_html, result_html, pop_html)
    r["res_text"] = result_v49.res_string(r["res"]) if r["res"] else None
    return json.dumps(r, ensure_ascii=False)


def result_check(path, golden_json):
    """結果ページの読み取りが、PC版Pythonでの読み取り（正解データ）と完全一致するか。"""
    g = json.loads(golden_json)
    r = json.loads(result_parse(path))
    return json.dumps({"race_id": g["parse"].get("race_id"), "ok": r == g["parse"], "web": (r.get("res_text") or "")[:120],
                       "python": (g["parse"].get("res_text") or "")[:120], "errors": r.get("errors")}, ensure_ascii=False)
