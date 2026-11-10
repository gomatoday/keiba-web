# -*- coding: utf-8 -*-
"""分析計算v4.9.py（Web版のファイル名は keiba_v49.py。中身は同一）  南関東 v4.9: 予想の本体を市場の予測モデルにし、単勝・複勝・ワイド・馬連の期待値と3案の仮想購入を出す。
v4.9:
 (1) 出走表の読み取り・品質の確認・モード判定・7項目の寄与は、分析計算v4.7.py の関数をそのまま呼ぶ（v4.7 のファイルは変えない）。
     v4.7 の勝率・切り捨て・三連複の買い目・マークシートは計算しない（高速化）。新馬モードは評価の対象外で、確率も買い目も出さない。
 (2) 予想の本体: 市場の予測モデル（57項目。v49_model.py・v49_params.json）。スコア s、予測した支持率 q = softmax(s)。
 (3) 着順の確率: 1着 softmax(a1·s)、2・3着 softmax(a2·s)。券種は単勝・複勝・ワイド・馬連（三連複・三連単・馬単は外した）。
 (4) 3案: 案A＝予測1位の単勝（q1が境目以上）、案B＝複勝の期待値0.9以上、案C＝予測1位の複勝（q1が境目以上）。実際の馬券は買わない。
 (5) 比較用: v4.8 の予想のモデルの勝率 p48（v48_model.py・v48_params.json。変えない）を同じレースで計算して記録する。
 (6) 当日のオッズ・人気は使わない。過去走の人気は使う。馬体重は使わない。
使い方: python 分析計算v4.9.py predict <出走表HTML> [会場名+R番号 例: 川崎2R]"""
import sys, os, re, json, hashlib, importlib.util

VERSION = "v4.9"
HERE = os.path.dirname(os.path.abspath(__file__))


def _load(names, mod):
    for n in names:
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location(mod, p)
            m = importlib.util.module_from_spec(spec)
            sys.modules[mod] = m
            spec.loader.exec_module(m)
            return m, p
    raise SystemExit("【停止】同じフォルダに %s がありません" % " または ".join(names))


if HERE not in sys.path:
    sys.path.insert(0, HERE)
E47, _P47 = _load(["分析計算v4.7.py", "keiba_v47.py"], "keiba_v47")
FX, _PFX = _load(["候補抽出.py", "feat_extract.py"], "feat_extract")
M, _PM = _load(["v49_model.py"], "v49_model")
PAR = M.load_params()
M48 = M.M48
PAR48 = M48.load_params()


