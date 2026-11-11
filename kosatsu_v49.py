# -*- coding: utf-8 -*-
"""考察計算v4.9.py（Web版のファイル名は kosatsu_v49.py。中身は同一）  結果の考察と、複数レースの集計（v4.9 の判定）
v4.9:
 (1) モデルの判定: Δ_r = ln P_v4.9(実際の三連複の組) − ln P_v4.8(同じ組。v4.8 の予想のモデル p48・g=0.9986)。同着は各組のPの合計。
     対象の通常モードのレースが300以上に達した時点で、揃っている全レースを使って1回だけ判定する（300ちょうどには切らない）。
     Δの平均の対ブートストラップ（レース単位・10,000回・乱数シード20261201）の95%区間の下限が0を超えれば「効果あり」。
 (2) 買い方の判定: 案B（複勝の期待値0.9以上）。モデルの判定と同じく、対象の通常モードのレースが300以上に達した時点で、揃っている全レースのうち
     単勝・複勝の払戻がそろったレースを使って1回だけ判定する。回収率（総払戻÷総投資）の対ブートストラップ（レース単位・10,000回・シード20261212）の95%区間の下限が100%を超えれば
     「回収率100%超えを確認」。案A・案C は同じレースで記録する（シード20261211・20261213。判定に使わない）。
 (3) それぞれ、条件に達するまでは判定の値を計算も表示もしない。
 (4) 検証に使わないレース（レースIDで除く）: 設計に使った607レース（v49_params.json の design.race_ids）、v4.8 の設計用データ（v48_params.json の design.race_ids）、
     v4.8 の EXCLUDE_IDS（v4.7 の LEDGER の全レース・v4.6 の検討に使ったレース・混在の見送り）。検証に使うレースの選び方・開始日はユーザーが管理する（STUDY 行で開始日を指定できる）。
使い方
  1) python 考察計算v4.9.py kosatsu 分析出力.txt 結果.txt   （結果.txt は result_v49.py が作る "RES {...}" の1行。手入力の場合も同じ形）
  2) python 考察計算v4.9.py aggregate <LEDGER行を集めたファイル>
"""
import sys, re, json, math, os, random, hashlib, importlib.util

RULE_VERSION = "v4.9"
JUDGE_N = 300
BOOT_B = 10000
SEED_MODEL = 20261201
SEED_PLAN = {"案A": 20261211, "案B": 20261212, "案C": 20261213}
HERE = os.path.dirname(os.path.abspath(__file__))
PTYPES = ["単勝", "複勝", "ワイド", "馬連", "三連複"]


def _load(names, mod):
    for n in names:
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location(mod, p)
            m = importlib.util.module_from_spec(spec)
            sys.modules[mod] = m
            spec.loader.exec_module(m)
            return m
    raise SystemExit("【停止】同じフォルダに %s がありません" % " または ".join(names))


if HERE not in sys.path:
    sys.path.insert(0, HERE)
