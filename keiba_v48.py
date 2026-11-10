# -*- coding: utf-8 -*-
"""分析計算v4.8.py（Web版のファイル名は keiba_v48.py。中身は同一）  南関東 全券種の期待値と仮想購入（当日のオッズ不使用）
使い方: python 分析計算v4.8.py predict <出走表.html> [会場+R番号 例: 浦和12R]
同じフォルダに 分析計算v4.7.py（または keiba_v47.py）・候補抽出.py（または feat_extract.py）・v48_model.py・v48_params.json を置く。
v4.8:
 (1) v4.7 の計算（分析計算v4.7.py）をそのまま実行し、7項目の寄与と、比較用の v4.7 の勝率（逃げ補正+0.9）・ref45 の勝率を得る（v4.7 の出力は記録として REC に含める）。
 (2) 候補抽出で出走表から項目を抜き出し、予想のモデル（7項目の係数＋g、⑤内枠外枠、⑥人気）で勝率を出す。逃げ補正はない。
 (3) 市場の予測モデル（出走表から当日の単勝人気を予測。F6）で支持率を出し、自分と組み合わせた着順モデルで全券種の確率を出す。
 (4) 券種ごとの払戻の見積もりで期待値を出し、4案（案1〜案4）を仮想購入する（実際の馬券は買わない）。
 (5) 係数はすべて v48_params.json（304レースの設計用データで作って固定）。新馬モードは v4.7 のまま（評価の対象外）。初出走馬と経験馬が混在するレースは見送り。
確率の記録: 勝率・支持率は小数9桁に丸めてRECに書き、券種の確率と期待値は丸めた値から計算する（考察計算v4.8で同じ値を再計算できるようにするため）。"""
import sys, os, io, re, json, math, contextlib, importlib.util, hashlib

VERSION = "v4.8"
HERE = os.path.dirname(os.path.abspath(__file__))


