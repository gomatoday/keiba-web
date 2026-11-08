# -*- coding: utf-8 -*-
"""Web版の受け渡し役（Pyodide上で動く）。計算はすべて keiba_v47.py（分析計算v4.7.py と同一ファイル）が行う。
このファイルは、ファイルの受け渡し・標準出力の取り込み・正解データとの比較だけを行い、予測ロジックを持たない。"""
import io, json, re, math, contextlib, importlib.util, sys

ENGINE_PATH = "/app/keiba_v47.py"
KOSATSU_PATH = "/app/kosatsu_v47.py"
_eng = None
_kos = None


def load_engine():
    """keiba_v47.py を読み込み、指紋とlxmlの有無を返す。lxmlが無いとPC版と解析器が変わるため、呼び出し側で停止する。"""
    global _eng
    spec = importlib.util.spec_from_file_location("keiba_v47", ENGINE_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _eng = m
    try:
        import lxml  # noqa: F401
        from bs4 import BeautifulSoup
        BeautifulSoup("<p>x</p>", "lxml")
        lx = True
    except Exception:
        lx = False
    global _kos
    spec = importlib.util.spec_from_file_location("kosatsu_v47", KOSATSU_PATH)
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    _kos = k
    return json.dumps({"code": m.code_sha(), "version": m.VERSION, "lxml": lx,
                       "code_k": k.code_sha(), "version_k": k.RULE_VERSION,
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


# ---------------- 正解データとの比較（計画書■17の基準） ----------------
REL_TOL = 1e-9


def _plain(x):
    if isinstance(x, dict):
        return [["-".join(map(str, k)) if isinstance(k, tuple) else str(k), v] for k, v in x.items()]
    return x


def _cmp_num(a, b, path, st):
    """数値の比較。完全一致の件数と、相対誤差の最大値を記録する。"""
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        if a != b:
            st["diff"].append(path)
        return
    st["n"] += 1
    if a == b:
        st["exact"] += 1
        return
    d = abs(a - b) / max(abs(a), abs(b), 1e-300)
    st["maxrel"] = max(st["maxrel"], d)
    if d > REL_TOL:
        st["diff"].append("%s: %r != %r" % (path, a, b))


def _walk(a, b, path, st):
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            st["diff"].append(path + ": 長さ %d != %d" % (len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, "%s[%d]" % (path, i), st)
    elif isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            st["diff"].append(path + ": キー不一致")
            return
        for k in a:
            _walk(a[k], b[k], path + "." + str(k), st)
    else:
        _cmp_num(a, b, path, st)


def golden_check(html_path, golden_json):
    """正解データ（PC版Pythonの出力）と、このブラウザでの実行結果を比べる。
    判定: 出力全文とREC行は完全一致、丸め前の内部値（softmax・三連複確率・z得点）は相対誤差1e-9以内。"""
    g = json.loads(golden_json)
    calls = {"softmax": [], "trio_probs": [], "z_scores": []}
    orig = {}
    for name in calls:
        f = getattr(_eng, name)
        orig[name] = f

        def wrap(*a, _f=f, _n=name, **k):
            r = _f(*a, **k)
            calls[_n].append({"args": [_plain(x) for x in a], "kw": k, "ret": _plain(r)})
            return r
        setattr(_eng, name, wrap)
    try:
        rc, out, rec = _run_predict(html_path)
    finally:
        for name, f in orig.items():
            setattr(_eng, name, f)
    st = {"n": 0, "exact": 0, "maxrel": 0.0, "diff": []}
    _walk(json.loads(json.dumps(calls)), g["internals"], "internals", st)
    stdout_same = (out == g["stdout"])
    rec_same = (rec == g["rec"])
    first_diff = None
    if not stdout_same:
        a, b = out.splitlines(), g["stdout"].splitlines()
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "(なし)"
            y = b[i] if i < len(b) else "(なし)"
            if x != y:
                first_diff = {"line": i + 1, "web": x[:300], "python": y[:300]}
                break
    ok = (rc == g["rc"]) and stdout_same and rec_same and not st["diff"]
    return json.dumps({"race_id": (g.get("rec") or {}).get("race_id"), "ok": ok, "rc_same": rc == g["rc"],
                       "stdout_same": stdout_same, "rec_same": rec_same,
                       "internals_n": st["n"], "internals_exact": st["exact"], "internals_maxrel": st["maxrel"],
                       "internals_diff": st["diff"][:10], "first_stdout_diff": first_diff,
                       "golden_code": g.get("engine_code"), "golden_python": g.get("python")}, ensure_ascii=False)


# ---------------- Phase 2: 結果の考察（考察計算v4.7.py の kosatsu をそのまま実行） ----------------
def _run_kosatsu(bunseki_path, result):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = _kos.kosatsu(bunseki_path, result)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    out = buf.getvalue()
    m = re.search(r"^LEDGER (\{.*\})\s*$", out, re.M)
    rid = re.search(r"レースID=(\d+)", out)
    return rc, out, (json.loads(m.group(1)) if m else None), (rid.group(1) if rid else None)


def kosatsu(bunseki_path, result):
    rc, out, led, rid = _run_kosatsu(bunseki_path, result)
    return json.dumps({"rc": rc, "stdout": out, "ledger": led, "race_id": rid}, ensure_ascii=False)


def kosatsu_check(golden_json):
    """Phase 2の正解データ（PC版Pythonの考察出力）と比べる。分析出力（正解データのもの）と結果の文字列を入力に、出力全文が完全一致すること。"""
    g = json.loads(golden_json)
    p = "/work/kosatsu_test_bunseki.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(g["bunseki_stdout"])
    rc, out, led, rid = _run_kosatsu(p, g["result"])
    same = out == g["kosatsu_stdout"]
    first = None
    if not same:
        a, b = out.splitlines(), g["kosatsu_stdout"].splitlines()
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "(なし)"
            y = b[i] if i < len(b) else "(なし)"
            if x != y:
                first = {"line": i + 1, "web": x[:300], "python": y[:300]}
                break
    return json.dumps({"race_id": g["race_id"], "kind": g.get("kind"), "result": g["result"], "ok": same and rc == g["rc"],
                       "rc_same": rc == g["rc"], "stdout_same": same, "first_stdout_diff": first,
                       "golden_code": g.get("kosatsu_code"), "golden_python": g.get("python")}, ensure_ascii=False)


# ---------------- Phase 3: 記録のLEDGER行の照合（考察計算v4.7.py の read_ledger をそのまま使う） ----------------
def ledger_check(text):
    """LEDGER行を集めた文字列を、考察計算の read_ledger で照合する（版・指紋・再計算・重複）。集計（Δ等）は出さない。"""
    p = "/work/ledger_check.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        L, study, stops = _kos.read_ledger(p)
    except (ValueError, OSError) as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({"ok": True, "n": len(L)}, ensure_ascii=False)


# ---------------- Phase 4: 集計（考察計算v4.7.py の aggregate をそのまま実行） ----------------
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
    """Phase 4の正解データ（PC版Pythonのaggregate出力）と比べる。同じLEDGER行のファイルから、出力全文が完全一致すること。"""
    g = json.loads(golden_json)
    rc, out = _run_aggregate(g["ledger_text"])
    same = out == g["aggregate_stdout"]
    first = None
    if not same:
        a, b = out.splitlines(), g["aggregate_stdout"].splitlines()
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "(なし)"
            y = b[i] if i < len(b) else "(なし)"
            if x != y:
                first = {"line": i + 1, "web": x[:300], "python": y[:300]}
                break
    return json.dumps({"race_id": g["name"], "ok": same and rc == g["rc"], "rc_same": rc == g["rc"], "stdout_same": same,
                       "first_stdout_diff": first, "golden_code": g.get("kosatsu_code"), "golden_python": g.get("python")}, ensure_ascii=False)