M = _load(["v49_model.py"], "v49_model")
PAR = M.load_params()
M48 = M.M48
PAR48 = M48.load_params()
V48_EXCLUDE = set("""
2026050120020501 2026050120020502 2026050120020503 2026050120020504 2026050120020505 2026050120020506
2026050120020507 2026050120020508 2026050120020509 2026050120020510 2026050120020511 2026050120020512
2026050419020101 2026050419020102 2026050419020103 2026050419020104 2026050419020105 2026050419020106
2026050419020107 2026050419020108 2026050419020109 2026050419020110 2026050419020111 2026050419020112
2026050519020201 2026050519020202 2026050519020203 2026050519020204 2026050519020205 2026050519020206
2026050519020207 2026050519020208 2026050519020209 2026050519020210 2026050519020211 2026050519020212
2026050619020301 2026050619020302 2026050619020303 2026050619020304 2026050619020305 2026050619020306
2026050619020307 2026050619020308 2026050619020309 2026050619020310 2026050619020311 2026050619020312
2026050719020401 2026050719020402 2026050719020403 2026050719020404 2026050719020405 2026050719020406
2026050719020407 2026050719020408 2026050719020409 2026050719020410 2026050719020411 2026050719020412
2026050819020501 2026050819020502 2026050819020503 2026050819020504 2026050819020505 2026050819020506
2026050819020507 2026050819020508 2026050819020509 2026050819020510 2026050819020511 2026050819020512
2026051121020101 2026051121020102 2026051121020103 2026051121020104 2026051121020105 2026051121020106
2026051121020107 2026051121020108 2026051121020109 2026051121020110 2026051121020111 2026051121020112
2026051221020201 2026051221020202 2026051221020203 2026051221020204 2026051221020205 2026051221020206
2026051221020207 2026051221020208 2026051221020209 2026051221020210 2026051221020211 2026051221020212
2026051321020301 2026051321020302 2026051321020303 2026051321020304 2026051321020305 2026051321020306
2026051321020307 2026051321020308 2026051321020309 2026051321020310 2026051321020311 2026051321020312
2026060119030101 2026060119030102 2026060119030103 2026060119030104 2026060119030105 2026060119030106
2026060119030107 2026060119030108 2026060119030109 2026060119030110 2026060119030111 2026060119030112
2026060219030201 2026060219030202 2026060219030203 2026060219030204 2026060219030205 2026060219030206
2026060219030207 2026060219030208 2026060219030209 2026060219030210 2026060219030211 2026060219030212
2026060319030301 2026060319030302 2026060319030303 2026060319030304 2026060319030305 2026060319030306
2026060319030307 2026060319030308 2026060319030309 2026060319030310 2026060319030311 2026060319030312
2026060419030401 2026060419030402 2026060419030403 2026060419030404 2026060419030405 2026060419030406
2026060419030407 2026060419030408 2026060419030409 2026060419030410 2026060419030411 2026060419030412
2026060519030501 2026060519030502 2026060519030503 2026060519030504 2026060519030505 2026060519030506
2026060519030507 2026060519030508 2026060519030509 2026060519030510 2026060519030511 2026060519030512
2026060820040101 2026060820040102 2026060820040103 2026060820040104 2026060820040105 2026060820040106
2026060820040107 2026060820040108 2026060820040109 2026060820040110 2026060820040111 2026060920040201
2026060920040202 2026060920040203 2026060920040204 2026060920040205 2026060920040206 2026060920040207
2026060920040208 2026060920040209 2026060920040210 2026060920040211 2026060920040212 2026061020040301
2026061020040302 2026061020040303 2026061020040304 2026061020040305 2026061020040306 2026061020040307
2026061020040308 2026061020040309 2026061020040310 2026061020040311 2026061020040312 2026061120040401
2026061120040402 2026061120040403 2026061120040404 2026061120040405 2026061120040406 2026061120040407
2026061120040408 2026061120040409 2026061120040410 2026061120040411 2026061120040412 2026061220040501
2026061220040502 2026061220040503 2026061220040504 2026061220040505 2026061220040506 2026061220040507
2026061220040508 2026061220040509 2026061220040510 2026061220040511 2026061220040512 2026061521030101
2026061521030102 2026061521030103 2026061521030104 2026061521030105 2026061521030106 2026061521030107
2026061521030108 2026061521030109 2026061521030110 2026061521030111 2026061521030112 2026061621030201
2026061621030202 2026061621030203 2026061621030204 2026061621030205 2026061621030206 2026061621030207
2026061621030208 2026061621030209 2026061621030210 2026061621030211 2026061621030212 2026061721030301
2026061721030302 2026061721030303 2026061721030304 2026061721030305 2026061721030306 2026061721030307
2026061721030308 2026061721030309 2026061721030310 2026061721030311 2026061721030312 2026061821030401
2026061821030402 2026061821030403 2026061821030404 2026061821030405 2026061821030406 2026061821030407
2026061821030408 2026061821030409 2026061821030410 2026061821030411 2026061821030412 2026061921030501
2026061921030502 2026061921030503 2026061921030504 2026061921030505 2026061921030506 2026061921030507
2026061921030508 2026061921030509 2026061921030510 2026061921030511 2026061921030512 2026062218030101
2026062218030102 2026062218030103 2026062218030104 2026062218030105 2026062218030106 2026062218030107
2026062218030108 2026062218030109 2026062218030110 2026062218030111 2026062218030112 2026062318030201
2026062318030202 2026062318030203 2026062318030204 2026062318030205 2026062318030206 2026062318030207
2026062318030208 2026062318030209 2026062318030210 2026062318030211 2026062318030212 2026062418030301
2026062418030302 2026062418030303 2026062418030304 2026062418030305 2026062418030306 2026062418030307
2026062418030308 2026062418030309 2026062418030310 2026062418030311 2026062418030312 2026062518030401
2026062518030402 2026062518030403 2026062518030404 2026062518030405 2026062518030406 2026062518030407
2026062518030408 2026062518030409 2026062518030410 2026062518030411 2026062518030412 2026062618030501
2026062618030502 2026062618030503 2026062618030504 2026062618030505 2026062618030506 2026062618030507
2026062618030508 2026062618030509 2026062618030510 2026062618030511 2026062618030512 2026062920050101
2026062920050102 2026062920050103 2026062920050104 2026062920050105 2026062920050106 2026062920050107
2026062920050108 2026062920050109 2026062920050110 2026062920050111 2026062920050112 2026063020050201
2026063020050202 2026063020050203 2026063020050204 2026063020050205 2026063020050206 2026063020050207
2026063020050208 2026063020050209 2026063020050210 2026063020050211 2026063020050212
""".split())
EXCLUDE_IDS = set(PAR["design"]["race_ids"]) | set(PAR48["design"]["race_ids"]) | V48_EXCLUDE