def _load(names, mod):
    for n in names:
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location(mod, p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise SystemExit("エラー: 同じフォルダに %s がありません" % " または ".join(names))


E47 = _load(["分析計算v4.7.py", "keiba_v47.py"], "keiba_v47")
FX = _load(["候補抽出.py", "feat_extract.py"], "feat_extract")
M = _load(["v48_model.py"], "v48_model")
PAR = M.load_params()


def code_sha():
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.abspath(__file__), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def fingerprints():
    return {"code": code_sha(), "code_m": M.code_sha(), "code_p": PAR["_sha"], "code_a47": E47.code_sha(), "code_f": FX.code_sha()}


def r9(xs):
    return [round(x, 9) for x in xs]


def _run47(path, expect):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = E47.predict(path, expect or None)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    out = buf.getvalue()
    m = re.search(r"^REC (\{.*\})\s*$", out, re.M)
    return rc, out, (json.loads(m.group(1)) if m else None)


def tbl(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def header(fp):
    print("[コード指紋 sha256先頭12桁=%s]" % fp["code"])
    print("指紋: v48_model=%s ／ 係数=%s ／ 分析計算v4.7=%s ／ 候補抽出=%s" % (fp["code_m"], fp["code_p"], fp["code_a47"], fp["code_f"]))
    print("")


def compute(rec47, feat):
    """通常モードの1レース。REC48 の中身（辞書）を返す。"""
    nums = rec47["nums"]
    hm = {h["n"]: h for h in rec47["hs"]}
    C = [hm[u]["c"][:7] for u in nums]
    vals, CAND, EX = M.race_inputs(feat, C)
    u48, p48 = M.model_probs(PAR, C, CAND, EX)
    u48np, p48np = M.model_probs(PAR, C, CAND, EX, pos_zero=True)
    s_m, q = M.market_probs(PAR, C, CAND, EX)
    p48, p48np, q = r9(p48), r9(p48np), r9(q)
    c = r9(M.combined_probs(PAR, p48, q))
    ts = M.tickets(PAR, nums, c, q)
    plans = {}
    for pl in M.PLANS:
        sel = M.plan_select(ts, pl)
        plans[pl[0]] = [{"t": t, "k": k, "pc": round(pc, 9), "pm": round(pm, 9), "pay": round(pay, 1), "ev": round(ev, 6)} for t, k, pc, pm, pay, ev in sel]
    hv = [{"n": u, "days": v["days"], "chg": v["change"], "dkg": v["dkg"], "trf": v["transfer"], "x": round(v["x"], 6),
           "pa": round(v["pop_avg"], 6), "pg": round(v["pop_gap"], 6)} for u, v in zip(nums, vals)]
    return {"nums": nums, "u48": [round(x, 9) for x in u48], "p48": p48, "u48np": [round(x, 9) for x in u48np], "p48np": p48np,
            "g48": PAR["own"]["g"], "q": q, "g_m": PAR["market"]["g"], "c": c, "g_c": PAR["comb"]["g"],
            "p47": rec47["p_win"], "p45": rec47["ref45"]["p_win"], "g47": rec47["par"]["g"], "plans": plans, "hv": hv,
            "best": max(ts, key=lambda x: x[5])[5] if ts else None, "n_tickets": len(ts)}


def predict(path, expect=None):
    fp = fingerprints()
    rc47, out47, rec47 = _run47(path, expect)
    raw = open(path, "rb").read()
    if rec47 is None:
        # v4.7 が停止・見送り・エラー（買い目なし）。v4.7 の出力の要点をそのまま示す
        header(fp)
        lines = [l for l in out47.splitlines() if l.strip() and not l.startswith("[コード指紋")]
        kind = "見送り" if "見送り" in out47 else "停止"
        print("**【%s %s】** v4.7 の計算で%sになりました（v4.8 でも同じ扱い）。" % (kind, VERSION, kind))
        print("")
        for l in lines:
            print(l)
        return rc47
    if rec47["mode"] == "新馬":
        header(fp)
        print("**【新馬モード %s】** レースID=%s ／ %s ／ %sm ／ %d頭。v4.7 の計算のまま（評価の対象外。4案の買い目は出さない）。" %
              (VERSION, rec47["race_id"], rec47["venue"], rec47["dist"], rec47["heads"]))
        print("")
        rec = dict(fp, ver=VERSION, mode="新馬", race_id=rec47["race_id"], venue=rec47["venue"], dist=rec47["dist"], heads=rec47["heads"],
                   nums=rec47["nums"], qual=rec47.get("q"), warnings=rec47.get("warnings", []), rec47=rec47)
        print("予想レコード（下のコードブロックを結果の考察用に保存）:")
        print("")
        print("```")
        print("REC " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
        print("```")
        return 0
    feat, err = FX.extract(raw, E47)
    if err:
        header(fp)
        print("【停止】候補抽出: " + err)
        return 1
    if feat["nums"] != rec47["nums"]:
        header(fp)
        print("【停止】候補抽出と分析計算v4.7 で馬番の並びが違います（%s ／ %s）" % (feat["nums"], rec47["nums"]))
        return 1
    R = compute(rec47, feat)
    warns = list(rec47.get("warnings", [])) + ["候補抽出: " + w for w in feat.get("warnings", [])]
    rec = dict(fp, ver=VERSION, mode="通常", race_id=rec47["race_id"], venue=rec47["venue"], dist=rec47["dist"], heads=rec47["heads"],
               qual=rec47.get("q"), warnings=warns, **R)
    rec["rec47"] = rec47
    nums = R["nums"]
    names = {h["馬番"]: (h["馬名"], h["騎手"]) for h in feat["horses"]}
    header(fp)
    print("**【予想 %s】** レースID=%s ／ %s ／ %sm ／ %d頭" % (VERSION, rec["race_id"], rec["venue"], rec["dist"], rec["heads"]))
    print("")
    for w in warns:
        print("警告: " + w)
        print("")
    print("**馬別の確率**（v4.8＝予想のモデル。市場＝出走表から予測した当日の単勝の支持率。組み合わせ＝v4.8と市場を組み合わせた勝率。v4.7＝比較用）")
    print("")
    order = sorted(range(len(nums)), key=lambda i: -R["c"][i])
    print(tbl(["馬番", "馬名", "騎手", "v4.8", "市場（予測）", "組み合わせ", "v4.7"],
              [[nums[i], names[nums[i]][0], names[nums[i]][1], "%.1f%%" % (100 * R["p48"][i]), "%.1f%%" % (100 * R["q"][i]),
                "%.1f%%" % (100 * R["c"][i]), "%.1f%%" % (100 * R["p47"][i])] for i in order]))
    print("")
    print("**仮想購入（4案。各100円。実際の馬券は買わない）** 期待値＝組み合わせた確率×見積もった払戻÷100。見積もった払戻は当日のオッズではなく、予測した市場の支持率からの推定")
    print("")
    for name, th, cap, types in M.PLANS:
        sel = R["plans"][name]
        cond = "期待値%.2f以上%s（%s）" % (th, "・期待値の高い順に最大%d点" % cap if cap else "・点数の制限なし", "全券種" if len(types) > 1 else "・".join(types))
        if not sel:
            print("%s: 見送り（%s の買い目なし。このレースの最大の期待値=%.3f）" % (name, cond, R["best"]))
            print("")
            continue
        print("%s: %d点（%s）" % (name, len(sel), cond))
        print("")
        print(tbl(["券種", "買い目", "組み合わせた確率", "見積もった払戻", "期待値"],
                  [[x["t"], x["k"], "%.2f%%" % (100 * x["pc"]), "%d円" % round(x["pay"]), "%.3f" % x["ev"]] for x in sel[:30]]))
        if len(sel) > 30:
            print("")
            print("（ほか%d点。全部は予想レコードに記録）" % (len(sel) - 30))
        print("")
    print("予想レコード（下のコードブロックを結果の考察用に保存）:")
    print("")
    print("```")
    print("REC " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    print("```")
    return 0


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "predict":
        return predict(a[1], " ".join(a[2:]) if len(a) > 2 else None)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
