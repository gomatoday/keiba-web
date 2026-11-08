# -*- coding: utf-8 -*-
"""
考察計算v4.7.py  結果の考察と、複数レースの集計（v4.7の判定：新しい通常モード300レースの対数スコアの差）
v4.7: 分析計算v4.7.pyに対応。
 (1) 逃げ補正は一律+0.9（NIGE_BOOST）。勝率=softmax(能力計+逃げ補正)。β=1・g=0.8固定。
 (2) 切り捨て（配分表・展開区分は廃止）: 補正後の能力計u（小数3桁）の順位が10位以下、または補正後の3着内確率（全頭の確率から計算）が10%以下の馬を除く。
     残った馬の3頭の組を、全頭の三連複確率（選定馬で作り直さない）の高い順に並べる（同確率は馬番昇順の辞書順）。連続上位1〜20位を仮想購入（各100円）。残った組が20通り以下なら全買い。
 (3) 比較用の記録ref45: 補正なし(u=能力計)で同じ手順。主評価の比較相手。ref40・refw・ref43は廃止（配分表を使うため）。
 (4) 主評価: Δ_r = ln P_v47(実際の組) − ln P_ref45(実際の組)。P=全頭の三連複確率（選定・購入と無関係）。同着で実際の組が複数あるときは各組のPの合計。
     判定は、対象の通常モードのレースが300以上に達した時点で、揃っている全レースを使って1回だけ（300ちょうどには切らない）。Δの平均の対ブートストラップ（レース単位・10,000回・乱数シード固定）の95%区間の下限が0を超えれば「補正に効果あり」。
     300に達するまでΔ・回収率は計算も表示もしない（200レース時点の中間報告は品質の項目だけ）。
 (5) 副評価（採否に使わない）: 仮想回収率（全買いを除く）の、v4.7とref45の対の差の95%区間。5.3の併記（逃げ馬ありのレースのΔ、Δ=0のレース数）。
 (6) 検証に使わないレース: v4.5のLEDGERの通常42レースと新馬3レース、v4.6の検討に使った47レース（EXCLUDE_IDS）。
使い方
  1) python 考察計算v4.7.py kosatsu   分析出力.txt "1-2-3/500円"      （1レースの考察。末尾にLEDGER行。同着は "1-2-3/500円,1-2-4/700円" のようにカンマで並べる）
  2) python 考察計算v4.7.py aggregate <LEDGER行を集めたファイル>      （先頭に "STUDY {"start":"20261107"}" の行を置くと、その日以降のレースだけを対象にする。"STOP ..." の行は停止の件数として数える）
"""
import sys, re, json, math, os, itertools, hashlib, random

RULE_VERSION = "v4.7"
POINTS = [5, 10, 15, 20]
STYLES = ["逃げ", "先行", "差し", "追込"]
ITEM_JA = {"ord": "着順", "margin": "着差", "pos": "位置", "l3f": "末脚", "apt": "適性", "time": "時計", "jky": "騎手", "wt": "体重",
           "trial": "能試", "debut": "初出走", "jkcourse": "騎手コース", "sire": "種牡馬", "jktr": "騎手厩舎"}
FRONT = ("逃げ", "先行")
BAND_JA = {"1-3": "1-3位", "4-6": "4-6位", "7-": "7位以下"}
# v4.7の切り捨て設定（分析計算v4.7.pyのSETTINGS["p1"]と同じ。REC行のpar.p1と照合する）
P1_CFG = {"cut_rank": 9, "cut_p3": 0.10}
RECENCY = [0.2, 0.2, 0.2, 0.2, 0.2]
NIGE_BOOST = 0.9         # v4.7: 脚質「逃げ」の能力計に加える値（一律。分析計算v4.7.pyのSETTINGS["nige_boost"]と同じ）
NIGE_NP_MIN = 0.5        # 逃げ確率がこれ以上の馬を脚質「逃げ」とする（分析計算v4.7.pyのSETTINGS["nige_np_min"]と同じ）
TOPN = 20
JUDGE_N = 300            # 判定に使うレース数（判定を行う最小のレース数。判定は、300以上に達した時点で揃っている対象レース全部で1回だけ行う。途中経過は出さない）
BOOT_B = 10000           # ブートストラップ回数
BOOT_SEED = 20261106     # 乱数シード（固定）
BUY_CFG = {"rank_ranges": [[1, 20]], "unit_yen": 100, "max_points": 20}
GRID_G = [0.6, 0.7, 0.8, 0.9, 1.0]   # 参考表示（gの感度）。判定には使わない
# 検証に使わないレース（v4.7の設計・補正値の決定に使ったレース）。分析計算v4.6の回帰テストに使ったHTML47レースのレースID
EXCLUDE_IDS = set("""
2026060119030101 2026060119030102 2026060119030103 2026060119030104
2026060119030105 2026060119030106 2026060119030107 2026060119030108
2026060119030109 2026060119030110 2026060119030111 2026060119030112
2026060820040101 2026060820040102 2026060820040103 2026060820040104
2026060820040105 2026060820040106 2026060820040107 2026060820040108
2026060820040109 2026060820040110 2026060820040111 2026061521030101
2026061521030102 2026061521030103 2026061521030104 2026061521030105
2026061521030106 2026061521030107 2026061521030108 2026061521030109
2026061521030110 2026061521030111 2026061521030112 2026062218030101
2026062218030102 2026062218030103 2026062218030104 2026062218030105
2026062218030106 2026062218030107 2026062218030108 2026062218030109
2026062218030110 2026062218030111 2026062218030112
""".split())


def code_sha():
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.abspath(__file__), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]  # 空白・改行の違いは無視


