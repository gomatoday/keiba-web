# -*- coding: utf-8 -*-
"""v48_model.py  v4.8 の特徴量と確率の計算（分析計算v4.8・考察計算v4.8・係数作成v4.8 で共通に使う。標準のPythonだけで書く）。
係数は v48_params.json（係数作成v4.8.py が304レースの設計用データから作り、固定する）。
  予想のモデル: u = Σ θ_k·c_k（v4.7 の7項目の寄与。REC の hs.c の先頭7つ）＋ ⑤ 相対馬番×場×距離区分（8）＋ ⑥ 近走の平均相対人気・前走の人気と着順のずれ（2）。
               勝率 = softmax(u)。2・3着はヘンリー型（指数 g）。逃げ補正はない。
  市場の予測モデル: スコア s = X·w（F6。7項目の寄与・候補15列・人気と着順の履歴・騎手と調教師など。履歴系はレース内で標準化）。
               支持率 = softmax(s/τ)。2・3着はヘンリー型（指数 g_m）。
  組み合わせた着順モデル: 勝率 ∝ 自分^a × 市場^b、2・3着はヘンリー型（指数 g_c）。
  券種ごとの払戻の見積もり: log(払戻/100) = α + β·log(市場の確率) + γ·log(組み合わせた確率) ＋ s²/2。期待値 = 組み合わせた確率 × 払戻/100。"""
import math, re, json, os, itertools, hashlib
from datetime import date

NANKAN = ("浦和", "船橋", "大井", "川崎")
VENUES = ["大井", "川崎", "浦和", "船橋"]
NOT_RUN = ("取消", "除外", "能試", "初出走欄", "取止")      # 「実際に走った」に数えない欄
TYPES = ["単勝", "複勝", "馬連", "ワイド", "馬単", "三連複", "三連単"]
ORDERED = ("単勝", "複勝", "馬単", "三連単")                  # 組番の並びに意味がある券種（単勝・複勝は1頭）
PLANS = [  # (名前, 期待値のしきい値, 1レースの最大点数〔Noneは制限なし〕, 使う券種)
    ("案1", 0.95, 3, TYPES),
    ("案2", 1.00, 3, TYPES),
    ("案3", 0.90, None, TYPES),
    ("案4", 1.00, None, ["三連複"]),
]
HERE = os.path.dirname(os.path.abspath(__file__))