def code_sha():
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.abspath(__file__), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def stop(msg):
    print("【停止】" + msg)
    return 1


def _read_tag(arg, tag):
    txt = open(arg, encoding="utf-8").read() if os.path.exists(arg) else arg
    m = re.search(r"^" + tag + r" (\{.*\})\s*$", txt, re.M)
    if m:
        return json.loads(m.group(1))
    return json.loads(txt.strip())


def norm_key(combo):
    return "-".join(str(u) for u in sorted(int(u) for u in str(combo).split("-")))


def _close(a, b, tol):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def validate_rec(rec):
    """REC（v4.9）を、記録された項目と係数から再計算して照合する。"""
    if rec.get("ver") != RULE_VERSION:
        raise ValueError("版が違います(%s)" % rec.get("ver"))
    if (rec.get("code_m"), rec.get("code_p"), rec.get("code_m48"), rec.get("code_p48")) != (M.code_sha(), PAR["_sha"], M48.code_sha(), PAR48["_sha"]):
        raise ValueError("v49_model・係数・v48_model・v4.8の係数の指紋が本ファイルの環境と違います")
    if rec["mode"] == "新馬":
        return
    if rec["mode"] != "通常":
        raise ValueError("モードが不正です")
    n = len(rec["nums"])
    for k in ("X", "s", "u48", "p48", "C"):
        if len(rec[k]) != n:
            raise ValueError("%s の長さが頭数と合いません" % k)
    if not _close(rec["s"], M.scores(PAR, rec["X"]), 1e-8):
        raise ValueError("スコアが項目と係数からの再計算と合いません")
    if not _close(rec["p48"], [round(x, 9) for x in M.softmax(rec["u48"])], 1e-8):
        raise ValueError("v4.8 の勝率が能力値と合いません")
    if rec["a1"] != PAR["order"]["a1"] or rec["a2"] != PAR["order"]["a2"] or rec["q1_cut"] != PAR["plans"]["q1_cut"] or rec["g48"] != PAR48["own"]["g"]:
        raise ValueError("着順の係数・境目・g が係数と合いません")
    ts = M.tickets(PAR, rec["nums"], rec["s"])
    pl, h, q1 = M.plans(PAR, rec["nums"], rec["s"], ts)
    if abs(rec["q1"] - q1) > 1e-8:
        raise ValueError("q1 が再計算と合いません")
    for name, _, _ in M.PLANS:
        got = rec["plans"].get(name)
        if got is None or len(got) != len(pl[name]):
            raise ValueError("%s の買い目の数が再計算と合いません" % name)
        for a, x in zip(got, pl[name]):
            if a["t"] != x[0] or a["k"] != x[1] or abs(a["pc"] - x[2]) > 1e-8 or abs(a["ev"] - x[5]) > 1e-5:
                raise ValueError("%s の買い目が再計算と合いません（%s %s）" % (name, a["t"], a["k"]))