def trio_probs(p, g=1.0):
    """ヘンリー型。1着の段は p（合計1に正規化）、2・3着の段は w=p^g を使い、残りのwの和で割る。g=1.0はHarville式。分析計算v4.7.pyと同じ式。"""
    n = len(p)
    sp = sum(p)
    p = [x / sp for x in p]
    w = [x ** g for x in p]
    W = sum(w)
    res = {}
    for a, b, c in itertools.combinations(range(n), 3):
        tot = 0.0
        for x, y, z in itertools.permutations((a, b, c)):
            d1 = W - w[x]
            d2 = W - w[x] - w[y]
            if d1 <= 0 or d2 <= 0:
                continue
            tot += p[x] * w[y] / d1 * w[z] / d2
        res[(a, b, c)] = tot
    return res


def trio_actual(p, idxs, g):
    """実際の3頭の組の確率（ヘンリー型）。idxs=pリスト内の位置3つ。trio_probsと同じ式。"""
    sp = sum(p)
    p = [x / sp for x in p]
    w = [x ** g for x in p]
    W = sum(w)
    tot = 0.0
    for x, y, z in itertools.permutations(idxs):
        d1 = W - w[x]
        d2 = W - w[x] - w[y]
        if d1 <= 0 or d2 <= 0:
            continue
        tot += p[x] * w[y] / d1 * w[z] / d2
    return tot


def softmax(us):
    m = max(us)
    ex = [math.exp(u - m) for u in us]
    t = sum(ex)
    return [e / t for e in ex]


def p3_list(pw, g):
    """全頭モデルでの各馬の3着内確率（pwの並び順）。分析計算v4.7.pyのp3_of(trio_probs(pw6, g))と同じ値。"""
    tp = trio_probs(pw, g)
    out = [0.0] * len(pw)
    for idx, pr in tp.items():
        for j in idx:
            out[j] += pr
    return out


def load_rec(arg):
    txt = open(arg, encoding="utf-8").read() if os.path.exists(arg) else arg
    txt = txt.strip()
    m = re.search(r"REC (\{.*\})", txt, re.S)
    if m:
        txt = m.group(1)
    return json.loads(txt)


def stop(msg):
    print("【停止】" + msg)
    return 1


def in_buy(rank):
    """v4.7: 実購入帯（連続上位1〜20位）"""
    return any(a <= rank <= b for a, b in BUY_CFG["rank_ranges"])


def _finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def _prob_vector(p, n):
    if not isinstance(p, list) or len(p) != n or any(not _finite(v) or v <= 0 for v in p) or abs(sum(p) - 1) > n * 0.00000051:
        raise ValueError("勝率ベクトルの長さ・正値・合計不一致")


def _marks_check(ents, combos):
    if not isinstance(ents, list) or not ents:
        raise ValueError("購入マークシート欠落")
    made = set()
    for e in ents:
        for col in ("a", "b", "c"):
            xs = e[col]
            if not isinstance(xs, list) or not xs or any(type(x) is not int for x in xs) or len(set(xs)) != len(xs):
                raise ValueError("マーク列の空欄・重複・型不正")
        one = {"-".join(map(str, sorted(t))) for t in itertools.product(e["a"], e["b"], e["c"]) if len(set(t)) == 3}
        if not one or type(e.get("n")) is not int or e["n"] != len(one) or made & one:
            raise ValueError("マークシートの点数不一致・口間重複")
        made |= one
    if made != set(combos):
        raise ValueError("マークシートの組に過不足")


def _check_rounded_softmax(vector, us, error=0.000500001):
    """vector（6桁に丸めた勝率）が、softmax(us)の丸め区間（usは各±errorの区間）に入るかを確認する。"""
    n = len(us)
    m = max(us)
    ex = [math.exp(u - m) for u in us]
    for j, v in enumerate(vector):
        rest = sum(ex[k] for k in range(n) if k != j)
        lo = ex[j] / (ex[j] + rest * math.exp(2 * error))
        hi = ex[j] / (ex[j] + rest * math.exp(-2 * error))
        if not lo - 0.00000051 <= v <= hi + 0.00000051:
            return False
    return True


def _check_nige_style(names, nps, fms):
    """v4.7: 脚質「逃げ」⇔ 逃げ確率np≥NIGE_NP_MIN（1角位置が取れた馬＝fmがあるとき）。取れない馬は脚質不明。"""
    for st, np_, fm in zip(names, nps, fms):
        if fm is None:
            if st != "不明":
                raise ValueError("1角位置のない馬の脚質が不明でない")
            continue
        if not _finite(np_) or (st == "逃げ") != (np_ >= NIGE_NP_MIN):
            raise ValueError("脚質『逃げ』と逃げ確率npの不整合")


def select_v47(nums, u3, p3, cfg=None):
    """v4.7の切り捨て（配分表・展開区分は廃止）。nums=馬番、u3=補正後の能力計u（小数3桁。ref45では能力計ab）、p3=全頭モデルでの3着内確率。
    uの順位（高い順、同値は馬番の小さい順）がcut_rankより下、または3着内確率がcut_p3以下の馬を除く。残りが3頭未満になるときは、uの上位3頭を残す（安全策。v4.6から継続。safety=True）。"""
    if cfg is None:
        cfg = P1_CFG
    n = len(nums)
    order = sorted(range(n), key=lambda j: (-u3[j], nums[j]))
    rank = {j: r + 1 for r, j in enumerate(order)}
    pool = [j for j in order if rank[j] <= cfg["cut_rank"] and p3[j] > cfg["cut_p3"]]
    safety = len(pool) < 3
    if safety:
        pool = order[:3]
    return {"cut": sorted(nums[j] for j in range(n) if j not in pool), "pool": sorted(nums[j] for j in pool), "safety": bool(safety)}


