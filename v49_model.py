# -*- coding: utf-8 -*-
"""v49_model.py  v4.9 の特徴量と確率の計算（分析計算v4.9・考察計算v4.9・係数作成v4.9 で共通に使う。標準のPythonだけで書く）。
係数は v49_params.json（係数作成v4.9.py が607レースから作り、固定する）。
  予想の本体（市場の予測モデル）: スコア s = X·w。X は v4.8 の市場の予測モデルの46項目（v48_model.market_matrix。騎手・調教師の表は v4.9 で作り直したもの）
               ＋ 新しい11項目（年齢・牝・前走の上がり相対順位・近走の上がり相対順位の平均・前走の1角相対位置・距離の変化・走った数〔レース内で標準化〕、
               父・母父・馬主・生産者の「人気の集まりやすさ」の表〔レース内で標準化〕）。
               X は小数6桁に丸め、s は丸めた X から計算して小数9桁に丸める（考察計算が同じ値を再計算して照合できるようにするため）。
  予測した支持率 q = softmax(s)。
  着順の確率: 1着は softmax(a1·s)、2着・3着は残りの馬で softmax(a2·s)（a1・a2 は着順に当てはめた値）。
  市場の確率（払戻の見積もり用）: 1・2・3着とも softmax(s)。
  払戻の見積もり（単勝・複勝・ワイド・馬連）: log(払戻/100) = α + β·ln(市場の確率) + γ·ln(着順の確率) ＋ s²/2。期待値 = 着順の確率 × 払戻/100。
  複勝は、出走7頭以下なら2着以内、8頭以上なら3着以内。
  買い方: 案A＝予測1位の馬の単勝（q1が境目以上のレース）、案B＝複勝の期待値0.9以上（全頭）、案C＝予測1位の馬の複勝（q1が境目以上のレース）。"""
import math, re, json, os, hashlib, itertools, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = "v4.9"
TYPES = ["単勝", "複勝", "ワイド", "馬連"]
NEW_NUM = ["age", "female", "l3r_last", "l3r_avg", "c1_last", "ddist", "n_runs"]
NEW_TE = ["sire", "bms", "owner", "breeder"]
TE_KEYS = ["j", "t"] + NEW_TE
EV_B = 0.9
PLANS = [("案A", "単勝", "q1"), ("案B", "複勝", "ev"), ("案C", "複勝", "q1")]