def lnP49(s, a1, a2, nums, combos):
    ix = {u: i for i, u in enumerate(nums)}
    p1, w = M.stage(s, a1, a2)
    return math.log(sum(M.trio_prob(p1, w, [ix[int(t)] for t in c.split("-")]) for c in combos))


def lnP48(p, g, nums, combos):
    ix = {u: i for i, u in enumerate(nums)}
    return math.log(sum(M48.trio_prob(p, g, [ix[int(t)] for t in c.split("-")]) for c in combos))


def plan_results(plans, pays):
    pk = {t: {norm_key(r["組"]): r["払戻"] for r in pays.get(t, [])} for t in M.TYPES}
    out = {}
    for name, _, _ in M.PLANS:
        sel = plans[name]
        hits = [{"t": x["t"], "k": x["k"], "pay": pk[x["t"]][x["k"]], "est": x["pay"]} for x in sel if x["k"] in pk[x["t"]]]
        out[name] = {"n": len(sel), "stake": 100 * len(sel), "ret": sum(h["pay"] for h in hits), "hit": bool(hits),
                     "exp": round(sum(x["pc"] for x in sel), 9), "hits": hits, "tickets": [[x["t"], x["k"], x["pc"], x["pay"]] for x in sel]}
    return out


def kosatsu(rec_arg, res_arg):
    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    try:
        rec = _read_tag(rec_arg, "REC")
    except Exception as e:
        return stop("分析時のREC行を読めません: %s" % e)
    try:
        res = _read_tag(res_arg, "RES")
    except Exception as e:
        return stop("結果（RES）を読めません: %s" % e)
    try:
        validate_rec(rec)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        return stop("REC厳密照合: %s" % e)
    print("[分析側の指紋 分析計算v4.9=%s ／ v49_model=%s ／ 係数=%s ／ 分析計算v4.7=%s ／ 候補抽出=%s ／ v48_model=%s ／ v4.8の係数=%s]" %
          (rec["code"], rec["code_m"], rec["code_p"], rec["code_a47"], rec["code_f"], rec["code_m48"], rec["code_p48"]))
    if res.get("race_id") != rec["race_id"]:
        return stop("レースID不一致 予想=%s 結果=%s" % (rec["race_id"], res.get("race_id")))
    nums = rec["nums"]
    orders = res.get("orders") or []
    pays = res.get("pays") or {}
    if not orders or any(len(set(o)) != 3 or any(u not in nums for u in o) for o in orders):
        return stop("着順%s が出走馬番%sに含まれません（取消・除外の馬が入っていないか確認してください）" % (orders, nums))
    combos = sorted({norm_key(r["組"]) for r in pays.get("三連複") or []})
    if not combos or sorted({"-".join(str(u) for u in sorted(o)) for o in orders}) != combos:
        return stop("着順と三連複の組が合いません（着順=%s、三連複=%s）" % (orders, combos))
    for t in PTYPES:
        for r in pays.get(t, []):
            if any(int(u) not in nums for u in str(r["組"]).split("-")) or type(r["払戻"]) is not int or r["払戻"] <= 0:
                return stop("%sの払戻 %s が不正です" % (t, r))
    complete = bool(pays.get("単勝")) and bool(pays.get("複勝"))
    rid = rec["race_id"]
    led = {"ver": RULE_VERSION, "code_k": code_sha(), "code_a": rec["code"], "code_m": rec["code_m"], "code_p": rec["code_p"], "code_a47": rec["code_a47"],
           "code_f": rec["code_f"], "code_m48": rec["code_m48"], "code_p48": rec["code_p48"],
           "mode": rec["mode"], "race_id": rid, "date": rid[:8], "venue": rec["venue"], "dist": rec["dist"], "rno": int(rid[-2:]), "heads": rec["heads"],
           "nums": nums, "orders": orders, "pays": {t: [{"組": r["組"] if t in ("単勝", "複勝") else norm_key(r["組"]), "払戻": r["払戻"]} for r in pays.get(t, [])] for t in PTYPES},
           "combos": combos, "pays_complete": complete, "source": res.get("source"), "qual": rec.get("qual"),
           "excl": None if rec["mode"] == "通常" else "新馬モード（評価の対象外）", "warnings": rec.get("warnings", []),
           "pop": res.get("pop"), "finish": res.get("finish")}
    print("【考察 %s】レースID=%s %s %sm %d頭 モード=%s" % (RULE_VERSION, rid, rec["venue"], rec["dist"], rec["heads"], rec["mode"]))
    print("結果: 着順 %s ／ 三連複 %s ／ 払戻の入力元=%s%s" % (" , ".join("-".join(map(str, o)) for o in orders), " , ".join(combos), res.get("source"),
                                                       "" if complete else "（単勝・複勝の払戻がそろっていないため、3案の回収率の集計から除く）"))
    if rec["mode"] == "通常":
        l49 = lnP49(rec["s"], rec["a1"], rec["a2"], nums, combos)
        l48 = lnP48(rec["p48"], rec["g48"], nums, combos)
        pr = plan_results(rec["plans"], pays)
        led.update({"s": rec["s"], "a1": rec["a1"], "a2": rec["a2"], "q1": rec["q1"], "p48": rec["p48"], "g48": rec["g48"],
                    "lnP49": round(l49, 6), "lnP48": round(l48, 6), "d48": round(l49 - l48, 6), "plans": pr})
        print("1. モデルの判定の値: ln P_v4.9=%+.4f ／ ln P_v4.8=%+.4f ／ Δ=%+.4f" % (l49, l48, l49 - l48))
        print("2. 3案の仮想購入（各100円）:")
        for name, v in pr.items():
            print("   %s: %d点 %s 払戻%d円（仮想）／ 見込みの当たり %.3f%s" % (name, v["n"], "的中" if v["hit"] else ("見送り" if not v["n"] else "不的中"), v["ret"], v["exp"],
                                                                 "".join(" ／ %s %s 実際%d円・見積もり%d円" % (h["t"], h["k"], h["pay"], round(h["est"])) for h in v["hits"])))
        q = rec.get("qual") or {}
        print("3. 品質: 取消・除外=%s頭 ／ 頭数表記=%s・抽出=%s ／ 1角位置の取れない馬=%s頭 ／ 特徴量の欠測率=%s ／ 全馬の人気=%s" %
              (q.get("scratched"), q.get("heads_hdr"), q.get("heads_parsed"), q.get("fm_missing"), q.get("feat_missing"), "あり" if res.get("pop") else "なし"))
    else:
        print("新馬モード: 評価の対象外（判定に入れない）")
    if rec.get("warnings"):
        print("分析時の警告: " + " / ".join(rec["warnings"]))
    print("LEDGER行(下の1行を集計用に保存):")
    print("LEDGER " + json.dumps(led, ensure_ascii=False, separators=(",", ":")))
    return 0