def pool_ranked(nums, tp, pool):
    """残った馬の3頭の組だけを、全頭三連複確率（tp）の高い順に並べる。同じ確率（小数9桁で丸めて比べる）の組は、馬番を昇順に並べた3つ組の辞書順。
    戻り値: [(組の馬番タプル(昇順), 全頭での確率)]。選定馬だけで勝率を作り直すことはしない（v4.6のステップ9は廃止）。"""
    ps = set(pool)
    rows = []
    for idx, pr in tp.items():
        c = tuple(sorted(nums[j] for j in idx))
        if all(u in ps for u in c):
            rows.append((c, pr))
    rows.sort(key=lambda r: (-round(r[1], 9), r[0]))
    return rows




def _top_rows(ranked):
    return [{"rank": i, "combo": "-".join(str(u) for u in c), "p": round(pr, 6)} for i, (c, pr) in enumerate(ranked[:TOPN], 1)]


def _rank_list2(rows, expected):
    if not isinstance(rows, list) or len(rows) != min(TOPN, len(expected)):
        raise ValueError("順位リスト長さ不一致（上位最大20点が必要）")
    for i, (t, (combo, pr)) in enumerate(zip(rows, expected), 1):
        key = "-".join(map(str, combo))
        if type(t.get("rank")) is not int or t["rank"] != i or t.get("combo") != key:
            raise ValueError("rank連番・組・順位不一致")
        if not _finite(t.get("p")) or abs(t["p"] - pr) > 0.00000051:
            raise ValueError("順位リスト確率不一致")


def _sel_expected(nums, u3, pw6, g, nige_all):
    """v4.7の切り捨てと候補の組の順位づけを再計算する（分析計算v4.7.pyと同じ式）。"""
    tp = trio_probs(pw6, g)
    p3 = [0.0] * len(nums)
    for idx, pr in tp.items():
        for j in idx:
            p3[j] += pr
    sel = select_v47(nums, u3, p3)
    ranked = pool_ranked(nums, tp, sel["pool"])
    sel.update({"nige_all": nige_all, "ncomb_pool": len(ranked), "all_buy": len(ranked) <= TOPN})
    return tp, sel, ranked


def validate_rec(rec):
    """仮想購入と参考順位を別々に再計算する。丸められた能力には区間を使う。"""
    nums = rec["nums"]
    n = rec["heads"]
    if type(n) is not int or n < 3 or len(nums) != n or any(type(u) is not int or u <= 0 for u in nums) or len(set(nums)) != n:
        raise ValueError("頭数・馬番不一致")
    mode = rec["mode"]
    if mode not in ("通常", "新馬") or "p1" not in rec or ((mode == "新馬") != (rec["p1"] is None)):
        raise ValueError("モードとp1 nullの不整合")
    par = rec["par"]
    if par["style_adjust"] is not False or par["p1"] != P1_CFG or par["g"] != 0.8 or rec["scale"] != par["scale"]:
        raise ValueError("補正なし・切り捨て・g・scale設定不一致")
    if mode == "通常" and par.get("recency") != RECENCY:
        raise ValueError("近走の重み(recency)不一致")
    if mode == "通常" and par.get("nige_np_min") != NIGE_NP_MIN:
        raise ValueError("逃げの判定基準(par.nige_np_min)不一致")
    if mode == "通常" and par.get("nige_boost") != NIGE_BOOST:
        raise ValueError("逃げ補正の設定(par.nige_boost)不一致")
    if rec.get("buy_cfg") != BUY_CFG:
        raise ValueError("固定購入設定の欠落・改変")
    _prob_vector(rec["p_win"], n)
    hs = rec["hs"]
    if len(hs) != n or {h["n"] for h in hs} != set(nums) or len(rec["style"]) != n:
        raise ValueError("全頭評価の欠落・重複")
    hm = {h["n"]: h for h in hs}
    g = par["g"]
    if mode == "通常":
        _check_nige_style(rec["style"], [hm[u].get("np") for u in nums], [hm[u].get("fm") for u in nums])
        nige_all = sum(1 for s_ in rec["style"] if s_ == "逃げ")
        for u in nums:
            want = NIGE_BOOST if rec["style"][nums.index(u)] == "逃げ" else 0.0
            h = hm[u]
            if not _finite(h.get("adj")) or abs(h["adj"] - want) > 1e-9:
                raise ValueError("hs.adj(逃げ補正)が脚質と不一致")
            if not _finite(h.get("u")) or not _finite(h.get("ab")) or abs(h["u"] - (h["ab"] + h["adj"])) > 0.0011:
                raise ValueError("hs.uが能力計+逃げ補正と不一致")
        if not _check_rounded_softmax(rec["p_win"], [hm[u]["ab"] + hm[u]["adj"] for u in nums]):
            raise ValueError("勝率と能力+逃げ補正の丸め区間不一致")
        tp, sel, ranked = _sel_expected(nums, [hm[u]["u"] for u in nums], rec["p_win"], g, nige_all)
        if rec["p1"] != sel:
            raise ValueError("切り捨て・候補の再計算と不一致（RECのp1）")
        _rank_list2(rec["top"], ranked)
        r45 = rec.get("ref45")
        if not isinstance(r45, dict) or len(r45.get("ab", [])) != n or len(r45.get("p_win", [])) != n:
            raise ValueError("比較用の記録ref45の欠落・長さ不一致")
        if r45["ab"] != [hm[u]["ab"] for u in nums]:
            raise ValueError("ref45の能力計と本命の能力計の不一致")
        _prob_vector(r45["p_win"], n)
        if not _check_rounded_softmax(r45["p_win"], r45["ab"]):
            raise ValueError("ref45の勝率と能力計の丸め区間不一致")
        tp45, sel45, ranked45 = _sel_expected(nums, r45["ab"], r45["p_win"], g, nige_all)
        if r45["p1"] != sel45:
            raise ValueError("ref45の切り捨て・候補の再計算と不一致")
        _rank_list2(r45["top"], ranked45)
        q = rec.get("q")
        if not isinstance(q, dict) or q.get("date_ok") is not True:
            raise ValueError("品質の記録(q)の欠落、または近走欄の最新日がレース日以降")
    else:
        if rec.get("ref45") is not None:
            raise ValueError("新馬モードに通常専用記録が混入")
        tp = trio_probs(rec["p_win"], g)
        ranked = [(tuple(sorted(nums[j] for j in idx)), pr) for idx, pr in sorted(tp.items(), key=lambda kv: -kv[1])]
        _rank_list2(rec["top"], ranked)
    buy = [dict(t, pf=t.get("pf", t["p"])) for t in rec["top"] if in_buy(t["rank"])]
    if rec.get("buy") != buy:
        raise ValueError("仮想購入buyの欠落・改変・順序不一致")
    if rec.get("buy_points") != len(buy) or rec.get("buy_stake") != 100 * len(buy) or rec.get("buy_full_cover") is not (len(buy) == math.comb(n, 3)):
        raise ValueError("仮想購入点数・投資・全組購入不一致")
    if rec.get("buy_mass") != round(sum(t["pf"] for t in buy), 6):
        raise ValueError("仮想購入質量不一致")
    _marks_check(rec.get("marks"), [t["combo"] for t in buy])
    refs = rec.get("reference_marks")
    if not isinstance(refs, dict) or set(refs) != {str(k) for k in POINTS if k <= len(rec["top"])}:
        raise ValueError("参考マーク記録の欠落")
    for k, ents in refs.items():
        _marks_check(ents, [t["combo"] for t in rec["top"][:int(k)]])
    return tp


