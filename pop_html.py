# -*- coding: utf-8 -*-
"""結果ページ（成績・払戻金）から、全馬の単勝人気・単勝の払戻と人気・三連複の払戻と人気を読み取り、POP行（1行のJSON）にする。
次版の検討用の記録で、予測・考察の計算は持たない。result_html.py は変えずに、そのレースIDの特定（見出しと /syousai/ リンクの照合）を使う。
読み取れない・食い違う場合は、推測で補わずに errors に書く（errors が空のときだけ使ってよい）。
使い方（PC）: python pop_html.py 結果ページ.txt   （同じフォルダの 分析計算v4.7.py と result_html.py を読み込む。標準出力に POP 行）"""
import re, os, sys, json, hashlib, importlib.util

POP_VERSION = "pop-1"


def code_sha(path=None):
    p = path or os.path.abspath(__file__)
    return hashlib.sha256(re.sub(r"\s+", "", open(p, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def _txt(x):
    return re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()


def _int(s):
    s = (s or "").replace(",", "").strip()
    return int(s) if re.fullmatch(r"\d+", s) else None


def _pay_rows(soup, kind):
    """払戻表で、行見出し（th）が kind の行と、rowspan で続く行の（組番, 金額, 人気）。"""
    out = []
    for th in soup.find_all("th"):
        if _txt(th) != kind or th.find_parent("thead") is not None:
            continue
        span = int(th.get("rowspan") or 1)
        cur = th.find_parent("tr")
        for _ in range(span):
            if cur is None:
                break
            tds = [_txt(x) for x in cur.find_all("td")]
            if len(tds) >= 3:
                out.append({"組": tds[0], "払戻": _int(tds[1]), "人気": _int(tds[2])})
            cur = cur.find_next_sibling("tr")
        break
    return out


def parse_pop(raw_bytes, decode_html, result_html):
    """戻り値: dict（pver, race_id, pop{馬番:人気}, finish[{着, 馬番, 人気}], 単勝[], 三連複[], errors, notes）。"""
    from bs4 import BeautifulSoup
    out = {"pver": POP_VERSION, "code_p": code_sha(), "race_id": None, "date": None, "venue": None, "rno": None,
           "pop": {}, "finish": [], "単勝": [], "三連複": [], "errors": [], "notes": []}
    base = result_html.parse_result_html(raw_bytes, decode_html)
    out.update({k: base.get(k) for k in ("race_id", "date", "venue", "rno")})
    if not base.get("race_id"):
        out["errors"].append("レースIDを特定できません（%s）" % "、".join(base.get("errors") or []))
        return out
    if base.get("errors"):
        out["notes"].append("結果の読み取りの注意: " + "、".join(base["errors"]))
    s, enc = decode_html(raw_bytes)
    soup = BeautifulSoup(s, "lxml")
    fin = None
    for t in soup.find_all("table"):
        hs = [_txt(x) for x in t.find_all("th")]
        if hs[:3] == ["着", "枠", "馬番"]:
            fin, heads = t, hs
            break
    if fin is None:
        out["errors"].append("着順の表がありません")
        return out
    if "人気" not in heads:
        out["errors"].append("着順の表に「人気」の列がありません")
        return out
    iu, ip = heads.index("馬番"), heads.index("人気")
    for tr in fin.find_all("tr"):
        tds = [_txt(x) for x in tr.find_all("td")]
        if len(tds) < 3:
            continue
        if len(tds) != len(heads):
            out["errors"].append("着順の表の列数が見出しと合いません（見出し%d・行%d）: %s" % (len(heads), len(tds), tds[:3]))
            return out
        u = _int(tds[iu])
        if u is None:
            out["errors"].append("馬番を読めない行: %s" % tds[:3])
            return out
        if u in out["pop"]:
            out["errors"].append("馬番%dが重複しています" % u)
            return out
        p = _int(tds[ip])
        out["pop"][u] = p
        out["finish"].append({"着": tds[0], "馬番": u, "人気": p})
    ps = [p for p in out["pop"].values() if p is not None]
    if not ps:
        out["errors"].append("人気を1頭も読めません")
        return out
    if sorted(ps) != list(range(1, len(ps) + 1)):
        out["notes"].append("人気が1〜%dの連番になっていません: %s" % (len(ps), sorted(ps)))
    nopop = [u for u, p in out["pop"].items() if p is None]
    if nopop:
        out["notes"].append("人気のない馬番（取消・除外など）: %s" % nopop)
    out["単勝"] = _pay_rows(soup, "単勝")
    out["三連複"] = _pay_rows(soup, "三連複")
    if not out["単勝"]:
        out["notes"].append("単勝の払戻を読めません")
    if not out["三連複"]:
        out["notes"].append("三連複の払戻を読めません")
    out["pop"] = {str(k): v for k, v in out["pop"].items()}
    return out


def pop_line(p):
    return "POP " + json.dumps(p, ensure_ascii=False, separators=(",", ":"))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    eng_path = next((os.path.join(here, n) for n in ("分析計算v4.7.py", "keiba_v47.py") if os.path.exists(os.path.join(here, n))), None)
    rh_path = os.path.join(here, "result_html.py")
    if not eng_path or not os.path.exists(rh_path):
        print("【停止】同じフォルダに 分析計算v4.7.py と result_html.py が必要です")
        return 1
    eng, rh = _load(eng_path, "keiba_v47"), _load(rh_path, "result_html")
    p = parse_pop(open(sys.argv[1], "rb").read(), eng.decode_html, rh)
    if p["errors"]:
        print("【停止】" + "、".join(p["errors"]))
        return 1
    print(pop_line(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