def validate_ledger(x):
    if x.get("ver") != RULE_VERSION:
        raise ValueError("版が違います(%s)。旧版の行は混ぜられません" % x.get("ver"))
    if x.get("code_k") != code_sha():
        raise ValueError("考察側の指紋(%s)が本ファイルと一致しません" % x.get("code_k"))
    if (x.get("code_m"), x.get("code_p"), x.get("code_m48"), x.get("code_p48")) != (M.code_sha(), PAR["_sha"], M48.code_sha(), PAR48["_sha"]):
        raise ValueError("v49_model・係数・v48_model・v4.8の係数の指紋が違います")
    if x["date"] != x["race_id"][:8] or x["rno"] != int(x["race_id"][-2:]):
        raise ValueError("レースIDと日付・R番号が一致しません")
    if x["mode"] == "新馬":
        return
    if x["a1"] != PAR["order"]["a1"] or x["a2"] != PAR["order"]["a2"]:
        raise ValueError("着順の係数が係数ファイルと違います")
    nums, combos = x["nums"], x["combos"]
    if abs(lnP49(x["s"], x["a1"], x["a2"], nums, combos) - x["lnP49"]) > 2e-6 or abs(lnP48(x["p48"], x["g48"], nums, combos) - x["lnP48"]) > 2e-6:
        raise ValueError("ln P が確率からの再計算と合いません")
    if abs(x["lnP49"] - x["lnP48"] - x["d48"]) > 3e-6:
        raise ValueError("Δ が対数スコアと合いません")
    pk = {t: {r["組"] if t in ("単勝", "複勝") else norm_key(r["組"]): r["払戻"] for r in x["pays"][t]} for t in M.TYPES}
    for name, v in x["plans"].items():
        ret = sum(pk[t].get(k, 0) for t, k, _, _ in v["tickets"])
        if v["n"] != len(v["tickets"]) or v["stake"] != 100 * v["n"] or v["ret"] != ret or v["hit"] != (ret > 0):
            raise ValueError("%s の点数・払戻が結果と合いません" % name)