def parse_result(res_str):
    """結果の文字列を [(着順3頭のリスト, 払戻), ...] にする。同着で組が複数あるときはカンマで並べる。先頭の要素だけ race_id/ を付けてよい。"""
    s = res_str.replace("円", "").replace("　", " ")
    items, rid = [], None
    parts = [p for p in re.split(r"[,、，]", s) if p.strip()]
    for k, p in enumerate(parts):
        m = re.match(r"\s*(?:(\d{10,})\s*/\s*)?(\d+)\s*[-－ー]\s*(\d+)\s*[-－ー]\s*(\d+)\s*[/ ]\s*(\d+)\s*$", p)
        if not m or (m.group(1) and k > 0):
            return None, None
        if m.group(1):
            rid = m.group(1)
        items.append(([int(m.group(2)), int(m.group(3)), int(m.group(4))], int(m.group(5))))
    return (items, rid) if items else (None, None)


def _bet_result(top_rows, pmap, combos_hit, pay_of, cut, order_horses, sel):
    buy = [t for t in top_rows if in_buy(t["rank"])]
    hits = [t for t in buy if t["combo"] in combos_hit]
    ret = sum(pay_of[t["combo"]] for t in hits)
    return {"points": len(buy), "stake": BUY_CFG["unit_yen"] * len(buy), "combos": [t["combo"] for t in buy],
            "hit": bool(hits), "hit_rank": min((t["rank"] for t in hits), default=None), "ret": ret,
            "mass": round(sum(pmap[t["combo"]] for t in buy), 8), "cut_n": len(cut), "cut_hit": bool(set(order_horses) & set(cut)),
            "pool_n": len(sel["pool"]), "ncomb_pool": sel["ncomb_pool"], "all_buy": sel["all_buy"], "safety": sel["safety"]}


