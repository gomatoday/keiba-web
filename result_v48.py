# -*- coding: utf-8 -*-
"""result_v48.py  結果ページ（成績・払戻金）から、着順と全券種の払戻を読み取り、考察計算v4.8 に渡す結果（RES の JSON）を作る。
入力の補助で、予測・考察の計算は持たない。レースIDの特定・着順・三連複は result_html.py（v4.7 と同じ）をそのまま使い、
払戻表の各券種は pop_html.py の読み取りを使う。全馬の人気（POP）も一緒に返す（記録用）。
読み取れない・食い違う場合は、推測で補わずに誤りとして返す（errors が空のときだけ使ってよい）。"""
import json

LABELS = {"単勝": "単勝", "複勝": "複勝", "馬連": "普通馬複", "ワイド": "ワイド", "馬単": "馬単", "三連複": "三連複", "三連単": "三連単"}


def parse(raw_bytes, decode_html, result_html, pop_html):
    from bs4 import BeautifulSoup
    base = result_html.parse_result_html(raw_bytes, decode_html)
    out = {"race_id": base.get("race_id"), "venue": base.get("venue"), "rno": base.get("rno"), "date": base.get("date"),
           "errors": list(base.get("errors") or []), "notes": list(base.get("notes") or []), "res": None, "pop": None}
    if out["errors"]:
        return out
    s, _ = decode_html(raw_bytes)
    soup = BeautifulSoup(s, "lxml")
    pays = {}
    for t, lab in LABELS.items():
        rows = pop_html._pay_rows(soup, lab)
        pays[t] = [{"組": r["組"], "払戻": r["払戻"]} for r in rows if r["払戻"]]
        if not pays[t]:
            out["notes"].append("%sの払戻を読めません" % t)
    # 三連複は result_html.py の読み取りと一致すること
    trio_a = sorted(("-".join(str(u) for u in g["combo"]), g["pay"]) for g in base["trio"])
    trio_b = sorted(("-".join(str(u) for u in sorted(int(x) for x in r["組"].split("-"))), r["払戻"]) for r in pays["三連複"])
    if trio_a != trio_b:
        out["errors"].append("三連複の払戻の読み取りが食い違います（%s ／ %s）" % (trio_a, trio_b))
        return out
    orders = [g["order"] for g in base["trio"]]
    out["res"] = {"race_id": out["race_id"], "orders": orders, "pays": pays, "source": "結果ページ"}
    p = pop_html.parse_pop(raw_bytes, decode_html, result_html)
    out["pop"] = p if not p["errors"] else None
    if p["errors"]:
        out["notes"].append("人気の読み取り: " + "、".join(p["errors"]))
    return out


def res_string(res):
    return "RES " + json.dumps(res, ensure_ascii=False, separators=(",", ":"))


def main():
    """PC用: python result_v48.py <結果ページ.html>  → RES 行を表示（考察計算v4.8.py kosatsu の第2引数にそのまま使える）。"""
    import sys, os, importlib.util
    if len(sys.argv) < 2:
        print(main.__doc__)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))

    def load(names, mod):
        for n in names:
            p = os.path.join(here, n)
            if os.path.exists(p):
                spec = importlib.util.spec_from_file_location(mod, p)
                m = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(m)
                return m
        raise FileNotFoundError("、".join(names) + " が同じフォルダにありません")
    sys.path.insert(0, here)
    e47 = load(["分析計算v4.7.py", "keiba_v47.py"], "keiba_v47")
    rh = load(["result_html.py"], "result_html")
    ph = load(["pop_html.py"], "pop_html")
    r = parse(open(sys.argv[1], "rb").read(), e47.decode_html, rh, ph)
    for n in r["notes"]:
        print("注意: " + n)
    if r["errors"]:
        print("【停止】" + "、".join(r["errors"]))
        return 1
    print(res_string(r["res"]))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