def _load_v48():
    for n in ("v48_model.py",):
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location("v48_model", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise SystemExit("【停止】同じフォルダに v48_model.py がありません")


M48 = _load_v48()


def code_sha(path=None):
    p = path or os.path.abspath(__file__)
    return hashlib.sha256(re.sub(r"\s+", "", open(p, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def load_params(path=None):
    p = path or os.path.join(HERE, "v49_params.json")
    d = json.load(open(p, encoding="utf-8"))
    d["_sha"] = code_sha(p)
    return d


def softmax(us):
    m = max(us)
    ex = [math.exp(u - m) for u in us]
    t = sum(ex)
    return [e / t for e in ex]


# ---------------- 新しい11項目（候補抽出の1頭から） ----------------
def _rel(a, n):
    return (a - 1) / (n - 1) if a and n and n > 1 else None


def new_extra(h, feat):
    rr = M48.real_runs(h)
    last = rr[0] if rr else None
    e = {}
    e["age"] = h["年齢"]
    e["female"] = 1.0 if h["性"] == "牝" else 0.0
    e["l3r_last"] = _rel(last["上がり順位"], last["頭数"]) if last else None
    v = [_rel(r["上がり順位"], r["頭数"]) for r in rr]
    v = [x for x in v if x is not None]
    e["l3r_avg"] = sum(v) / len(v) if v else None
    e["c1_last"] = _rel(last["通過順"][0], last["頭数"]) if last and last["通過順"] else None
    e["ddist"] = (feat["dist"] - last["距離"]) / 1000 if last and last["距離"] else None
    e["n_runs"] = len(rr)
    ow = (h["記録のみ"].get("馬主_生産") or "").split(" ")
    e["sire"], e["bms"] = h["父"], h["母父"]
    e["owner"] = ow[0] if ow and ow[0] else None
    e["breeder"] = ow[1] if len(ow) > 1 else None
    return e


def race_inputs(feat, C):
    """FEAT（候補抽出の出力）と7項目の寄与 C から、v4.8 の候補15列・市場の項目と、新しい項目を作る。"""
    vals, CAND, EX = M48.race_inputs(feat, C)
    NX = [new_extra(h, feat) for h in feat["horses"]]
    return CAND, EX, NX


def design_rows(P, C, CAND, EX, NX):
    """予想の本体の入力（馬ごとの行。57列）。P は v49_params（te: 6つの表）。小数6桁に丸める。"""
    te = P["te"]
    X = M48.market_matrix(C, CAND, EX, te["j"], te["t"])
    cols = [M48.zfill([e[k] for e in NX]) for k in NEW_NUM]
    cols += [M48.zfill([te[k].get(e[k], 0.5) if e[k] else 0.5 for e in NX]) for k in NEW_TE]
    return [[round(v, 6) + 0.0 for v in (list(X[i]) + [c[i] for c in cols])] for i in range(len(X))]


def scores(P, X):
    return [round(M48.dot(P["w"], x), 9) + 0.0 for x in X]


# ---------------- 着順の確率 ----------------
def stage(s, a1, a2):
    p1 = softmax([a1 * v for v in s])
    m = max(s)
    w = [math.exp(a2 * (v - m)) for v in s]
    return p1, w


def trio_prob(p1, w, idxs):
    """実際の3頭の組の確率（順番なし）。1着は p1、2・3着は残りの馬の w で決まる。"""
    W = sum(w)
    t = 0.0
    for x, y, z in itertools.permutations(idxs):
        t += p1[x] * w[y] / (W - w[x]) * w[z] / (W - w[x] - w[y])
    return t


def outcomes(p1, w):
    """券種ごとの「位置のタプル → 確率」。単勝・複勝（7頭以下は2着以内）・ワイド・馬連。"""
    n = len(p1)
    W = sum(w)
    o = {t: {} for t in TYPES}
    top2 = [0.0] * n
    top3 = [0.0] * n
    for i in range(n):
        o["単勝"][(i,)] = p1[i]
        d1 = W - w[i]
        for j in range(n):
            if j == i:
                continue
            pij = p1[i] * w[j] / d1
            kk = (i, j) if i < j else (j, i)
            o["馬連"][kk] = o["馬連"].get(kk, 0.0) + pij
            top2[i] += pij
            top2[j] += pij
            d2 = d1 - w[j]
            for k in range(n):
                if k == i or k == j:
                    continue
                v = pij * w[k] / d2
                top3[i] += v
                top3[j] += v
                top3[k] += v
                for a_, b_ in ((i, j), (i, k), (j, k)):
                    kk = (a_, b_) if a_ < b_ else (b_, a_)
                    o["ワイド"][kk] = o["ワイド"].get(kk, 0.0) + v
    pl = top2 if n <= 7 else top3
    for i in range(n):
        o["複勝"][(i,)] = pl[i]
    return o


def key_str(key, nums):
    return "-".join(str(u) for u in sorted(nums[i] for i in key))


def tickets(P, nums, s):
    """4券種の全買い目。戻り値: [(券種, 組番, 着順の確率, 市場の確率, 見積もった払戻〔円〕, 期待値)]。"""
    a1, a2 = P["order"]["a1"], P["order"]["a2"]
    Oc = outcomes(*stage(s, a1, a2))
    Om = outcomes(*stage(s, 1.0, 1.0))
    out = []
    for t in TYPES:
        al, be, ga, s2 = P["pay"][t]
        for k, pc in Oc[t].items():
            qm = Om[t][k]
            epay = math.exp(al + be * math.log(qm) + ga * math.log(pc) + s2 / 2.0) * 100.0
            out.append((t, key_str(k, nums), pc, qm, epay, pc * epay / 100.0))
    return out


def q1_of(s):
    q = softmax(s)
    h = max(range(len(q)), key=lambda i: (q[i], -i))
    return h, q[h]


def plans(P, nums, s, ts):
    """案A・案B・案C の買い目。案B は期待値の高い順（小数12桁に丸めて比べ、同じなら組番の順）。"""
    h, q1 = q1_of(s)
    cut = P["plans"]["q1_cut"]
    tk = {(t, k): x for x in ts for t, k in [(x[0], x[1])]}
    out = {}
    out["案A"] = [tk[("単勝", str(nums[h]))]] if q1 >= cut else []
    b = [x for x in ts if x[0] == "複勝" and x[5] >= EV_B]
    b.sort(key=lambda x: (-round(x[5], 12), int(x[1])))
    out["案B"] = b
    out["案C"] = [tk[("複勝", str(nums[h]))]] if q1 >= cut else []
    return out, h, q1


# ---------------- 出走表の読み取り（分析計算v4.7.py の関数をそのまま呼ぶ） ----------------
def core47(E47, path, expect=None):
    """E47＝分析計算v4.7.py のモジュール。分析計算v4.7 の predict と同じ順で、読み取り・確認・モード判定を行い、通常モードでは7項目の寄与を返す。
    戻り値: (状態, 内容)。状態は "error"・"stop"・"debut"・"mixed"・"normal"。"""
    E47.load_settings()
    warns = []
    soup, raw = E47.make_soup(path)
    hdr = E47.parse_header(soup, raw, warns)
    if not hdr["venue"] or not hdr["dist"] or not hdr["race_id"]:
        return "error", "エラー: 出走表HTMLから会場・距離・レースIDを読み取れません（%s）。文字化けや別ページの可能性があります。HTMLを確認してください。" % " / ".join(warns)
    if expect:
        m = re.match(r"\s*(浦和|船橋|大井|川崎)\s*(\d{1,2})\s*R\s*$", expect)
        rno = int(hdr["race_id"][-2:]) if hdr["race_id"] else None
        if not m:
            return "error", "エラー: 指定は『浦和12R』の形式で渡してください: %s" % expect
        if hdr["venue"] != m.group(1) or rno != int(m.group(2)):
            return "error", "エラー: 指定(%s)とHTML(%s %sR, id=%s)が一致しません。HTMLを確認してください。" % (expect, hdr["venue"], rno, hdr["race_id"])
    horses = E47.parse_horses(soup, hdr, warns)
    if len(horses) < 3:
        return "error", "エラー: 馬を3頭以上抽出できません。HTMLを確認してください。"
    if hdr["heads"] and hdr["heads"] != len(horses):
        warns.append("頭数表記%d頭と抽出頭数%d頭が不一致" % (hdr["heads"], len(horses)))
    nh = len(horses)
    _dates = [r_["date"] for h_ in horses for r_ in h_["runs"] if r_ and r_.get("date")]
    _rdate = (hdr.get("race_id") or "")[:8]
    _latest = max(_dates) if _dates else None
    _ok = (_latest is None) or (not re.fullmatch(r"\d{8}", _rdate)) or (_latest < _rdate)
    _nums = sorted(h_["num"] for h_ in horses)
    hdr["quality"] = {"scratched": len(hdr.get("scratched_cells", [])), "scratched_cells": hdr.get("scratched_cells", []),
                      "missing_nums": [k_ for k_ in range(1, (_nums[-1] if _nums else 0) + 1) if k_ not in _nums],
                      "latest_run": _latest, "race_date": _rdate, "date_ok": bool(_ok)}
    if not _ok:
        return "stop", "【停止】近走欄の最新日(%s)がレース日(%s)以降です。結果が混入したHTMLの疑いがあります。レース前のHTMLで実行してください。" % (_latest, _rdate)
    n_debut = sum(1 for h in horses if h.get("is_debut"))
    if n_debut == nh:
        return "debut", (hdr, horses, warns)
    if n_debut > 0:
        return "mixed", (hdr, horses, n_debut)
    feats, styles, wobbles, nprobs, fms, metas, srcs, frs = E47.build_features(horses, hdr, E47.SETTINGS["recency"])
    q = hdr["quality"]
    q["fm_missing"] = sum(1 for f_ in fms if f_ is None)
    _ks = [k_ for k_ in feats if k_ != "wt"]
    q["feat_missing"] = round(sum(1 for k_ in _ks for v_ in feats[k_] if v_ is None) / float(nh * len(_ks)), 4)
    q["heads_hdr"] = hdr.get("heads")
    q["heads_parsed"] = nh
    for h in horses:
        for w in h["warn"]:
            if "馬体重" not in w:
                warns.append("馬番%d: %s" % (h["num"], w))
    zf = {k: E47.z_scores(v) for k, v in feats.items()}
    P, scale = E47.SETTINGS["points"], E47.SETTINGS["scale"]
    C = [[round(P[k] / 100.0 * scale * zf[k][i], 3) + 0.0 for k in E47.HK_NORMAL][:7] for i in range(nh)]
    return "normal", (hdr, horses, warns, C)