def kosatsu(rec_arg, res_str):
    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    try:
        rec = load_rec(rec_arg)
    except Exception as e:
        return stop("分析時のREC行を読めません: %s" % e)
    if rec.get("ver") != RULE_VERSION:
        return stop("版番号不一致 REC=%s 考察計算=%s" % (rec.get("ver"), RULE_VERSION))
    if not rec.get("code"):
        return stop("REC行に分析側コード指紋(code)がありません。分析計算%s.pyで作ったRECを使ってください" % RULE_VERSION)
    try:
        tp = validate_rec(rec)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as e:
        return stop("REC厳密照合: %s" % e)
    print("[分析側コード指紋 sha256先頭12桁=%s]" % rec["code"])
    items, rid = parse_result(res_str)
    if not items:
        return stop('結果は "1-2-3/500円"（着順/100円あたり三連複払戻）の形式で渡してください（同着は "1-2-3/500円,1-2-4/700円"）')
    if rid and rid != rec.get("race_id"):
        return stop("レースID不一致 予想=%s 結果=%s" % (rec.get("race_id"), rid))
    nums, pw = rec["nums"], rec["p_win"]
    g = rec["par"]["g"]
    n = len(nums)
    mode = rec["mode"]
    orders = [o for o, _ in items]
    for o in orders:
        if len(set(o)) != 3 or any(x not in nums for x in o):
            return stop("着順%s が出走馬番%sに含まれません（取消・除外の馬が入っていないか確認してください）" % (o, nums))
    pay_of = {}
    for o, pay in items:
        k = "-".join(str(x) for x in sorted(o))
        if k in pay_of:
            return stop("同じ組が重複しています: %s" % k)
        pay_of[k] = pay
    combos_hit = set(pay_of)
    idxof = {u: i for i, u in enumerate(nums)}
    key = lambda idx: "-".join(str(x) for x in sorted(nums[j] for j in idx))
    pmap = {key(idx): pr for idx, pr in tp.items()}
    p3 = [0.0] * n
    for idx, pr in tp.items():
        for j in idx:
            p3[j] += pr
    r3_order = sorted(range(n), key=lambda j: -p3[j])
    r3 = {nums[j]: r + 1 for r, j in enumerate(r3_order)}
    rw_order = sorted(range(n), key=lambda j: -pw[j])
    rw = {nums[j]: r + 1 for r, j in enumerate(rw_order)}
    styles = dict(zip(nums, rec["style"]))
    order_horses = sorted({x for o in orders for x in o})
    p_act = sum(pmap[c] for c in combos_hit)
    lnP47 = math.log(p_act)
    hsm = {h["n"]: h for h in rec["hs"]}
    obm = {o["n"]: o for o in rec.get("obs", [])}
    hk = rec.get("hk", [])
    top_rows = rec["top"]
    sel = rec["p1"]
    pay_sum = sum(p for _, p in items)
    if mode == "通常":
        r45 = rec["ref45"]
        tp45 = trio_probs(r45["p_win"], g)
        pmap45 = {key(idx): pr for idx, pr in tp45.items()}
        p45 = sum(pmap45[c] for c in combos_hit)
        lnP45 = math.log(p45)
        delta = lnP47 - lnP45
        b47 = _bet_result(top_rows, pmap, combos_hit, pay_of, sel["cut"], order_horses, sel)
        b45 = _bet_result(r45["top"], pmap45, combos_hit, pay_of, r45["p1"]["cut"], order_horses, r45["p1"])
        b45["mass"] = round(sum(pmap45[t["combo"]] for t in r45["top"] if in_buy(t["rank"])), 8)
    else:
        lnP45 = delta = p45 = None
        b47 = _bet_result(top_rows, pmap, combos_hit, pay_of, [], order_horses, {"pool": nums, "ncomb_pool": len(pmap), "all_buy": False, "safety": False})
        b45 = None
    hf = []
    for j in r3_order:
        u = nums[j]
        h_ = hsm[u]
        o_ = obm.get(u, {})
        hf.append({"n": u, "s": styles[u], "r3": r3[u], "p3": round(p3[j], 4), "in": 1 if u in order_horses else 0, "pw": round(pw[j], 6),
                   "pw45": (rec["ref45"]["p_win"][j] if mode == "通常" else None), "rw": rw[u],
                   "ab": h_["ab"], "bo": h_.get("adj", 0.0), "u": h_.get("u"), "c": h_["c"], "np": h_.get("np"), "fm": h_.get("fm"), "fr": h_.get("fr"),
                   "raw": h_.get("raw"), "nr": h_.get("nr"), "sk": h_.get("sk"), "wd": o_.get("wd"), "dx": o_.get("dx"), "tr": o_.get("tr")})
    rid_ = rec["race_id"]
    ledger = {
        "ver": RULE_VERSION, "code_k": code_sha(), "code_a": rec["code"], "scale": rec.get("scale"), "g": g, "mode": mode,
        "race_id": rid_, "date": rid_[:8], "venue": rec["venue"], "dist": rec["dist"], "rno": int(rid_[-2:]), "heads": n,
        "nige_all": sel["nige_all"] if mode == "通常" else None,
        "orders": orders, "pays": [p for _, p in items], "combos": sorted(combos_hit),
        "p47": float("%.9g" % p_act), "p45": None if p45 is None else float("%.9g" % p45),
        "lnP47": round(lnP47, 6), "lnP45": None if lnP45 is None else round(lnP45, 6), "delta": None if delta is None else round(delta, 6),
        "b47": b47, "b45": b45, "all_buy": bool(b47["all_buy"]) if mode == "通常" else False,
        "excl": None if mode == "通常" else "新馬モード（評価の対象外）", "q": rec.get("q"), "hk": hk, "hf": hf, "nums_rec": nums, "warnings": rec.get("warnings", []),
        "style_table": rec.get("style_table"), "par": rec.get("par"),
    }
    print("【考察 %s】レースID=%s %s %sm %d頭 モード=%s" % (RULE_VERSION, rid_, rec["venue"], rec["dist"], n, mode))
    print("結果: 着順 %s / 三連複 %s / 払戻(100円) %s円" % (" , ".join("-".join(map(str, o)) for o in orders), " , ".join(sorted(combos_hit)), " , ".join(str(p) for _, p in items)))
    print("確率式: ヘンリー型 g=%s（全頭の勝率から計算。選定馬で作り直さない）" % g)
    if mode == "通常":
        print("1. 主評価の値: ln P_v47=%+.4f（P=%.3f%%）／ ln P_ref45=%+.4f（P=%.3f%%）／ Δ=%+.4f%s" %
              (lnP47, p_act * 100, lnP45, p45 * 100, delta, "（逃げ馬なしのためΔ=0）" if sel["nige_all"] == 0 else ""))
        print("2. 仮想購入（連続上位1〜20位・各100円）: v4.7=%s／ref45=%s" % (
            "%d点 %s 払戻%d円（仮想）%s" % (b47["points"], "的中(原順位%s)" % b47["hit_rank"] if b47["hit"] else "不的中", b47["ret"], "［全買い］" if b47["all_buy"] else ""),
            "%d点 %s 払戻%d円（仮想）%s" % (b45["points"], "的中(原順位%s)" % b45["hit_rank"] if b45["hit"] else "不的中", b45["ret"], "［全買い］" if b45["all_buy"] else "")))
        print("3. 切り捨て: v4.7=%s（実際の3着内に切り捨てた馬: %s）／ref45=%s（同: %s）／逃げ馬の頭数=%d" %
              (",".join(map(str, sel["cut"])) or "なし", "あり" if b47["cut_hit"] else "なし", ",".join(map(str, r45["p1"]["cut"])) or "なし", "あり" if b45["cut_hit"] else "なし", sel["nige_all"]))
        print("4. 着順の馬の評価（モデルは何位に見ていたか）")
        for pos, u in enumerate(orders[0], 1):
            i = idxof[u]
            print("   %d着 %2d番 脚質=%s 勝率%.1f%%(%d位) 3着内確率%.1f%%(%d位)" % (pos, u, styles[u], pw[i] * 100, rw[u], p3[i] * 100, r3[u]))
        print("   モデル勝率上位3頭 %s のうち3着以内に入った頭数=%d" % (",".join(str(nums[j]) for j in rw_order[:3]), len(set(nums[j] for j in rw_order[:3]) & set(orders[0]))))
        low = [j for j in r3_order if r3[nums[j]] >= 7]
        print("5. 下位馬（3着内確率7位以下）%d頭のうち3着以内に入った頭数: 実際%d / 期待%.2f" % (len(low), sum(1 for j in low if nums[j] in order_horses), sum(p3[j] for j in low)))
        for j in low:
            u = nums[j]
            if u in order_horses:
                h_ = hsm[u]
                print("   %d位 %2d番 脚質=%s 3着内確率%.1f%% 項目別寄与: %s" % (r3[u], u, styles[u], p3[j] * 100, " ".join("%s%+.2f" % (ITEM_JA.get(k, k), v) for k, v in zip(hk, h_["c"]))))
        q = rec.get("q") or {}
        print("6. 品質: 取消・除外=%s頭（欠けた馬番=%s）／頭数表記=%s・抽出=%s／1角位置の取れない馬=%s頭／特徴量の欠測率=%s" %
              (q.get("scratched"), ",".join(map(str, q.get("missing_nums", []))) or "なし", q.get("heads_hdr"), q.get("heads_parsed"), q.get("fm_missing"), q.get("feat_missing")))
    else:
        print("新馬モード: 評価の対象外（主評価・副評価に入れない）。仮想購入 %d点 %s 払戻%d円（仮想）" % (b47["points"], "的中" if b47["hit"] else "不的中", b47["ret"]))
    if rec.get("warnings"):
        print("分析時の警告: " + " / ".join(rec["warnings"]))
    print("LEDGER行(下の1行を集計用に保存):")
    print("LEDGER " + json.dumps(ledger, ensure_ascii=False, separators=(",", ":")))
    return 0