def code_sha(path=None):
    p = path or os.path.abspath(__file__)
    return hashlib.sha256(re.sub(r"\s+", "", open(p, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def load_params(path=None):
    p = path or os.path.join(HERE, "v48_params.json")
    d = json.load(open(p, encoding="utf-8"))
    d["_sha"] = code_sha(p)
    return d


# ---------------- 確率 ----------------
def softmax(us):
    m = max(us)
    ex = [math.exp(u - m) for u in us]
    t = sum(ex)
    return [e / t for e in ex]


def ordered_table(p, g):
    """順番つきの1-2-3着の確率（ヘンリー型）。キー=(i,j,k)（出走馬の並びの位置）。"""
    n = len(p)
    w = [x ** g for x in p]
    W = sum(w)
    T = {}
    for i in range(n):
        for j in range(n):
            if j == i:
                continue
            d1 = W - w[i]
            for k in range(n):
                if k == i or k == j:
                    continue
                T[(i, j, k)] = p[i] * w[j] / d1 * w[k] / (d1 - w[j])
    return T


def trio_prob(p, g, idxs):
    """実際の3頭の組の確率（順番なし）。"""
    w = [x ** g for x in p]
    W = sum(w)
    t = 0.0
    for x, y, z in itertools.permutations(idxs):
        t += p[x] * w[y] / (W - w[x]) * w[z] / (W - w[x] - w[y])
    return t


def outcomes(T, n):
    """券種ごとの「買い目 → 確率」。キーは出走馬の並びの位置のタプル（順番なしの券種は小さい順）。複勝は7頭以下なら2着まで。"""
    o = {t: {} for t in TYPES}
    place = 2 if n <= 7 else 3
    for (i, j, k), v in T.items():
        o["三連単"][(i, j, k)] = v
        kk = tuple(sorted((i, j, k)))
        o["三連複"][kk] = o["三連複"].get(kk, 0.0) + v
        o["馬単"][(i, j)] = o["馬単"].get((i, j), 0.0) + v
        kk = (i, j) if i < j else (j, i)
        o["馬連"][kk] = o["馬連"].get(kk, 0.0) + v
        o["単勝"][(i,)] = o["単勝"].get((i,), 0.0) + v
        for a_, b_ in ((i, j), (i, k), (j, k)):
            kk = (a_, b_) if a_ < b_ else (b_, a_)
            o["ワイド"][kk] = o["ワイド"].get(kk, 0.0) + v
        for h in (i, j, k)[:place]:
            o["複勝"][(h,)] = o["複勝"].get((h,), 0.0) + v
    return o


def key_str(t, key, nums):
    """位置のタプル → 組番の文字列（馬番。順番なしの券種は馬番の小さい順）。"""
    us = [nums[i] for i in key]
    if t not in ORDERED:
        us = sorted(us)
    return "-".join(str(u) for u in us)


# ---------------- 候補の値（FEAT の1頭から） ----------------
def real_runs(h):
    return [r for r in h["過去走"] if r and r["異常"] not in NOT_RUN]


def short_dist(venue, dist):
    return dist <= (1300 if venue == "浦和" else 1200)


def horse_vals(h, race_date, maxnum):
    rr = real_runs(h)
    last = rr[0] if rr else None
    v = {}
    days = None
    if last and last["日付"]:
        a = date(int(race_date[:4]), int(race_date[4:6]), int(race_date[6:]))
        b = date(int(last["日付"][:4]), int(last["日付"][4:6]), int(last["日付"][6:]))
        days = (a - b).days
    v["days"] = days
    v["i_short"] = 1.0 if days is not None and days <= 20 else 0.0
    v["i_long"] = 1.0 if days is not None and days >= 60 else 0.0
    v["change"] = 1.0 if (last and last["騎手"] and h["騎手"] and last["騎手"] != h["騎手"]) else 0.0
    v["dkg"] = (h["負担重量"] - last["斤量"]) if (last and last["斤量"] is not None and h["負担重量"] is not None) else 0.0
    v["transfer"] = 1.0 if (rr and all(r["場"] not in NANKAN for r in rr)) else 0.0
    v["x"] = (h["馬番"] - 1) / (maxnum - 1) if maxnum > 1 else 0.0
    rel = [r["人気"] / r["頭数"] for r in rr if r["人気"] and r["頭数"]]
    v["pop_avg"] = (sum(rel) / len(rel) - 0.5) if rel else 0.0
    v["pop_gap"] = ((last["着順"] - last["人気"]) / last["頭数"]) if (last and last["着順"] and last["人気"] and last["頭数"]) else 0.0
    return v


def cand_cols(v, venue, short):
    """候補15列（①2・②1・③1・④1・⑤8・⑥2）。市場の予測モデルが使う。予想のモデルは⑤⑥だけ（後ろの10列）。"""
    c5 = [v["x"] if (venue == vn and short == sd) else 0.0 for vn in VENUES for sd in (True, False)]
    return [v["i_short"], v["i_long"], v["change"], v["dkg"], v["transfer"]] + c5 + [v["pop_avg"], v["pop_gap"]]


OWN_CAND = slice(5, 15)    # ⑤8＋⑥2


# ---------------- 市場の予測モデルの項目 ----------------
def _pct(s, k=0):
    v = re.findall(r"([\d.]+)%", s or "")
    return float(v[k]) / 100 if len(v) > k else None


def market_extra(h, venue):
    rr = real_runs(h)
    last = rr[0] if rr else None
    prev = rr[1] if len(rr) > 1 else None

    def relp(r):
        return (r["人気"] - 1) / (r["頭数"] - 1) if r and r["人気"] and r["頭数"] and r["頭数"] > 1 else None

    def relf(r):
        return (r["着順"] - 1) / (r["頭数"] - 1) if r and r["着順"] and r["頭数"] and r["頭数"] > 1 else None
    e = {}
    e["pop_last"] = relp(last)
    e["pop_prev"] = relp(prev)
    e["lnpop_last"] = math.log(last["人気"]) if last and last["人気"] else None
    pr = [relp(r) for r in rr if relp(r) is not None]
    e["pop_min"] = min(pr) if pr else None
    e["fin_last"] = relf(last)
    e["win_last"] = 1.0 if last and last["着順"] == 1 else 0.0
    e["top3_last"] = 1.0 if last and last["着順"] and last["着順"] <= 3 else 0.0
    fr = [relf(r) for r in rr if relf(r) is not None]
    e["fin_best"] = min(fr) if fr else None
    e["mg_last"] = min(last["着差"], 3.0) if last and last["着差"] is not None and last["着順"] != 1 else (0.0 if last and last["着順"] == 1 else None)
    e["jk_course"] = _pct(h["記録のみ"]["騎手コース相性"])
    e["jk_ret_win"] = _pct(h["記録のみ"]["回収率_騎手"], 0)
    e["hs_ret_win"] = _pct(h["記録のみ"]["回収率_競走馬"], 0)
    e["kg"] = h["負担重量"]
    e["gen"] = 1.0 if h["減量記号"] else 0.0
    e["same_venue"] = 1.0 if last and last["場"] == venue else 0.0
    pl, fp = relp(last), relf(prev)
    e["finP"] = fp
    e["winP"] = 1.0 if prev and prev["着順"] == 1 else 0.0
    e["popL_x_finP"] = (pl - 0.5) * (fp - 0.5) if pl is not None and fp is not None else None
    e["popL_x_winP"] = (pl - 0.5) * (1.0 if prev and prev["着順"] == 1 else 0.0) if pl is not None else None
    e["popL_x_top3P"] = (pl - 0.5) * (1.0 if prev and prev["着順"] and prev["着順"] <= 3 else 0.0) if pl is not None else None
    ws = [(0.5 ** k, relf(r)) for k, r in enumerate(rr) if relf(r) is not None]
    e["fin_decay"] = sum(w * v for w, v in ws) / sum(w for w, _ in ws) if ws else None
    e["popL_x_finL"] = (pl - 0.5) * (relf(last) - 0.5) if pl is not None and relf(last) is not None else None
    e["jid"], e["tid"] = h["騎手ID"], h["調教師ID"]
    return e


MARKET_FEATS = ["pop_last", "pop_prev", "lnpop_last", "pop_min", "fin_last", "win_last", "top3_last", "fin_best", "mg_last",
                "jk_course", "jk_ret_win", "hs_ret_win", "TE_j", "TE_t", "kg", "gen", "same_venue",
                "finP", "winP", "popL_x_finP", "popL_x_winP", "popL_x_top3P", "fin_decay", "popL_x_finL"]


def zfill(vals):
    """レース内で、欠けを平均で埋めて標準化。"""
    xs = [v for v in vals if v is not None]
    if not xs:
        return [0.0] * len(vals)
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [0.0 if v is None else (v - mu) / sd for v in vals]


def market_matrix(C, CAND, EX, tej, tet):
    """市場の予測モデルの入力（馬ごとの行）。C=7項目の寄与、CAND=候補15列、EX=market_extra の辞書、tej/tet=騎手・調教師の表。"""
    cols = []
    for f_ in MARKET_FEATS:
        if f_ == "TE_j":
            vals = [tej.get(e["jid"], 0.5) for e in EX]
        elif f_ == "TE_t":
            vals = [tet.get(e["tid"], 0.5) for e in EX]
        else:
            vals = [e[f_] for e in EX]
        cols.append(zfill(vals))
    return [list(C[i]) + list(CAND[i]) + [col[i] for col in cols] for i in range(len(C))]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


# ---------------- 1レースの計算 ----------------
def race_inputs(feat, C):
    """FEAT（候補抽出の出力）と7項目の寄与 C（出走馬の並び）から、候補15列と市場の項目を作る。"""
    nums = feat["nums"]
    maxnum = max(nums)
    short = short_dist(feat["venue"], feat["dist"])
    vals = [horse_vals(h, feat["date"], maxnum) for h in feat["horses"]]
    CAND = [cand_cols(v, feat["venue"], short) for v in vals]
    EX = [market_extra(h, feat["venue"]) for h in feat["horses"]]
    return vals, CAND, EX


def model_probs(P, C, CAND, EX, pos_zero=False):
    """予想のモデルの勝率。pos_zero=True は位置変化（7項目の3番目）の係数を0にしたもの（副評価(a)）。"""
    th = list(P["own"]["theta"])
    if pos_zero:
        th[2] = 0.0
    phi = P["own"]["phi"]
    u = [dot(th, C[i]) + dot(phi, CAND[i][OWN_CAND]) for i in range(len(C))]
    return u, softmax(u)


def market_probs(P, C, CAND, EX):
    X = market_matrix(C, CAND, EX, P["market"]["te_j"], P["market"]["te_t"])
    s = [dot(P["market"]["w"], x) for x in X]
    tau = P["market"]["tau"]
    return s, softmax([v / tau for v in s])


def combined_probs(P, p, q):
    a, b = P["comb"]["a"], P["comb"]["b"]
    return softmax([a * math.log(x) + b * math.log(y) for x, y in zip(p, q)])


def tickets(P, nums, c, q):
    """全券種の買い目と期待値。戻り値: [(券種, 組番, 組み合わせた確率, 市場の確率, 見積もった払戻〔円〕, 期待値)]。"""
    n = len(nums)
    Oc = outcomes(ordered_table(c, P["comb"]["g"]), n)
    Om = outcomes(ordered_table(q, P["market"]["g"]), n)
    out = []
    for t in TYPES:
        al, be, ga, s2 = P["pay"][t]
        for k, pc in Oc[t].items():
            qm = Om[t][k]
            epay = math.exp(al + be * math.log(qm) + ga * math.log(pc) + s2 / 2.0) * 100.0
            out.append((t, key_str(t, k, nums), pc, qm, epay, pc * epay / 100.0))
    return out


def plan_select(ts, plan):
    """案ごとの買い目（期待値の高い順。同じ期待値は券種の順・組番の順）。"""
    name, th, cap, types = plan
    sel = [x for x in ts if x[0] in types and x[5] >= th]
    sel.sort(key=lambda x: (-round(x[5], 12), TYPES.index(x[0]), x[1]))
    return sel[:cap] if cap else sel