def code_sha(path=None):
    p = path or os.path.abspath(__file__)
    return hashlib.sha256(re.sub(r"\s+", "", open(p, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def fingerprints():
    return {"code": code_sha(), "code_m": M.code_sha(), "code_p": PAR["_sha"], "code_a47": E47.code_sha(), "code_f": FX.code_sha(),
            "code_m48": M48.code_sha(), "code_p48": PAR48["_sha"]}


def compute(path, expect=None):
    """1レースの計算（出力はしない）。係数作成v4.9.py も同じ関数を使う。"""
    st, body = M.core47(E47, path, expect)
    if st != "normal":
        return st, body
    hdr, horses, warns, C = body
    nums = [h["num"] for h in horses]
    feat, ferr = FX.extract(open(path, "rb").read(), E47)
    if feat is None:
        return "stop", "【停止】候補抽出が止まりました: %s" % ferr
    for w in feat.get("warnings", []):
        warns.append("候補抽出: " + w)
    if feat["nums"] != nums:
        return "stop", "【停止】候補抽出と v4.7 の読み取りで馬番の並びが違います（%s ／ %s）" % (feat["nums"], nums)
    CAND, EX, NX = M.race_inputs(feat, C)
    X = M.design_rows(PAR, C, CAND, EX, NX)
    s = M.scores(PAR, X)
    ts = M.tickets(PAR, nums, s)
    pl, h1, q1 = M.plans(PAR, nums, s, ts)
    u48, p48 = M48.model_probs(PAR48, C, CAND, EX)
    a1, a2 = PAR["order"]["a1"], PAR["order"]["a2"]
    p1, w = M.stage(s, a1, a2)
    win = M.outcomes(p1, w)
    q = M.softmax(s)
    return "normal", dict(hdr=hdr, horses=horses, warns=warns, C=C, feat=feat, CAND=CAND, EX=EX, NX=NX, X=X, s=s, q=q, ts=ts, plans=pl, h1=h1, q1=q1,
                          u48=[round(x, 9) + 0.0 for x in u48], p48=[round(x, 9) + 0.0 for x in p48], win=win, nums=nums)


def tbl(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def _tk(x):
    return {"t": x[0], "k": x[1], "pc": round(x[2], 9), "pm": round(x[3], 9), "pay": round(x[4], 2), "ev": round(x[5], 6)}


def predict(path, expect=None):
    fp = fingerprints()
    st, body = compute(path, expect)
    print("[コード指紋 sha256先頭12桁=%s]" % fp["code"])
    print("[v49_model=%s ／ 係数=%s ／ 分析計算v4.7=%s ／ 候補抽出=%s ／ 比較用 v48_model=%s・係数=%s]" %
          (fp["code_m"], fp["code_p"], fp["code_a47"], fp["code_f"], fp["code_m48"], fp["code_p48"]))
    print("")
    if st in ("error", "stop"):
        print(body.replace("【停止】", "【停止 v4.9】") if st == "stop" else body)
        return 1
    if st == "mixed":
        hdr, horses, n_debut = body
        print("**【見送り v4.9】** レースID=%s ／ %s ／ %s%sm ／ %d頭" % (hdr["race_id"], hdr["venue"], hdr["surface"], hdr["dist"], len(horses)))
        print("")
        print("初出走馬と経験馬が混在するレースのため、買い目は出しません（初出走%d頭・経験%d頭）。" % (n_debut, len(horses) - n_debut))
        return 0
    if st == "debut":
        hdr, horses, warns = body
        nums = [h["num"] for h in horses]
        rec = {"ver": VERSION, "code": fp["code"], "code_m": fp["code_m"], "code_p": fp["code_p"], "code_a47": fp["code_a47"], "code_f": fp["code_f"],
               "code_m48": fp["code_m48"], "code_p48": fp["code_p48"], "mode": "新馬", "race_id": hdr["race_id"], "venue": hdr["venue"], "dist": hdr["dist"],
               "heads": len(horses), "nums": nums, "qual": hdr.get("quality"), "warnings": warns}
        print("**【新馬 v4.9】** レースID=%s ／ %s ／ %s%sm ／ %d頭" % (hdr["race_id"], hdr["venue"], hdr["surface"], hdr["dist"], len(horses)))
        print("")
        print("全頭が初出走のため、評価の対象外です（確率・買い目は出しません。記録のみ）。")
        print("")
        print("予想レコード（下のコードブロックを結果の考察用に保存）:")
        print("")
        print("```")
        print("REC " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
        print("```")
        return 0
    d = body
    hdr, horses, warns, nums, s = d["hdr"], d["horses"], d["warns"], d["nums"], d["s"]
    nh = len(nums)
    ts = d["ts"]
    tk = {(x[0], x[1]): x for x in ts}
    pl = d["plans"]
    rec = {"ver": VERSION, "code": fp["code"], "code_m": fp["code_m"], "code_p": fp["code_p"], "code_a47": fp["code_a47"], "code_f": fp["code_f"],
           "code_m48": fp["code_m48"], "code_p48": fp["code_p48"], "mode": "通常", "race_id": hdr["race_id"], "venue": hdr["venue"], "dist": hdr["dist"],
           "heads": nh, "nums": nums, "qual": hdr.get("quality"), "warnings": warns,
           "C": d["C"], "X": d["X"], "s": s, "a1": PAR["order"]["a1"], "a2": PAR["order"]["a2"], "q1": round(d["q1"], 9), "q1_cut": PAR["plans"]["q1_cut"],
           "u48": d["u48"], "p48": d["p48"], "g48": PAR48["own"]["g"],
           "plans": {k: [_tk(x) for x in v] for k, v in pl.items()},
           "tick": [_tk(x) for x in ts if x[0] in ("単勝", "複勝") or x[5] >= 0.8],
           "best": {t: round(max(x[5] for x in ts if x[0] == t), 6) for t in M.TYPES}}
    print("**【予想 %s】** レースID=%s ／ %s ／ %s%sm%s ／ %d頭" % (VERSION, hdr["race_id"], hdr["venue"], hdr["surface"], hdr["dist"],
                                                               "(%s)" % hdr["course"] if hdr["course"] else "", nh))
    print("")
    for w in warns:
        print("警告: " + w)
        print("")
    q = hdr.get("quality") or {}
    print("品質: 取消・除外=%s頭（欠けた馬番=%s）／ 近走欄の最新日=%s（レース日より前=%s）／ 1角位置の取れない馬=%d頭" %
          (q.get("scratched"), ",".join(map(str, q.get("missing_nums", []))) or "なし", q.get("latest_run"), "はい" if q.get("date_ok") else "いいえ", q.get("fm_missing", 0)))
    print("")
    pk = "複勝（2着以内）" if nh <= 7 else "複勝（3着以内）"
    print("**馬別**（予測した支持率 q＝出走表だけから予測した当日の人気。勝率・%sの確率は着順に合わせた確率。期待値は見積もった払戻から）" % pk)
    print("")
    order = sorted(range(nh), key=lambda i: (-s[i], i))
    rows = []
    for r_, i in enumerate(order, 1):
        u = str(nums[i])
        a, b = tk[("単勝", u)], tk[("複勝", u)]
        rows.append([r_, nums[i], horses[i]["name"], horses[i]["jockey"], "%.1f%%" % (100 * d["q"][i]), "%.1f%%" % (100 * a[2]), "%.1f%%" % (100 * b[2]),
                     "%.2f" % a[5], "%.2f" % b[5], "%.1f%%" % (100 * d["p48"][i])])
    print(tbl(["予測順位", "馬番", "馬名", "騎手", "予測した支持率", "勝率", pk + "の確率", "単勝の期待値", "複勝の期待値", "参考: v4.8 の勝率"], rows))
    print("")
    print("予測1位の馬の支持率 q1=%.1f%%（案A・案Cの境目 %.1f%%）／ 券種ごとの最大の期待値: %s" %
          (100 * d["q1"], 100 * PAR["plans"]["q1_cut"], " ／ ".join("%s %.2f" % (t, rec["best"][t]) for t in M.TYPES)))
    print("")
    print("**仮想購入（各100円。実際の馬券は買わない）**")
    print("")
    prow = []
    desc = {"案A": "予測1位の単勝（q1が境目以上）", "案B": "複勝の期待値%.1f以上" % M.EV_B, "案C": "予測1位の複勝（q1が境目以上）"}
    for k, _, _ in M.PLANS:
        v = pl[k]
        prow.append([k, desc[k], " ／ ".join("%s %s（確率%.1f%%・期待値%.2f）" % (x[0], x[1], 100 * x[2], x[5]) for x in v) if v else "見送り", len(v)])
    print(tbl(["案", "買い方", "買い目", "点数"], prow))
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
        return predict(a[1], a[2] if len(a) >= 3 else None)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