def validate_ledger(x):
    """LEDGER行を、全頭の勝率(hf)と結果から再計算して照合する。主評価・副評価・併記の値は、この行だけから再計算できる。"""
    if x.get("ver") != RULE_VERSION:
        raise ValueError("版が違います(%s)。旧版の行は混ぜられません" % x.get("ver"))
    if x.get("code_k") != code_sha():
        raise ValueError("考察側コード指紋(%s)が本ファイルと一致しません（混在または別版）" % x.get("code_k"))
    if not x.get("code_a"):
        raise ValueError("分析側コード指紋が欠落しています")
    mode = x.get("mode")
    if mode not in ("通常", "新馬"):
        raise ValueError("モードが不正です")
    g = x.get("g")
    if g != 0.8:
        raise ValueError("gが0.8ではありません(%s)" % g)
    nums, n = x["nums_rec"], x["heads"]
    hf = x["hf"]
    if len(hf) != n or {h["n"] for h in hf} != set(nums) or len(nums) != n:
        raise ValueError("全頭の詳細(hf)がない、または馬番が合いません")
    hm = {h["n"]: h for h in hf}
    pw = [hm[u]["pw"] for u in nums]
    _prob_vector(pw, n)
    orders, pays, combos = x["orders"], x["pays"], x["combos"]
    if not orders or len(orders) != len(pays) or len(combos) != len(set(combos)):
        raise ValueError("着順・払戻・組の記録が不正です")
    for o in orders:
        if len(set(o)) != 3 or any(u not in nums for u in o):
            raise ValueError("着順の馬番が出走馬にありません")
    if sorted("-".join(str(u) for u in sorted(o)) for o in orders) != sorted(combos):
        raise ValueError("着順と組の記録が一致しません")
    pay_of = {"-".join(str(u) for u in sorted(o)): p for o, p in zip(orders, pays)}
    ix = {u: i for i, u in enumerate(nums)}

    def p_of(vec):
        return sum(trio_actual(vec, [ix[int(v)] for v in c.split("-")], g) for c in combos)
    pa47 = p_of(pw)
    if abs(pa47 - x["p47"]) > 1e-8 * pa47 + 1e-12:
        raise ValueError("p47が全頭の勝率からの再計算と一致しません")
    b = x["b47"]
    if not (isinstance(b, dict) and b["points"] == min(TOPN, b["ncomb_pool"]) if mode == "通常" else isinstance(b, dict)):
        raise ValueError("仮想購入の点数が不正です")
    bs = [x["b47"]] + ([x["b45"]] if mode == "通常" else [])
    for bb in bs:
        if bb["stake"] != BUY_CFG["unit_yen"] * bb["points"] or bb["points"] != len(bb["combos"]) or bb["points"] > TOPN:
            raise ValueError("仮想購入の点数・投資が不正です")
        hits = [c for c in bb["combos"] if c in pay_of]
        if bb["hit"] != bool(hits) or bb["ret"] != sum(pay_of[c] for c in hits):
            raise ValueError("仮想購入の的中・払戻が結果と一致しません")
    if mode == "通常":
        pw45 = [hm[u]["pw45"] for u in nums]
        if any(v is None for v in pw45):
            raise ValueError("ref45の勝率(pw45)がありません")
        _prob_vector(pw45, n)
        pa45 = p_of(pw45)
        if abs(pa45 - x["p45"]) > 1e-8 * pa45 + 1e-12:
            raise ValueError("p45が全頭の勝率からの再計算と一致しません")
        if abs(math.log(pa47) - x["lnP47"]) > 2e-6 or abs(math.log(pa45) - x["lnP45"]) > 2e-6 or abs(x["lnP47"] - x["lnP45"] - x["delta"]) > 3e-6:
            raise ValueError("対数スコア・Δが確率と一致しません")
        if x["nige_all"] != sum(1 for h in hf if h["s"] == "逃げ"):
            raise ValueError("逃げ馬の頭数が脚質と一致しません")
        for bb, nm in ((x["b47"], "v4.7"), (x["b45"], "ref45")):
            if bb["all_buy"] != (bb["ncomb_pool"] <= TOPN) or bb["points"] != min(TOPN, bb["ncomb_pool"]):
                raise ValueError("%sの全買い・点数が候補の組数と一致しません" % nm)
        if x["all_buy"] != x["b47"]["all_buy"]:
            raise ValueError("全買いフラグ不一致")
        q = x.get("q")
        if not isinstance(q, dict) or q.get("date_ok") is not True:
            raise ValueError("品質の記録(q)がない、または近走欄の最新日がレース日以降です")
    if (x.get("excl") is None) != (mode == "通常"):
        raise ValueError("除外の理由(excl)がモードと一致しません")
    if x["date"] != x["race_id"][:8] or x["rno"] != int(x["race_id"][-2:]):
        raise ValueError("レースIDと日付・R番号が一致しません")