def read_ledger(path):
    L, study, stops = [], {}, 0
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if line.startswith("LEDGER "):
            try:
                x = json.loads(line[7:])
                validate_ledger(x)
            except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError) as e:
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
        raise ValueError("分析側の指紋が混在しています: " + ",".join(sorted({x["code_a"] for x in L})))
    return L, study, stops


def _boot(stat, n, seed, B=BOOT_B):
    rng = random.Random(seed)
    vals = sorted(stat([rng.randrange(n) for _ in range(n)]) for _ in range(B))
    return vals[int(round(0.025 * B))], vals[int(round(0.975 * B)) - 1]


def _tbl(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(out)


def is_design(x):
    return x["race_id"] in EXCLUDE_IDS


def aggregate(path):
    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    try:
        L, study, stops = read_ledger(path)
    except (ValueError, OSError) as e:
        print("【停止】" + str(e))
        return 1
    test = bool(study.get("test_include_design"))
    judge_n = int(study.get("test_judge_n") or JUDGE_N)
    if judge_n != JUDGE_N:
        test = True
    print("分析側の指紋=%s ／ v49_model=%s ／ 係数=%s ／ v48_model=%s ／ v4.8の係数=%s ／ 版=%s（運用メモの正本表と照合すること）" %
          (L[0]["code_a"], L[0]["code_m"], L[0]["code_p"], L[0]["code_m48"], L[0]["code_p48"], RULE_VERSION))
    if test:
        print("")
        print("**【テスト用】STUDY行の test_include_design・test_judge_n により、検証に使わないレースを含める、または判定の件数を変えています（%dレース）。判定には使えません。**" % judge_n)
    start = study.get("start")
    if not start:
        print("注意: STUDY行（開始日）がありません。開始日による絞り込みは行いません。運用メモに記録した開始日・対象の場と照合してください。")
    design = [] if study.get("test_include_design") else [x for x in L if is_design(x)]
    dset = {x["race_id"] for x in design}
    before = [x for x in L if x["race_id"] not in dset and start and x["date"] < start]
    bset = {x["race_id"] for x in before}
    debut = [x for x in L if x["mode"] == "新馬" and x["race_id"] not in dset and x["race_id"] not in bset]
    elig = sorted([x for x in L if x["mode"] == "通常" and x["race_id"] not in dset and x["race_id"] not in bset], key=lambda x: x["race_id"])
    n = len(elig)
    pc = [x for x in elig if x["pays_complete"]]
    nb = sum(x["plans"]["案B"]["n"] for x in pc)
    print("")
    print("**【件数と品質】**（判定の値は、対象が%dレースに達するまで計算も表示もしない）" % judge_n)
    print("")
    qs = [x.get("qual") or {} for x in elig]
    venues = {}
    for x in elig:
        venues[x["venue"]] = venues.get(x["venue"], 0) + 1
    rows = [["LEDGER行（全体）", len(L)], ["検証に使わない（設計に使ったレースなど）", len(design)], ["検証に使わない（開始日より前）", len(before)],
            ["新馬モード（評価の対象外）", len(debut)], ["対象の通常モードのレース", n],
            ["　うち単勝・複勝の払戻がそろったレース（3案の集計に使う）", len(pc)],
            ["　うち手入力の結果", sum(1 for x in elig if x.get("source") != "結果ページ")],
            ["　うち全馬の人気がないレース", sum(1 for x in elig if not x.get("pop"))],
            ["案Bの点数（払戻がそろったレース）", nb],
            ["取消・除外のあるレース（頭数計）", "%d（%d頭）" % (sum(1 for q in qs if q.get("scratched")), sum(q.get("scratched") or 0 for q in qs))],
            ["頭数表記と抽出頭数が違うレース", sum(1 for q in qs if q.get("heads_hdr") and q.get("heads_hdr") != q.get("heads_parsed"))],
            ["1角位置の取れない馬のあるレース", sum(1 for q in qs if q.get("fm_missing"))],
            ["特徴量の欠測率（レース平均。体重を除く）", "%.2f%%" % (100 * sum(q.get("feat_missing") or 0 for q in qs) / n) if n else "-"],
            ["停止の件数（STOP行）", stops],
            ["開催日の範囲", "%s〜%s" % (elig[0]["date"], elig[-1]["date"]) if n else "-"],
            ["場別の件数", " ／ ".join("%s=%d" % (k, v) for k, v in sorted(venues.items())) or "-"]]
    print(_tbl(["項目", "値"], rows))
    print("")
    # ---- モデルの判定
    if n < judge_n:
        print("対象は%dレース。判定には%dレース必要です（あと%dレース）。判定の途中経過は出しません。" % (n, judge_n, judge_n - n))
        return 0
    J = elig
    nj = len(J)
    d = [x["d48"] for x in J]
    m = sum(d) / nj
    lo, hi = _boot(lambda idx: sum(d[i] for i in idx) / nj, nj, SEED_MODEL)
    print("**【モデルの判定】**判定の時点で揃っている対象の通常モードのレース全部（%dレース。最初=%s、最後=%s）を使う。%dレースちょうどには切らない。" %
          (nj, J[0]["race_id"], J[-1]["race_id"], judge_n))
    print("")
    print("Δ_r = ln P_v4.9(実際の三連複の組) − ln P_v4.8(同じ組)（同着は各組のPの合計）")
    print("")
    print("Δの平均=%+.5f／95%%区間（レース単位の対ブートストラップ%d回・乱数シード%d）=[%+.5f, %+.5f]／下限>0=%s" % (m, BOOT_B, SEED_MODEL, lo, hi, "はい" if lo > 0 else "いいえ"))
    print("")
    print("**判定: %s**" % ("効果あり（v4.9 は v4.8 より当たりやすい）" if lo > 0 else "効果を確認できず"))
    print("")
    byv = {}
    for x in J:
        byv.setdefault(x["venue"], []).append(x["d48"])
    print("参考（記録のみ）: 平均 ln P（v4.9 ／ v4.8）= %.4f ／ %.4f ／ 場別のΔ: %s" % (sum(x["lnP49"] for x in J) / nj, sum(x["lnP48"] for x in J) / nj,
                                                                       " ／ ".join("%s %+.4f（%d）" % (k, sum(v) / len(v), len(v)) for k, v in sorted(byv.items()))))
    print("")
    # ---- 買い方の判定
    JB = pc
    if not JB:
        print("買い方の判定: 単勝・複勝の払戻がそろったレースがありません。")
        return 0
    print("**【買い方の判定】**判定の時点で揃っている対象レースのうち、単勝・複勝の払戻がそろったレース全部（%dレース。案Bの点数%d点。最初=%s、最後=%s）を使う。実際の馬券は買わない。" %
          (len(JB), nb, JB[0]["race_id"], JB[-1]["race_id"]))
    print("")
    rows_b, verdict = [], None
    for name, _, _ in M.PLANS:
        per = [(x["plans"][name]["stake"], x["plans"][name]["ret"]) for x in JB]
        st = sum(a for a, _ in per)
        rt = sum(b for _, b in per)
        nbuy = sum(1 for a, _ in per if a)
        hits = sorted((h["pay"] for x in JB for h in x["plans"][name]["hits"]), reverse=True)
        exp = sum(x["plans"][name]["exp"] for x in JB)
        ratios = sorted(h["pay"] / h["est"] for x in JB for h in x["plans"][name]["hits"])
        if st:
            lo_, hi_ = _boot(lambda idx: (sum(per[i][1] for i in idx) / max(1, sum(per[i][0] for i in idx))), len(per), SEED_PLAN[name])
        rows_b.append([name + ("（判定）" if name == "案B" else "（記録）"), "%d／%d" % (nbuy, len(JB)), st // 100, st, rt, "%.1f%%" % (100.0 * rt / st) if st else "-",
                       "[%.1f%%, %.1f%%]" % (100 * lo_, 100 * hi_) if st else "-", len(hits), "%.1f" % exp,
                       "%.1f%%" % (100.0 * (rt - sum(hits[:1])) / st) if st else "-", "%.2f" % ratios[len(ratios) // 2] if ratios else "-"])
        if name == "案B":
            verdict = st and lo_ > 1.0
    print(_tbl(["案", "買ったレース", "点数", "投資（仮想）", "払戻（仮想）", "回収率", "95%区間", "的中の本数", "見込みの当たり", "最大1本を除く", "払戻の比（中央値）"], rows_b))
    print("")
    print("**判定（案B）: %s**" % ("回収率100%超えを確認（95%区間の下限が100%を超えた）" if verdict else "回収率100%超えを確認できず"))
    print("")
    sm = [x for x in JB if x["heads"] <= 7]
    lg = [x for x in JB if x["heads"] >= 8]

    def rr(xs):
        st = sum(x["plans"]["案B"]["stake"] for x in xs)
        return "%d点・%.1f%%" % (st // 100, 100.0 * sum(x["plans"]["案B"]["ret"] for x in xs) / st) if st else "0点"
    print("参考（記録のみ）: 案Bの頭数別 7頭以下 %s ／ 8頭以上 %s" % (rr(sm), rr(lg)))
    return 0


def main():
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "kosatsu":
        return kosatsu(a[1], a[2])
    if len(a) >= 2 and a[0] == "aggregate":
        return aggregate(a[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