def read_ledger(path):
    L, study, stops = [], {}, 0
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if line.startswith("LEDGER "):
            try:
                x = json.loads(line[7:])
                validate_ledger(x)
            except (KeyError, TypeError, ValueError, IndexError, OverflowError, json.JSONDecodeError) as e:
                raise ValueError("%d行目のLEDGER行が読めない・照合できません: %s" % (ln, e))
            L.append(x)
        elif line.startswith("STUDY "):
            study = json.loads(line[6:])
        elif line.startswith("STOP"):
            stops += 1
    if not L:
        raise ValueError("LEDGER行がありません")
    ids = [x["race_id"] for x in L]
    if len(ids) != len(set(ids)):
        raise ValueError("レースIDが重複しています: " + ",".join(sorted({i for i in ids if ids.count(i) > 1})))
    if len({x["code_a"] for x in L}) != 1:
        raise ValueError("分析側コード指紋が混在しています: " + ",".join(sorted({x["code_a"] for x in L})))
    if len({x["scale"] for x in L if x["mode"] == "通常"}) > 1:
        raise ValueError("能力差倍率が混在しています")
    return L, study, stops


def _boot_ci(stat, n, B=BOOT_B, seed=BOOT_SEED):
    """レース単位のブートストラップ。stat(idxリスト)->値。95%区間（パーセンタイル）を返す。"""
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        vals.append(stat([rng.randrange(n) for _ in range(n)]))
    vals.sort()
    return vals[int(round(0.025 * B))], vals[int(round(0.975 * B)) - 1]


def _tbl(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(out)


def aggregate(path):
    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    try:
        L, study, stops = read_ledger(path)
    except (ValueError, OSError) as e:
        print("【停止】" + str(e))
        return 1
    print("分析側コード指紋=%s（運用メモの正本表と照合すること）／能力差倍率scale(通常モード)=%s／g=%s／逃げ補正=%+.1f／版=%s" %
          (L[0]["code_a"], sorted({x["scale"] for x in L if x["mode"] == "通常"})[0] if any(x["mode"] == "通常" for x in L) else "なし", L[0]["g"], NIGE_BOOST, RULE_VERSION))
    start = study.get("start")
    if not start:
        print("注意: STUDY行（開始日）がありません。開始日による絞り込みは行いません。運用メモに記録した開始日・対象の場と照合してください。")
    design = [x for x in L if x["race_id"] in EXCLUDE_IDS]
    before = [x for x in L if x["race_id"] not in EXCLUDE_IDS and start and x["date"] < start]
    debut = [x for x in L if x["mode"] == "新馬" and x not in design and x not in before]
    elig = sorted([x for x in L if x["mode"] == "通常" and x not in design and x not in before], key=lambda x: x["race_id"])
    n = len(elig)
    print("")
    print("**【件数と品質】**（Δ・回収率は、対象が%dレースに達するまで計算も表示もしない）" % JUDGE_N)
    print("")
    qs = [x["q"] for x in elig]
    scr_races = sum(1 for q in qs if q.get("scratched"))
    mism = sum(1 for q in qs if q.get("heads_hdr") and q.get("heads_hdr") != q.get("heads_parsed"))
    fm_races = sum(1 for q in qs if q.get("fm_missing"))
    fmiss = (sum(q.get("feat_missing", 0.0) for q in qs) / n) if n else 0.0
    venues = {}
    for x in elig:
        venues[x["venue"]] = venues.get(x["venue"], 0) + 1
    rows = [["LEDGER行（全体）", len(L)], ["検証に使わない（設計に使ったレース）", len(design)], ["検証に使わない（開始日より前）", len(before)],
            ["新馬モード（評価の対象外）", len(debut)], ["対象の通常モードのレース", n],
            ["　うち逃げ馬ありのレース", sum(1 for x in elig if x["nige_all"] > 0)], ["　うち逃げ馬なし（Δ=0）", sum(1 for x in elig if x["nige_all"] == 0)],
            ["　うち全買い（回収率の評価から除く）", sum(1 for x in elig if x["all_buy"])],
            ["取消・除外のあるレース（頭数計）", "%d（%d頭）" % (scr_races, sum(q.get("scratched", 0) for q in qs))],
            ["頭数表記と抽出頭数が違うレース", mism], ["1角位置の取れない馬のあるレース", fm_races],
            ["特徴量の欠測率（レース平均。体重を除く）", "%.2f%%" % (fmiss * 100)], ["近走欄の最新日がレース日以降", "0（あれば行を作る段階で停止している）"],
            ["停止の件数（STOP行）", stops],
            ["開催日の範囲", "%s〜%s" % (elig[0]["date"], elig[-1]["date"]) if n else "-"],
            ["場別の件数", " ／ ".join("%s=%d" % (k, v) for k, v in sorted(venues.items())) or "-"]]
    print(_tbl(["項目", "値"], rows))
    print("")
    if n < JUDGE_N:
        extra = "（200レースに達しています。中間報告は上の品質の項目だけです）" if n >= 200 else ""
        print("対象は%dレース。判定には%dレース必要です（あと%dレース）。判定の途中経過は出しません。%s" % (n, JUDGE_N, JUDGE_N - n, extra))
        return 0
    J = elig
    NJ = len(J)
    print("**【判定】**判定の時点で揃っている対象の通常モードのレース全部（%dレース。最初=%s、最後=%s）を使う。300レースちょうどには切らない。" %
          (NJ, J[0]["race_id"], J[-1]["race_id"]))
    print("")
    d = [x["delta"] for x in J]
    m = sum(d) / NJ
    lo, hi = _boot_ci(lambda idx: sum(d[i] for i in idx) / NJ, NJ, seed=BOOT_SEED)
    print("**主評価** Δ_r = ln P_v47(実際の組) − ln P_ref45(実際の組)（全買いのレースも含む。同着は各組のPの合計）")
    print("")
    print("Δの平均=%+.5f／95%%区間（レース単位の対ブートストラップ%d回・乱数シード%d）=[%+.5f, %+.5f]／下限>0=%s" % (m, BOOT_B, BOOT_SEED, lo, hi, "はい" if lo > 0 else "いいえ"))
    print("")
    print("**判定: %s**" % ("補正に効果あり" if lo > 0 else "効果を確認できず"))
    print("")
    nz = [x for x in J if x["nige_all"] > 0]
    dz = [x["delta"] for x in nz]
    n_zero = sum(1 for x in J if x["nige_all"] == 0)
    n_dzero = sum(1 for v in d if abs(v) < 1e-9)
    mz = sum(dz) / len(dz) if dz else float("nan")
    lz, hz = _boot_ci(lambda idx: sum(dz[i] for i in idx) / len(dz), len(dz), seed=BOOT_SEED + 1) if dz else (float("nan"), float("nan"))
    print("**併記（参考。判定には使わない）**")
    print("")
    print(_tbl(["項目", "値"], [["逃げ馬ありのレース数", len(nz)], ["逃げ馬なし（u=abなのでΔ=0）のレース数", n_zero], ["Δが0のレース数（|Δ|<1e-9）", n_dzero],
                              ["逃げ馬ありのレースのΔの平均", "%+.5f" % mz], ["　95%%区間（シード%d）" % (BOOT_SEED + 1), "[%+.5f, %+.5f]" % (lz, hz)],
                              ["Δ>0のレース数／Δ<0のレース数", "%d／%d" % (sum(1 for v in d if v > 1e-9), sum(1 for v in d if v < -1e-9))]]))
    print("")
    ng = [x for x in J if not x["all_buy"]]
    r47 = [x["b47"]["ret"] for x in ng]
    s47 = [x["b47"]["stake"] for x in ng]
    r45 = [x["b45"]["ret"] for x in ng]
    s45 = [x["b45"]["stake"] for x in ng]

    def roi_diff(idx):
        a = sum(r47[i] for i in idx)
        b_ = sum(s47[i] for i in idx)
        c = sum(r45[i] for i in idx)
        e = sum(s45[i] for i in idx)
        return a / b_ - c / e
    if ng:
        rl, rh = _boot_ci(roi_diff, len(ng), seed=BOOT_SEED + 2)
        print("**副評価（仮想回収率。全買いを除く%dレース。採否に使わない。実際の馬券は買わない）**" % len(ng))
        print("")
        print(_tbl(["方式", "的中数", "期待的中（全頭確率質量の和）", "投資（仮想）", "払戻（仮想）", "仮想回収率"],
                   [["v4.7", sum(1 for x in ng if x["b47"]["hit"]), "%.1f" % sum(x["b47"]["mass"] for x in ng), sum(s47), sum(r47), "%.1f%%" % (100.0 * sum(r47) / sum(s47))],
                    ["ref45（補正なし）", sum(1 for x in ng if x["b45"]["hit"]), "%.1f" % sum(x["b45"]["mass"] for x in ng), sum(s45), sum(r45), "%.1f%%" % (100.0 * sum(r45) / sum(s45))]]))
        print("")
        print("回収率の差（v4.7−ref45）=%+.1f%%ポイント／95%%区間（シード%d）=[%+.1f, %+.1f]%%ポイント" % (100 * roi_diff(list(range(len(ng)))), BOOT_SEED + 2, 100 * rl, 100 * rh))
        print("")
    print("**参考（記録のみ。変更の根拠にしない）**")
    print("")
    byv = {}
    for x in J:
        byv.setdefault(x["venue"], []).append(x["delta"])
    print(_tbl(["場", "レース数", "Δの平均"], [[k, len(v), "%+.4f" % (sum(v) / len(v))] for k, v in sorted(byv.items())]))
    print("")
    rows = []
    for gg in GRID_G:
        a_ = b_ = 0.0
        for x in J:
            nums = x["nums_rec"]
            hm = {h["n"]: h for h in x["hf"]}
            ix = {u: i for i, u in enumerate(nums)}
            v47 = [hm[u]["pw"] for u in nums]
            v45 = [hm[u]["pw45"] for u in nums]
            f = lambda vec: math.log(sum(trio_actual(vec, [ix[int(v)] for v in c.split("-")], gg) for c in x["combos"]))
            a_ += f(v47)
            b_ += f(v45)
        rows.append(["%.1f" % gg, "%+.4f" % (a_ / NJ), "%+.4f" % (b_ / NJ), "%+.4f" % ((a_ - b_) / NJ)])
    print("gの感度（β=1・補正0.9は固定。gだけ変えた場合の平均対数スコア）。使用g=0.8。検証期間中は変えない。")
    print("")
    print(_tbl(["g", "v4.7の平均ln P", "ref45の平均ln P", "Δの平均"], rows))
    return 0


def main():
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "kosatsu":
        return kosatsu(a[1], " ".join(a[2:]))
    if len(a) >= 2 and a[0] == "aggregate":
        return aggregate(a[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
