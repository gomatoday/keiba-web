# -*- coding: utf-8 -*-
"""
分析計算v4.7.py  南関東 三連複 買い目算出（オッズ不使用・条件付きロジット）
使い方（Haikuはこの3コマンドを実行して出力をそのまま貼るだけ）
  1) python 分析計算v4.7.py predict  <出走表.html> [会場+R番号 例: 浦和12R]
  2) python 分析計算v4.7.py result   '<予想レコードJSON または ファイルパス>' "<race_id> / 1-2-3 500"
  3) python 分析計算v4.7.py aggregate <LEDGER行を集めたファイル>
v4.7: (1)逃げ補正は一律+0.9（SETTINGS["nige_boost"]。展開区分による変更なし）。勝率=softmax(能力計＋逃げ補正)、β=1・g=0.8固定。(2)選定: 展開区分と配分表を廃止。補正後の能力計u（小数3桁）の順位が10位以下、または補正後の3着内確率（全頭の確率から計算）が10%以下の馬を除き、残った馬の3頭の組だけを、全頭の三連複確率（選定馬で作り直さない）の高い順に並べて、連続上位1〜20位を仮想購入する（同確率は馬番昇順の辞書順）。残った組が20通り以下なら全買い。(3)比較用の記録ref45は補正なし(u=能力計)で同じ手順。ref40・refw・ref43は廃止。(4)品質: 取消・除外の馬を明示的に除き（欠けた馬番を記録）、近走欄の最新日がレース日より前であることを確認（違反は停止）、能力試験の走は競走として数えない。判定は新しい通常モード300レースのΔ（考察計算v4.7.pyのaggregate）。
v4.6: (1)逃げ補正: 脚質が逃げの馬の能力ユーティリティ（ロジット）に、展開区分別の値（スロー+1.7／ミドル+0.7／ハイ+0.4。SETTINGS["nige_boost"]）を加えて勝率を作る。他の脚質は補正なし。展開区分は全出走馬の逃げの頭数で決める（v4.5と同じ）。切り捨ての順位・配分表の選定は能力計（補正前）の順位で行い、3着内確率は補正後の勝率から作る。(2)購入帯: 実購入は連続上位1〜20位（BUY_CFG。各100円・最大20点。v4.5は原順位1〜5位＋16〜20位）。(3)比較用の記録ref45: v4.5方式（逃げ補正なし）の勝率・選定・上位20点をRECに残す（買い目には使わない）。それ以外（脚質の定義・展開区分の境界・切り捨て・配分表・近走の重み・g・能力差倍率・配点・新馬モード）はv4.5と同じ。
v4.5: 脚質の「逃げ」を、最大前5走のうち1角位置割合0.20以下の走の割合（逃げ確率np）が0.5以上の馬とする（SETTINGS["nige_np_min"]）。
v4.4: 近走の重みなし（前5走を同じ重み0.2）／脚質は最大前5走の平均／展開区分は逃げ馬の頭数／能力計10位以下と3着内確率10%以下の切り捨て／配分表による選定（合計8頭）／比較用の記録ref43・refw。
v4.3: 馬体重増減を能力スコアから外す（配点wt=0。生値は観察用に記録）。
v4.2: 脚質補正（会場脚質補正・逃げ数補正）を勝率に使わない（SETTINGS["style_adjust"]=False）。補正あり（v4.0方式）はREC行のref40へ対比用に記録。
v4.0: 買い目を展開区分ごとの選定馬だけから作る（検証計画P1）。v3.0: ヘンリー型（g=0.8）。
resultは考察計算v4.7.pyの厳密照合を実行し、RECでなくLEDGERを出力する。
重み・補正値はすべて本ファイル冒頭の SETTINGS / 表に集約。同じ場所に「設定.json」があれば上書き。
"""
import sys, re, json, math, os, random, itertools, hashlib

try:
    from bs4 import BeautifulSoup
except Exception:
    print("エラー: beautifulsoup4 が必要です (pip install beautifulsoup4 lxml --break-system-packages)")
    sys.exit(1)

VERSION = "v4.7"

# ============================================================
# 設定（初期値＝仮置き。バックテストで学習・更新する）
# ============================================================
SETTINGS = {
    "scale": 1.0,                 # 配点→ロジット変換の能力差倍率（仮置き。能力ユーティリティにだけ掛かり、脚質補正には掛からない）
    # 配点（v4.3: 体重を0にしたため合計90）。ロジット係数 = 配点/100*scale
    "points": {
        "ord": 18,      # 近走 着順
        "margin": 14,   # 近走 着差（秒÷距離）
        "pos": 8,       # 近走 位置変化（最終通過順→着順）
        "l3f": 15,      # 末脚（上がり3F順位）
        "apt": 14,      # 適性（距離別・場別の3着内率）
        "time": 6,      # 持時計（今回距離）
        "jky": 15,      # 騎手（コース相性＋この騎手での成績）
        "wt": 0,        # v4.3: 馬体重増減は予想に使わない。生値と増減は観察用に記録だけ残す
    },
    "recency": [0.2, 0.2, 0.2, 0.2, 0.2],        # 前走→5走前の重み（同じ重み）
    "shrink_prior_top3": 0.25, "shrink_k_top3": 3,
    "shrink_prior_jky": 0.08, "shrink_k_jky": 20,
    "style_discount": 0.5,        # 会場×距離×脚質 補正の割引（交絡対策。v4.0方式の参考値用）
    "style_floor": -2.5,
    "style_zero_rate": 0.5,       # 勝率0%のときに置き換える値(%)
    "wobble_k": 3.0,              # 脚質のブレによる補正縮小: 1/(1+k*std)
    "nige_np_min": 0.5,           # 逃げ確率（最大前5走のうち1角位置割合0.20以下の走の割合）がこれ以上の馬を脚質「逃げ」とする
    "style_adjust": False,        # v4.0方式の全脚質補正を勝率に使うか。False=使わない（補正あり＝v4.0方式は対比用にref40へ記録）
    "nige_boost": 0.9,            # v4.7: 脚質が逃げの馬の能力ユーティリティに加える値（一律。展開区分による変更なし。検証期間中は変えない）
    "g": 0.8,                     # ヘンリー型の冪(g)。1着は勝率p、2・3着の段はw=p^gを正規化。g=1.0がHarville式
    # v4.7の切り捨て（配分表・展開区分は廃止）。補正後の能力計(u)の順位がcut_rankより下（10位以下）、または補正後の3着内確率(全頭)がcut_p3以下（10%以下）の馬を除く。検証期間中は変えない。
    "p1": {"cut_rank": 9, "cut_p3": 0.10},
    "top_n": 20,                  # 毎回20点。組合せが20通り未満なら全組合せ
    # 新馬モード（全頭が初出走のレースだけ）。配点・倍率は仮置き
    "debut": {"scale": 1.5, "points": {"trial": 30, "debut": 25, "jkcourse": 15, "sire": 20, "jktr": 5}},
    "eval_points": [5, 10, 15, 20],
}

# 会場×距離×脚質の勝率(%)  [逃げ, 先行, 差し, 追込]  出典: 競馬予想サイト解体新書（母数不明・仮置き）
STYLE_TABLE = {
    "浦和": {800: [68.7, 13.8, 1.0, 0.0], 1300: [44.1, 14.8, 4.0, 2.2], 1400: [28.3, 10.4, 5.5, 1.3],
             1500: [25.2, 11.8, 5.5, 1.8], 2000: [18.5, 17.8, 3.2, 0.0]},
    "船橋": {1000: [34.0, 13.0, 7.0, 1.0], 1200: [24.0, 12.0, 6.0, 1.0], 1500: [28.0, 13.0, 3.0, 2.0],
             1600: [29.0, 10.0, 6.0, 2.0], 1700: [24.0, 17.0, 5.0, 2.0], 1800: [29.0, 10.0, 6.0, 2.0],
             2200: [35.0, 10.0, 5.0, 0.0], 2400: [40.0, 50.0, 10.0, 0.0]},
    "大井": {1000: [36.5, 12.5, 5.0, 0.6], 1200: [23.9, 10.1, 3.7, 1.3], 1400: [19.9, 10.7, 5.3, 2.0],
             1500: [19.8, 10.5, 5.5, 2.3], 1600: [20.5, 11.1, 5.1, 2.0], 1650: [0.0, 17.0, 7.0, 0.0],
             1700: [12.8, 12.5, 7.6, 0.7], 1800: [11.1, 12.7, 6.0, 2.8], 2000: [6.4, 9.5, 7.3, 7.1],
             2400: [20.0, 10.7, 4.4, 0.0], 2600: [0.0, 16.7, 5.6, 0.0]},
    "川崎": {900: [31.1, 10.6, 10.5, 3.4], 1400: [28.3, 11.5, 5.9, 2.0], 1500: [22.6, 11.5, 5.5, 1.9],
             1600: [20.3, 11.7, 5.9, 1.8], 2000: [26.5, 10.8, 14.6, 1.9], 2100: [13.6, 10.7, 7.5, 2.1]},
}
JRA_BASE = [16.0, 12.5, 5.7, 2.2]   # 会場表が引けない時の最終フォールバック

# 逃げ馬数(期待値)別の補正（ロジット加算値）[逃げ, 先行, 差し, 追込]。単騎=0。仮置き。
FRONT_TABLE = {0: [-0.28, -0.10, 0.08, 0.14], 1: [0, 0, 0, 0],
               2: [-0.30, -0.03, 0.09, 0.12], 3: [-0.48, -0.09, 0.14, 0.20]}

STYLES = ["逃げ", "先行", "差し", "追込"]
VENUES = ["浦和", "船橋", "大井", "川崎"]
VENUE_CH = {"浦": "浦和", "船": "船橋", "大": "大井", "川": "川崎"}


def load_settings():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "設定.json")
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(SETTINGS.get(k), dict):
                    SETTINGS[k].update(v)
                else:
                    SETTINGS[k] = v
        except Exception as e:
            print("警告: 設定.json を読めないため既定値を使用:", e)

# ============================================================
# 共通ユーティリティ
# ============================================================

def num(s, default=None):
    try:
        return float(s)
    except Exception:
        return default


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def z_scores(vals):
    """None は平均扱い(=0)。分散0なら全0。"""
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0] * len(vals)
    m = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    if sd < 1e-9:
        return [0.0] * len(vals)
    return [0.0 if v is None else (v - m) / sd for v in vals]


def shrunk_rate(k, n, prior, kk):
    return (k + prior * kk) / (n + kk)

# ============================================================
# HTML 抽出
# ============================================================

def decode_html(b):
    """v4.7修正(2026-11-08): HTMLの文字コードを判定して読む。UTF-8として厳密に読めればUTF-8、読めなければ
    metaのcharset、最後にShift_JIS(cp932)。どれでも厳密に読めないときはNone（呼び出し側で停止する）。読めない文字を捨てない。"""
    m = re.search(rb'charset\s*=\s*["\']?([A-Za-z0-9_\-]+)', b[:8192], re.I)
    cs = m.group(1).decode("ascii").lower().replace("_", "-") if m else ""
    meta = {"shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932", "windows-31j": "cp932", "cp932": "cp932", "ms932": "cp932",
            "euc-jp": "euc_jp"}.get(cs)
    for enc in ["utf-8"] + ([meta] if meta else []) + ["cp932"]:
        try:
            return b.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return None, None


def make_soup(path):
    s, enc = decode_html(open(path, "rb").read())
    if s is None:
        print("エラー: HTMLの文字コードを判定できません（UTF-8・Shift_JISのどちらでも読めません）。HTMLを確認してください。")
        sys.exit(1)
    try:
        return BeautifulSoup(s, "lxml"), s
    except Exception:
        return BeautifulSoup(s, "html.parser"), s


def parse_header(soup, raw, warns):
    h = {"race_id": None, "venue": None, "dist": None, "course": "", "heads": None, "surface": "ダ"}
    m = re.search(r'id="_cc_proId"\s+value="(\d+)"', raw)
    if m:
        h["race_id"] = m.group(1)
    else:
        warns.append("レースIDを取得できません")
    sub = soup.select_one(".nk23_c-tab1__subtitle")
    txt = clean(sub.get_text(" ")) if sub else clean(soup.get_text(" "))[:3000]
    m = re.search(r"(浦和|船橋|大井|川崎)競馬", txt) or re.search(r"(浦和|船橋|大井|川崎)競馬", raw)
    if m:
        h["venue"] = m.group(1)
    else:
        warns.append("会場を判定できません")
    m = re.search(r"(ダ|芝)\s*([\d,]{3,5})\s*m\s*(（[^）]*）)?", txt)
    if m:
        h["surface"] = m.group(1)
        h["dist"] = int(m.group(2).replace(",", ""))
        h["course"] = (m.group(3) or "").strip("（）")
    else:
        warns.append("距離を判定できません")
    m = re.search(r"（(\d+)頭）", txt)
    if m:
        h["heads"] = int(m.group(1))
    return h


def parse_label_row(th_text):
    """'1800 1900 2000 2100 浦2000' → [(None,1800),...,('浦和',2000)]"""
    out = []
    for m in re.finditer(r"([浦船大川])?(\d{3,4})", th_text or ""):
        out.append((VENUE_CH.get(m.group(1)) if m.group(1) else None, int(m.group(2))))
    return out


def ptexts(td):
    return [clean(p.get_text(" ")) for p in td.find_all("p")] if td else []


def counts_from_p(p):
    """<p><span>1</span><span>2</span>..</p> → [1着,2着,3着,着外]"""
    sp = [clean(x.get_text()) for x in p.find_all("span")]
    v = [int(x) for x in sp if re.fullmatch(r"\d+", x)]
    return v if len(v) == 4 else None


def parse_past_run(td):
    """過去走セル → dict。読めない項目はNone。"""
    if td is None:
        return None
    txt = clean(td.get_text(" "))
    if not txt or txt in ("--", "-"):
        return None
    r = {"finish": None, "n": None, "dist": None, "margin": None, "l3f_rank": None, "pos": [], "date": None}
    inp = td.select_one('input[id^="rcd_"]')
    if inp is not None and re.fullmatch(r"\d{8}", clean(inp.get("value", ""))):
        r["date"] = clean(inp.get("value"))
    else:
        for a_ in td.select('a[href*="/result/"]'):
            m_ = re.search(r"/result/(\d{8})", a_.get("href", ""))
            if m_:
                r["date"] = m_.group(1)
                break
    if "能試" in txt:
        return None                      # v4.7: 能力試験の走は競走として数えない（脚質・逃げ確率・近走特徴量の分母・分子に入れない）
    s19 = td.select_one("span.nk23_u-text19")
    ft = clean(s19.get_text()) if s19 else ""
    m = re.match(r"(\d+)", ft)
    r["finish"] = int(m.group(1)) if m else None      # 中止・除外等はNone(最下位扱いは後段)
    r["abnormal"] = (r["finish"] is None)
    pop = td.select_one("span.popularity")
    if pop:
        m = re.search(r"(\d+)頭", clean(pop.get_text()))
        if m:
            r["n"] = int(m.group(1))
    # 距離: 'ダ 2000' 形式の最後の4桁数字
    for sp in td.select("span.nk23_u-text10"):
        t = clean(sp.get_text())
        m = re.search(r"[芝ダ障]\s*(\d{3,4})\s*$", t)
        if m:
            r["dist"] = int(m.group(1))
            break
    rt = td.select_one("span.racetime")
    if rt:
        m = re.search(r"\(\s*(-?[\d.]+)\s*\)", clean(rt.get_text()))
        if m:
            r["margin"] = float(m.group(1))
    ft3 = td.select_one("span.furlongtime")
    if ft3:
        m = re.search(r"\(\s*(\d+)\s*\)", clean(ft3.get_text()))
        if m:
            r["l3f_rank"] = int(m.group(1))
    po = td.select_one("p.position")
    if po:
        r["pos"] = [int(x) for x in re.findall(r"\d+", clean(po.get_text(" ")))]
    return r


def parse_horses(soup, hdr, warns):
    tables = soup.select("table.tb-shousai")
    if not tables:
        warns.append("出走表テーブル(tb-shousai)が見つかりません")
        return []
    rows = [r for r in tables[0].select("tr") if r.select_one("td.umaban")]
    # 列ラベル（距離別／場別の行見出し）
    def hl(cls):
        th = tables[0].select_one("th." + cls + ".nk23_u-right") or tables[0].select_one("th." + cls + " ")
        for t in tables[0].select("th." + cls):
            tx = clean(t.get_text(" "))
            if re.search(r"\d{3,4}", tx):
                return parse_label_row(tx)
        return []
    lab_ord1 = hl("cs-ord1")
    lab_time = hl("cs-time")
    lab_anl = hl("cs-anl")
    lab_jkc = hl("cs-recJkc")

    def lab_index(labs):
        for pref in (True, False):
            for i, (v, d) in enumerate(labs):
                if d == hdr["dist"] and ((v == hdr["venue"]) if pref else (v is None)):
                    return i
        return None
    horses = []
    for r in rows:
        h = {"num": None, "name": "", "runs": [], "warn": []}
        ucell = re.sub(r"\s+", "", clean(r.select_one("td.umaban").get_text(" ")))
        if not ucell.isdigit():
            # v4.7: 馬番のセルが数字でない行（取消・除外）は、z得点の計算より前に出走馬から除く。何頭あったかを記録する。
            if "取消" in ucell or "除外" in ucell:
                hdr.setdefault("scratched_cells", []).append(ucell)
            else:
                warns.append("馬番を読めない行があります(%s)。出走馬から除きました" % ucell)
            continue
        try:
            h["num"] = int(clean(r.select_one("td.umaban").get_text()))
            nm = r.select_one("td.pr-umaName-textRound span.nk23_u-text16")
            h["name"] = clean(nm.get_text()) if nm else ""
            # 騎手
            g1 = r.select_one("td.cs-g1")
            a = g1.select_one("a.is-link") if g1 else None
            h["jockey"] = clean(a.get_text()) if a else ""
            # 騎手×コース相性 '5.9% 2 R 34 R'
            ai = r.select_one("td.cs-ai1")
            h["ai_rate"], h["ai_n"] = None, 0
            if ai:
                t = clean(ai.get_text(" "))
                m = re.search(r"([\d.]+)%\s*(\d+)\s*R\s*(\d+)\s*R", t)
                if m:
                    h["ai_rate"] = float(m.group(1)) / 100
                    h["ai_k"] = int(m.group(2))
                    h["ai_n"] = int(m.group(3))
            ai2 = r.select_one("td.cs-ai2")
            h["ai2"] = None
            if ai2:
                m = re.search(r"([\d.]+)%\s*(\d+)\s*R\s*(\d+)\s*R", clean(ai2.get_text(" ")))
                if m:
                    h["ai2"] = (float(m.group(1)) / 100, int(m.group(3)))
            # 馬体重・増減
            g2 = r.select_one("td.cs-g2")
            h["wt"], h["wt_diff"] = None, None
            if g2:
                t = clean(g2.get_text(" ")).replace("＋", "+").replace("－", "-").replace("−", "-").replace("±", "")
                m = re.match(r"(\d{3})\s*([+-]?\d+)?", t)
                if m:
                    h["wt"] = int(m.group(1))
                    h["wt_diff"] = int(m.group(2)) if m.group(2) is not None else 0
                    if "±0" in clean(g2.get_text(" ")) or m.group(2) is None:
                        h["wt_diff"] = 0
            if h["wt_diff"] is None:
                h["warn"].append("馬体重増減を読めず")
            # 距離別・場別 成績
            h["dist_rec"], h["venue_rec"], h["best_time"], h["jky_rec"] = None, None, None, None
            oky = r.select_one("td.mk-oky")
            if oky and lab_ord1:
                ps = oky.find_all("p")
                for i, (v, d) in enumerate(lab_ord1):
                    if i < len(ps) and v is None and d == hdr["dist"]:
                        h["dist_rec"] = counts_from_p(ps[i])
            ojo = r.select_one("td.mk-ojo")
            if ojo and hdr["venue"] in VENUES:
                ps = ojo.find_all("p")
                idx = VENUES.index(hdr["venue"])
                if idx < len(ps):
                    h["venue_rec"] = counts_from_p(ps[idx])
            btm = r.select_one("td.mk-btm")
            if btm and lab_time:
                ps = [clean(p.get_text(" ")) for p in btm.find_all("p")]
                for i, (v, d) in enumerate(lab_time):
                    if i < len(ps) and v is None and d == hdr["dist"]:
                        m = re.search(r"(\d)(\d{2})(\d)", ps[i])
                        if m:
                            h["best_time"] = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10
            kwc = r.select_one("td.mk-kwc")
            if kwc:
                ps = counts_from_p(kwc.find("p")) if kwc.find("p") else None
                if ps is None:
                    nums = [int(x) for x in re.findall(r"\d+", clean(kwc.get_text(" ")))]
                    ps = nums[:4] if len(nums) >= 4 and "初騎乗" not in clean(kwc.get_text()) else None
                h["jky_rec"] = ps
            # 過去5走
            for k in range(1, 6):
                h["runs"].append(parse_past_run(r.select_one("td.mk-z%d" % k)))
            # 初出走（新馬）用の項目
            h["is_debut"] = not any(rr and rr.get("n") for rr in h["runs"])
            h["trial"] = None
            h["debut_j"], h["debut_t"] = None, None
            for k in range(1, 6):
                td = r.select_one("td.mk-z%d" % k)
                tx = clean(td.get_text(" ")) if td else ""
                if h["trial"] is None:
                    m = re.search(r"能試\s+(\S+?)(\d{2}\.\d{1,2}\.\d{1,2})\s+(\d+)\s+(\d+)レース\s+(\d+)kg\s+([\d.]+)", tx)
                    if m:
                        h["trial"] = {"date": m.group(2), "dist": int(m.group(3)), "kg": int(m.group(5)), "time": float(m.group(6))}
                m = re.search(r"初出走時勝率\s*騎手\s*([\d.]+)\s*調教師\s*([\d.]+)", tx)
                if m:
                    h["debut_j"], h["debut_t"] = float(m.group(1)), float(m.group(2))
            h["sire_rate"], h["jkc_rate"] = None, None
            for cls, labs, key in (("td.mk-sire", lab_anl, "sire_rate"), ("td.mk-kco", lab_jkc, "jkc_rate")):
                td = r.select_one(cls)
                ii = lab_index(labs) if len(labs) == 5 else None
                if td is not None and ii is not None:
                    vals = re.findall(r"([\d.]+)%", clean(td.get_text(" ")))
                    if len(vals) == 10:
                        h[key] = float(vals[5 + ii]) / 100.0     # 連対率
        except Exception as e:
            h["warn"].append("抽出で例外: %s" % e)
        if h["num"] is not None:
            horses.append(h)
    return horses

# ============================================================
# 特徴量
# ============================================================

def run_features(h, hdr, w_all=None):
    """近走の4特徴（着順・着差・位置変化・末脚）を近走加重平均で返す。
    第3戻り値に、使った走数(nr)と、使った最後の欄までに飛ばした欄の数(sk)を返す（重みは欄の位置で当てているため、飛ばした欄があると重みがずれる。記録のみ）。"""
    if w_all is None:
        w_all = SETTINGS["recency"]
    acc = {"ord": [], "margin": [], "pos": [], "l3f": []}
    first_ratio = []
    used_idx = []
    for i, r in enumerate(h["runs"]):
        if not r or not r.get("n") or r["n"] < 2:
            continue
        used_idx.append(i)
        n = r["n"]
        w = w_all[i] if i < len(w_all) else 0.1
        if r["finish"] is not None:         # 着順が読めない走(中止・除外等)は着順の特徴量から除く(v4.7確定)
            ordn = (r["finish"] - 1) / (n - 1)
            acc["ord"].append((w, 0.5 - ordn))
        if r["margin"] is not None and r["dist"] and r["finish"] is not None:
            m = min(abs(r["margin"]), 3.0) / r["dist"] * 1000
            signed = -m if r["finish"] == 1 else m     # 1着の値は2着との差(勝ち)なので符号反転
            acc["margin"].append((w, -signed))
        if r["pos"] and r["finish"] is not None:
            gain = (r["pos"][-1] - r["finish"]) / (n - 1)
            acc["pos"].append((w, max(-1.0, min(1.0, gain))))
        if r["l3f_rank"] is not None:
            acc["l3f"].append((w, (n - r["l3f_rank"]) / (n - 1) - 0.5))
        if r["pos"]:
            first_ratio.append((i, r["pos"][0] / n))
    out = {}
    for k, lst in acc.items():
        if lst:
            sw = sum(w for w, _ in lst)
            val = sum(w * v for w, v in lst) / sw
            val *= min(1.0, len(lst) / 3.0)      # 出走数が少ない馬は0(中立)方向へ縮小
            out[k] = val
        else:
            out[k] = None
    nr = len(used_idx)
    sk = (used_idx[-1] + 1 - nr) if used_idx else 0
    return out, first_ratio, {"nr": nr, "sk": sk}


def classify_style(first_ratio, v43=False):
    """最大前5走（1角位置が取れた走だけ）の1角位置/頭数の単純平均 → (脚質idx or None, ブレ(標準偏差), 分類に使った平均位置割合 or None)。
    v43=True はv4.3の分類（前走欄・2走前欄だけ。どちらも取れなければ取れた最初の1走）。比較用の記録ref43で使う。"""
    if not first_ratio:
        return None, 0.0, None
    if v43:
        recent = [v for (i, v) in first_ratio if i < 2]
        if not recent:
            recent = [first_ratio[0][1]]
    else:
        recent = [v for (i, v) in first_ratio if i < 5]
    m = sum(recent) / len(recent)
    allv = [v for (_, v) in first_ratio]
    if len(allv) >= 2:
        mu = sum(allv) / len(allv)
        sd = math.sqrt(sum((x - mu) ** 2 for x in allv) / len(allv))
    else:
        sd = 0.0
    if m <= 0.20:
        s = 0
    elif m <= 0.40:
        s = 1
    elif m <= 0.70:
        s = 2
    else:
        s = 3
    return s, sd, m


def nige_prob(first_ratio, v43=False):
    """逃げ確率（1角位置割合0.20以下の走の割合）。最大前5走、v43=Trueは前2欄（比較用ref43と、観察用の逃げ期待数）。"""
    rec = [v for (i, v) in first_ratio if i < (2 if v43 else 5)]
    if not rec:
        return 0.10
    return sum(1 for v in rec if v <= 0.20) / len(rec)


def style_row(venue, dist, warns):
    tbl = STYLE_TABLE.get(venue)
    if not tbl:
        warns.append("脚質表に会場なし→JRA基準を使用")
        return JRA_BASE, "JRA"
    if dist in tbl:
        return tbl[dist], "%s%d" % (venue, dist)
    near = min(tbl.keys(), key=lambda d: (abs(d - dist), d))
    warns.append("脚質表に%s%dmなし→同会場の最近距離%dmの値を使用" % (venue, dist, near))
    return tbl[near], "%s%d(代替)" % (venue, near)


def style_adjust_vector(row, ):
    zr = SETTINGS["style_zero_rate"]
    base = max(row[1], zr)
    out = []
    for r in row:
        r = max(r, zr)
        v = math.log(r / base) * SETTINGS["style_discount"]
        out.append(max(v, SETTINGS["style_floor"]))
    return out


def front_adjust(expected):
    e = max(0.0, min(3.0, expected))
    lo = int(math.floor(e))
    hi = min(3, lo + 1)
    f = e - lo
    return [FRONT_TABLE[lo][j] * (1 - f) + FRONT_TABLE[hi][j] * f for j in range(4)]

# ============================================================
# 条件付きロジット + ヘンリー型（g乗）
# ============================================================

def softmax(us):
    m = max(us)
    ex = [math.exp(u - m) for u in us]
    s = sum(ex)
    return [e / s for e in ex]


def trio_probs(p, g=1.0):
    """p: 馬番順の勝率。全C(n,3)組の三連複確率（ヘンリー型）。
    1着の段は p（合計1に正規化）、2着・3着の段は w=p^g を使い、残りの馬の w の和で割る。g=1.0 はHarville式と同じ。"""
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


def code_sha():
    return hashlib.sha256(re.sub(r"\s+", "", open(os.path.abspath(__file__), encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]  # 空白・改行の違いは無視


def _gen_marks(A, B, C):
    out = set()
    for a in A:
        for b in B:
            for c in C:
                if a != b and a != c and b != c:
                    out.add(frozenset((a, b, c)))
    return out


def _mark_candidates(S):
    """Sの中だけを作るフォーメーション（1頭目・2頭目・3頭目）を、種から列を広げて列挙する。"""
    horses = sorted(set(h for t in S for h in t))
    seen, vis, stack = {}, set(), []
    for t in sorted(S, key=sorted):  # 修正(2026-11-08): 集合の並び順（環境で変わる）に依存しないよう、馬番順に処理する
        for a, b, c in itertools.permutations(sorted(t)):
            stack.append(((a,), (b,), (c,)))
    while stack:
        st = stack.pop()
        key = tuple(sorted((tuple(sorted(x)) for x in st), key=lambda x: (len(x), x)))
        if key in vis:
            continue
        vis.add(key)
        g = _gen_marks(*key)
        if not g or not g <= S:
            continue
        cs = frozenset(g)
        cost = sum(len(x) for x in key)
        if cs not in seen or (cost, key) < seen[cs]:  # 修正(2026-11-08): 塗る数が同じなら、列の馬番の並びが小さい塗り方
            seen[cs] = (cost, key)
        for col in range(3):
            for h in horses:
                if h in key[col]:
                    continue
                ns = list(key)
                ns[col] = tuple(sorted(key[col] + (h,)))
                stack.append(tuple(ns))
    return seen


def solve_marks(S):
    """買い目集合Sを、重複なく過不足なく、最少の口数（同数なら塗る数が最少）で塗り分ける。"""
    seen = _mark_candidates(S)
    cands = sorted(seen, key=lambda c: (-len(c), sorted(sorted(t) for t in c)))  # 修正(2026-11-08): 同じ大きさの候補の並びを固定する
    best = [None]

    def dfs(unc, chosen):
        if not unc:
            cost = sum(seen[c][0] for c in chosen)
            if best[0] is None or (len(chosen), cost) < (len(best[0][0]), best[0][1]):
                best[0] = (list(chosen), cost)
            return
        if best[0] is not None and len(chosen) + 1 > len(best[0][0]):
            return
        e = min(unc, key=lambda t: sorted(t))
        for cs in [c for c in cands if e in c and c <= unc]:
            chosen.append(cs)
            dfs(unc - cs, chosen)
            chosen.pop()
    dfs(frozenset(S), [])
    ents = [(seen[c][1], c) for c in best[0][0]]
    ents.sort(key=lambda e: (-len(e[1]), e[0]))
    return [{"a": list(k[0]), "b": list(k[1]), "c": list(k[2]), "n": len(cs)} for k, cs in ents]


BUY_CFG = {"rank_ranges": [[1, 20]], "unit_yen": 100, "max_points": 20}


def purchase_record(rec):
    """順位リストは保持し、実在する固定順位だけを購入する。"""
    if SETTINGS["top_n"] != 20 or SETTINGS["style_adjust"] is not False:
        raise ValueError("v4.7はtop_n=20・style_adjust=False固定です")
    buy = [dict(t, pf=t.get("pf", t["p"])) for t in rec["top"]
           if any(lo <= t["rank"] <= hi for lo, hi in BUY_CFG["rank_ranges"])]
    rec["buy_cfg"] = json.loads(json.dumps(BUY_CFG))
    rec["buy"] = buy
    rec["reference_marks"] = rec.pop("marks")
    rec["marks"] = solve_marks({frozenset(map(int, t["combo"].split("-"))) for t in buy})
    rec["buy_mass"] = round(sum(t["pf"] for t in buy), 6)
    rec["buy_points"] = len(buy)
    rec["buy_stake"] = len(buy) * BUY_CFG["unit_yen"]
    rec["buy_full_cover"] = len(buy) == math.comb(rec["heads"], 3)


def print_purchase(rec, tbl):
    print("\n**仮想購入（固定：連続上位1〜20位、存在する順位のみ・1点100円。検証期間中は記録のみで、実際の馬券は買わない）**")
    print(tbl(["原順位", "組", "全頭での確率"],
              [[t["rank"], t["combo"], "%.4f%%" % (100 * t["pf"])] for t in rec["buy"]]))
    print("仮想購入%d点／投資%d円（仮想）／全頭確率質量%.4f%%／全組購入=%s" %
          (rec["buy_points"], rec["buy_stake"], rec["buy_mass"] * 100, rec["buy_full_cover"]))
    print("**仮想購入マークシート（各行を別口、行間の組重複なし）**")
    print(tbl(["1頭目", "2頭目", "3頭目", "点数"],
              [[",".join(map(str, e[k])) for k in ("a", "b", "c")] + [e["n"]] for e in rec["marks"]]))


def build_marks(top):
    """確率上位5/10/15/20点それぞれのマークシート。"""
    out = {}
    for K in (5, 10, 15, 20):
        if K <= len(top):
            S = set(frozenset(int(x) for x in t["combo"].split("-")) for t in top[:K])
            out[str(K)] = solve_marks(S)
    return out


def print_marks(marks, tbl):
    if not marks:
        return
    print("")
    print("**参考マークシート（仮想購入ではありません）** 確率上位5/10/15/20点の比較用")
    for K, ents in marks.items():
        print("")
        print("確率上位%s点（%d通りの塗り方・合計%d点）" % (K, len(ents), sum(e["n"] for e in ents)))
        print("")
        print(tbl(["1頭目", "2頭目", "3頭目", "点数"],
                  [[",".join(map(str, e["a"])), ",".join(map(str, e["b"])), ",".join(map(str, e["c"])), e["n"]] for e in ents]))


HK_NORMAL = ["ord", "margin", "pos", "l3f", "apt", "time", "jky", "wt"]


def observe(horses, hdr):
    """観察用の事実（予想には使わない）。馬体重増減・能力試験の有無・前走からの距離差（今回-前走。+は延長）。"""
    out = []
    for h in horses:
        r0 = h["runs"][0] if h.get("runs") else None
        pd_ = r0.get("dist") if r0 else None
        dx = (hdr["dist"] - pd_) if (hdr.get("dist") and pd_) else None
        out.append({"n": h["num"], "wd": h.get("wt_diff"), "tr": 1 if h.get("trial") else 0, "dx": dx})
    return out


def select_v47(nums, u3, p3, cfg=None):
    """v4.7の切り捨て（配分表・展開区分は廃止）。nums=馬番、u3=補正後の能力計u（小数3桁。ref45では能力計ab）、p3=全頭モデルでの3着内確率。
    uの順位（高い順、同値は馬番の小さい順）がcut_rankより下、または3着内確率がcut_p3以下の馬を除く。残りが3頭未満になるときは、uの上位3頭を残す（安全策。v4.6から継続。safety=True）。"""
    if cfg is None:
        cfg = SETTINGS["p1"]
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


def p3_of(tp, n):
    p3 = [0.0] * n
    for idx, pr in tp.items():
        for j in idx:
            p3[j] += pr
    return p3


def par_record(points, scale):
    """REC行に載せる、検証用の設定値。points=そのモードの配点、scale=そのモードの能力差倍率。"""
    return {"points": dict(points), "scale": scale, "g": SETTINGS["g"], "p1": SETTINGS["p1"],
            "style_discount": SETTINGS["style_discount"], "wobble_k": SETTINGS["wobble_k"],
            "shr_top3": [SETTINGS["shrink_prior_top3"], SETTINGS["shrink_k_top3"]],
            "shr_jky": [SETTINGS["shrink_prior_jky"], SETTINGS["shrink_k_jky"]],
            "recency": SETTINGS["recency"], "nige_np_min": SETTINGS["nige_np_min"],
            "nige_boost": SETTINGS["nige_boost"],
            "style_adjust": SETTINGS["style_adjust"]}


def print_p1(tbl, horses, styles_ja, nums, u3, sel, p3):
    """【切り捨てと候補】v4.7。"""
    cfg = SETTINGS["p1"]
    print("**【切り捨てと候補（v4.7）】**")
    print("")
    print("逃げ馬の頭数(全出走馬)=%d ／ 逃げ補正=%+.1f（脚質が逃げの馬の能力計に一律加算）" % (sel["nige_all"], SETTINGS["nige_boost"]))
    print("")
    print("切り捨て（補正後の能力計uが%d位以下、または補正後の3着内確率が%.0f%%以下）=%s ／ 候補%d頭=%s ／ 候補の3頭の組%d通り%s" %
          (cfg["cut_rank"] + 1, cfg["cut_p3"] * 100, ",".join(map(str, sel["cut"])) or "なし", len(sel["pool"]), ",".join(map(str, sel["pool"])), sel["ncomb_pool"],
           "（20通り以下のため全買い）" if sel["all_buy"] else ""))
    if sel["safety"]:
        print("")
        print("候補が3頭未満になるため、uの上位3頭を候補にしました（安全策）。")
    print("")
    n = len(nums)
    order = sorted(range(n), key=lambda j: (-u3[j], nums[j]))
    rows = []
    for r, j in enumerate(order, 1):
        u = nums[j]
        rows.append([u, horses[j]["name"], styles_ja[j], "%+.2f" % u3[j], r, "%.1f%%" % (p3[j] * 100), "切り捨て" if u in sel["cut"] else "候補"])
    print(tbl(["馬番", "馬名", "脚質", "補正後の能力計u", "u順位", "3着内確率", "候補"], rows))
    print("")


def print_low_table(tbl, horses, styles_ja, pw, tp, hs, hkn, obs):
    """【根拠3】全頭を3着内確率の順に並べ、7位以下の馬の評価の中身を示す（観察用。買い目の選定には使わない）。"""
    n = len(horses)
    p3 = p3_of(tp, n)
    r3o = sorted(range(n), key=lambda j: -p3[j])
    rw = {j: r + 1 for r, j in enumerate(sorted(range(n), key=lambda j: -pw[j]))}
    ar = {j: r + 1 for r, j in enumerate(sorted(range(n), key=lambda j: -hs[j]["ab"]))}
    rows = []
    for r, j in enumerate(r3o, 1):
        c = hs[j]["c"]
        imax = max(range(len(c)), key=lambda t: c[t])
        imin = min(range(len(c)), key=lambda t: c[t])
        o = obs[j]
        rows.append([r, "1-3位" if r <= 3 else ("4-6位" if r <= 6 else "7位以下"), horses[j]["num"], horses[j]["name"], styles_ja[j],
                     "%.1f%%" % (p3[j] * 100), rw[j], ar[j], "%+.2f" % hs[j].get("adj_ref", hs[j]["adj"]),
                     "%s%+.2f" % (hkn[imax], c[imax]), "%s%+.2f" % (hkn[imin], c[imin]),
                     "-" if o["dx"] is None else "%+d" % o["dx"], "-" if o["wd"] is None else "%+d" % o["wd"], "有" if o["tr"] else "-"])
    print("**【根拠3】3着内確率の順位と、7位以下の馬の評価の中身**（観察用。買い目の選定には使わない）")
    print("")
    print(tbl(["3着内確率順", "帯", "馬番", "馬名", "脚質", "3着内確率", "勝率順", "能力計順位", "参考補正計", "最大寄与", "最小寄与", "前走比距離", "体重増減", "能試"], rows))
    print("")
    print("勝率順=逃げ補正を加えた後の勝率の順位。能力計順位=補正を除いた能力ユーティリティの順位。参考補正計=v4.0方式の全脚質補正を使った場合の補正の合計（勝率に使わない観察用。v4.7の逃げ補正は別で、【根拠2】の「適用:逃げ補正」）。最大寄与・最小寄与=能力ユーティリティの項目別寄与（ロジット）の最大・最小。前走比距離=今回距離-前走距離（+は延長）。体重増減・能試は事実の表示のみ（体重は予想に使わない）。")
    print("")


def predict_debut(hdr, horses, warns):
    """新馬モード（全頭が初出走）。能試・初出走時勝率・騎手コース・種牡馬・騎手厩舎で採点。"""
    D = SETTINGS["debut"]
    P, scale = D["points"], D["scale"]
    nh = len(horses)
    nums = [h["num"] for h in horses]
    # 能試は日付・距離が最頻と同じ馬だけ比較（他は中立）
    keys = [(h["trial"]["date"], h["trial"]["dist"]) for h in horses if h["trial"]]
    modal = max(sorted(set(keys)), key=keys.count) if keys else None
    miss = []
    feats = {k: [] for k in P}
    for h in horses:
        t = h["trial"]
        if t and (t["date"], t["dist"]) == modal:
            feats["trial"].append(-t["time"])
        else:
            feats["trial"].append(None)
            miss.append(h["num"])
        feats["debut"].append((h["debut_j"] + h["debut_t"]) / 2 if h["debut_j"] is not None else None)
        jc = []
        if h.get("ai_rate") is not None:
            jc.append(shrunk_rate(h["ai_rate"] * h["ai_n"], h["ai_n"], SETTINGS["shrink_prior_jky"], SETTINGS["shrink_k_jky"]))
        if h["jkc_rate"] is not None:
            jc.append(h["jkc_rate"])
        feats["jkcourse"].append(sum(jc) / len(jc) if jc else None)
        feats["sire"].append(h["sire_rate"])
        feats["jktr"].append(None)
    # 騎手×調教師の相性(ai2)
    for i, h in enumerate(horses):
        v = h.get("ai2")
        feats["jktr"][i] = shrunk_rate(v[0] * v[1], v[1], SETTINGS["shrink_prior_jky"], SETTINGS["shrink_k_jky"]) if v and v[1] else None
    if miss:
        warns.append("能試タイムを比較できない馬（なし/日付・距離違い）: %s（中立0）" % ",".join(map(str, miss)))
    zf = {k: z_scores(v) for k, v in feats.items()}
    util = [sum(P[k] / 100.0 * scale * zf[k][i] for k in P) for i in range(nh)]
    pw = softmax(util)
    tp = trio_probs([round(x, 6) for x in pw], SETTINGS["g"])   # RECのp_win（6桁）と同じ値から計算する（考察計算の再計算と一致させる）
    total = sum(tp.values())
    if abs(total - 1.0) > 1e-6:
        warns.append("三連複確率の合計が1でない(%.6f)" % total)
    ranked = sorted(tp.items(), key=lambda kv: -kv[1])
    topn = SETTINGS["top_n"]
    top = []
    for rk, (idx, pr) in enumerate(ranked[:topn], 1):
        top.append({"rank": rk, "combo": "-".join(str(nums[j]) for j in sorted(idx, key=lambda j: nums[j])), "p": round(pr, 6)})
    if len(ranked) <= topn:
        warns.append("参考順位は全%d組（20点以下）を出力。実購入は固定順位のみ（全組購入の特例なし）" % len(ranked))
    marks = build_marks(top)
    hk = list(P.keys())
    hs = [{"n": nums[i], "c": [round(P[k] / 100.0 * scale * zf[k][i], 3) for k in hk], "ab": round(util[i], 3), "sa": 0.0, "fa": 0.0,
           "sc": 1.0, "adj": 0.0, "u": round(util[i], 3),
           "raw": [None if feats[k][i] is None else round(feats[k][i], 4) for k in hk],
           "src": {"ai": [horses[i].get("ai_rate"), horses[i].get("ai_n")], "ai2": horses[i].get("ai2"),
                   "dj": horses[i].get("debut_j"), "dt": horses[i].get("debut_t")}} for i in range(nh)]
    obs = observe(horses, hdr)
    rec = {
        "ver": VERSION, "code": code_sha(), "scale": scale, "mode": "新馬", "marks": marks, "race_id": hdr["race_id"], "venue": hdr["venue"], "dist": hdr["dist"],
        "course": hdr["course"], "heads": nh, "nums": nums, "p_win": [round(x, 6) for x in pw],
        "style": ["不明"] * nh, "style_table": "なし(新馬)", "expected_nige": 0.0, "top": top, "warnings": warns,
        "hk": hk, "hs": hs, "obs": obs, "par": par_record(P, scale), "p1": None, "q": hdr.get("quality"),
    }

    def tbl(head, rows):
        out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
        for r in rows:
            out.append("| " + " | ".join(str(x) for x in r) + " |")
        return "\n".join(out)

    purchase_record(rec)
    KN = [("trial", "能試時計"), ("debut", "初出走(騎/厩平均)"), ("jkcourse", "騎手コース"), ("sire", "種牡馬連対率"), ("jktr", "騎手厩舎")]
    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    print("")
    print("**【予想 %s・新馬モード】** レースID=%s ／ %s ／ %s%sm%s ／ %d頭" % (VERSION, hdr["race_id"], hdr["venue"], hdr["surface"], hdr["dist"],
                                                                       "(%s)" % hdr["course"] if hdr["course"] else "", nh))
    print("")
    for w in warns:
        print("警告: " + w)
        print("")
    print("全頭が初出走のため、近走・脚質は使わず、能力試験などで採点しています（逃げ補正はありません）。")
    print("")
    print("**馬別 推定勝率**")
    print("")
    print(tbl(["馬番", "馬名", "騎手", "推定勝率"],
              [[nums[i], horses[i]["name"], horses[i]["jockey"], "%.1f%%" % (pw[i] * 100)] for i in sorted(range(nh), key=lambda j: -pw[j])]))
    print("")
    print("**【根拠1】特徴量の生値**（-は取得不可＝中立0）")
    print("")
    rows = []
    for i in range(nh):
        c = []
        for k, _ in KN:
            v = feats[k][i]
            c.append("-" if v is None else ("%.1f" % -v if k == "trial" else ("%.1f" % v if k == "debut" else "%.3f" % v)))
        rows.append([nums[i]] + c)
    print(tbl(["馬番"] + [nm for _, nm in KN], rows))
    print("")
    print("**【根拠2】能力ユーティリティ** = Σ(配点/100×能力差倍率%.1f×レース内z得点)。各項の寄与（ロジット）" % scale)
    print("")
    print("配点: " + " ／ ".join("%s=%d" % (nm, P[k]) for k, nm in KN))
    print("")
    rows = []
    for i in sorted(range(nh), key=lambda j: -pw[j]):
        c = [P[k] / 100.0 * scale * zf[k][i] for k, _ in KN]
        rows.append([nums[i]] + ["%+.2f" % x for x in c] + ["%+.2f" % util[i], "%.1f%%" % (pw[i] * 100)])
    print(tbl(["馬番"] + [nm for _, nm in KN] + ["合計U", "勝率"], rows))
    print("")
    print("勝率 = softmax(合計U)。三連複確率 = 全組合せのヘンリー型式（1着は勝率、2・3着は勝率のg乗を正規化して計算。g=%.2f）。" % SETTINGS["g"])
    print("")
    print_low_table(tbl, horses, ["不明"] * nh, pw, tp, hs, [nm for _, nm in KN], obs)
    print("**評価用参考順位（実購入とは別）三連複 上位%d点**" % len(top))
    print("")
    print(tbl(["順位", "買い目", "確率"], [[t["rank"], t["combo"], "%.3f%%" % (t["p"] * 100)] for t in top]))
    print("")
    print_purchase(rec, tbl)
    print_marks(rec["reference_marks"], tbl)
    print("")
    print("予想レコード（下のコードブロックを結果の考察用に保存）:")
    print("")
    print("```")
    print("REC " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    print("```")
    return 0


def predict(path, expect=None):
    load_settings()
    warns = []
    soup, raw = make_soup(path)
    hdr = parse_header(soup, raw, warns)
    # v4.7修正(2026-11-08): 会場・距離・レースIDが取れないHTMLは、新馬モード等に誤って進まないよう停止する。
    if not hdr["venue"] or not hdr["dist"] or not hdr["race_id"]:
        print("エラー: 出走表HTMLから会場・距離・レースIDを読み取れません（%s）。文字化けや別ページの可能性があります。HTMLを確認してください。" % " / ".join(warns))
        return 1
    # 指定(会場+R番号 例: 浦和12R)とHTMLの一致確認。不一致なら出力せず停止。
    if expect:
        m = re.match(r"\s*(浦和|船橋|大井|川崎)\s*(\d{1,2})\s*R\s*$", expect)
        rno = int(hdr["race_id"][-2:]) if hdr["race_id"] else None
        if not m:
            print("エラー: 指定は『浦和12R』の形式で渡してください: %s" % expect)
            return 1
        if hdr["venue"] != m.group(1) or rno != int(m.group(2)):
            print("エラー: 指定(%s)とHTML(%s %sR, id=%s)が一致しません。HTMLを確認してください。" % (expect, hdr["venue"], rno, hdr["race_id"]))
            return 1
    horses = parse_horses(soup, hdr, warns)
    if len(horses) < 3:
        print("エラー: 馬を3頭以上抽出できません。HTMLを確認してください。")
        return 1
    if hdr["heads"] and hdr["heads"] != len(horses):
        warns.append("頭数表記%d頭と抽出頭数%d頭が不一致" % (hdr["heads"], len(horses)))
    nh = len(horses)
    # v4.7: 品質の記録と、結果混入の確認（近走欄の最新日がレース日より前であること）
    _dates = [r_["date"] for h_ in horses for r_ in h_["runs"] if r_ and r_.get("date")]
    _rdate = (hdr.get("race_id") or "")[:8]
    _latest = max(_dates) if _dates else None
    _ok = (_latest is None) or (not re.fullmatch(r"\d{8}", _rdate)) or (_latest < _rdate)
    _nums = sorted(h_["num"] for h_ in horses)
    hdr["quality"] = {"scratched": len(hdr.get("scratched_cells", [])), "scratched_cells": hdr.get("scratched_cells", []),
                      "missing_nums": [k_ for k_ in range(1, (_nums[-1] if _nums else 0) + 1) if k_ not in _nums],
                      "latest_run": _latest, "race_date": _rdate, "date_ok": bool(_ok)}
    if not _ok:
        print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
        print("")
        print("【停止】近走欄の最新日(%s)がレース日(%s)以降です。結果が混入したHTMLの疑いがあります。レース前のHTMLで実行してください。" % (_latest, _rdate))
        return 1
    n_debut = sum(1 for h in horses if h.get("is_debut"))
    if n_debut == nh:
        return predict_debut(hdr, horses, warns)
    if n_debut > 0:
        print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
        print("")
        print("**【見送り】** レースID=%s ／ %s ／ %s%sm ／ %d頭" % (hdr["race_id"], hdr["venue"], hdr["surface"], hdr["dist"], nh))
        print("")
        print("初出走馬と経験馬が混在するレースのため、買い目は出しません（初出走%d頭・経験%d頭）。" % (n_debut, nh - n_debut))
        return 0
    return predict_normal(hdr, horses, warns)


def build_features(horses, hdr, weights, v43=False):
    """特徴量の生値と脚質。weights=近走の重み、v43=Trueは脚質・逃げ確率をv4.3の方法（前2欄）で求める（比較用の記録ref43）。"""
    feats = {k: [] for k in ["ord", "margin", "pos", "l3f", "apt", "time", "jky", "wt"]}
    styles, wobbles, nprobs, fms, metas, srcs, frs = [], [], [], [], [], [], []
    for h in horses:
        rf, fr, meta = run_features(h, hdr, weights)
        for k in ("ord", "margin", "pos", "l3f"):
            feats[k].append(rf[k])
        s, sd, fm = classify_style(fr, v43)
        npv = nige_prob(fr, v43)
        if not v43 and s is not None:       # 逃げ⇔逃げ確率がnige_np_min以上。平均0.20以下でも逃げ確率が足りない馬は先行
            if npv >= SETTINGS["nige_np_min"]:
                s = 0
            elif s == 0:
                s = 1
        styles.append(s); wobbles.append(sd); nprobs.append(npv); fms.append(fm); metas.append(meta); frs.append([round(v, 3) for (i, v) in fr if i < 5])
        srcs.append({"dr": h["dist_rec"], "vr": h["venue_rec"], "ai": [h.get("ai_rate"), h.get("ai_n")], "jr": h["jky_rec"]})
        # 適性
        parts = []
        for rec in (h["dist_rec"], h["venue_rec"]):
            if rec:
                n = sum(rec)
                parts.append(shrunk_rate(rec[0] + rec[1] + rec[2], n, SETTINGS["shrink_prior_top3"], SETTINGS["shrink_k_top3"]))
        feats["apt"].append(sum(parts) / len(parts) if parts else None)
        feats["time"].append(-h["best_time"] if h["best_time"] else None)
        # 騎手
        jp = []
        if h.get("ai_rate") is not None:
            jp.append((0.6, shrunk_rate(h["ai_rate"] * h["ai_n"], h["ai_n"], SETTINGS["shrink_prior_jky"], SETTINGS["shrink_k_jky"])))
        if h["jky_rec"]:
            n = sum(h["jky_rec"])
            jp.append((0.4, shrunk_rate(sum(h["jky_rec"][:3]), n, SETTINGS["shrink_prior_top3"], SETTINGS["shrink_k_top3"])))
        feats["jky"].append(sum(w * v for w, v in jp) / sum(w for w, _ in jp) if jp else None)
        # 馬体重
        feats["wt"].append(-min(abs(h["wt_diff"]), 20) if h["wt_diff"] is not None else None)

    return feats, styles, wobbles, nprobs, fms, metas, srcs, frs


def predict_normal(hdr, horses, warns):
    """通常モード（全頭が経験馬）。v4.7: 勝率=softmax(能力計＋逃げ補正)（逃げ補正は一律+0.9）。補正後のuの順位と補正後の3着内確率で切り捨て（配分表・展開区分は廃止）、
    残った馬の3頭の組を全頭の三連複確率の高い順に並べ、連続上位1〜20位を仮想購入する。比較用の記録ref45は、補正なし(u=能力計)で同じ手順を行う。"""
    nh = len(horses)
    P = SETTINGS["points"]
    scale = SETTINGS["scale"]
    g = SETTINGS["g"]

    # --- 特徴量（生値）。近走の重みは同じ(0.2)、脚質は最大前5走の平均（能試の走は数えない）
    feats, styles, wobbles, nprobs, fms, metas, srcs, frs = build_features(horses, hdr, SETTINGS["recency"])
    # 品質の記録（レースごと）: 1角位置の取れない馬の数、特徴量の欠測率（体重を除く）、頭数表記と抽出頭数
    q = hdr.setdefault("quality", {})
    q["fm_missing"] = sum(1 for f_ in fms if f_ is None)
    _ks = [k_ for k_ in feats if k_ != "wt"]
    q["feat_missing"] = round(sum(1 for k_ in _ks for v_ in feats[k_] if v_ is None) / float(nh * len(_ks)), 4)
    q["heads_hdr"] = hdr.get("heads")
    q["heads_parsed"] = nh
    # 馬体重は予想に使わない（配点0）ので、取得できない馬の警告は出さない。欠測は obs の wd=None として記録される。
    for h in horses:
        for w in h["warn"]:
            if "馬体重" not in w:
                warns.append("馬番%d: %s" % (h["num"], w))

    # --- z得点 → 能力ユーティリティ
    zf = {k: z_scores(v) for k, v in feats.items()}
    ability = []
    for i in range(nh):
        u = 0.0
        for k in feats:
            u += P[k] / 100.0 * scale * zf[k][i]
        ability.append(u)

    # --- 脚質補正（v4.0方式の全脚質補正は参考値としてだけ計算する）
    row, row_name = style_row(hdr["venue"], hdr["dist"] or 0, warns) if hdr["dist"] else (JRA_BASE, "JRA")
    sadj = style_adjust_vector(row)
    expected_nige = sum(nprobs)
    fadj = front_adjust(expected_nige)
    adj_ref = []
    for i in range(nh):
        if styles[i] is None:
            adj_ref.append(0.0)
        else:
            scl = 1.0 / (1.0 + SETTINGS["wobble_k"] * wobbles[i])
            adj_ref.append((sadj[styles[i]] + fadj[styles[i]]) * scl)     # 参考（観察用）
    style_names = [STYLES[s] if s is not None else "不明" for s in styles]
    # --- v4.7 逃げ補正: 脚質が逃げの馬だけ、一律+0.9を能力ユーティリティに加える
    nige_all = sum(1 for s_ in style_names if s_ == "逃げ")
    boost = SETTINGS["nige_boost"]
    adj = [boost if style_names[i] == "逃げ" else 0.0 for i in range(nh)]
    util = [ability[i] + adj[i] for i in range(nh)]
    pw = softmax(util)

    pw6 = [round(x, 6) for x in pw]
    tp = trio_probs(pw6, g)          # RECのp_win（6桁）と同じ値から計算する（考察計算の再計算と一致させる）。全頭で計算する（選定馬だけで作り直さない）
    total = sum(tp.values())
    if abs(total - 1.0) > 1e-6:
        warns.append("三連複確率の合計が1でない(%.6f)" % total)
    nums = [h["num"] for h in horses]
    topn = SETTINGS["top_n"]

    # --- 切り捨て（補正後のu順位・補正後の3着内確率）→ 残った馬の組を全頭確率順に → 連続上位1〜20位
    p3_full = p3_of(tp, nh)
    u3 = [round(x, 3) for x in util]
    sel = select_v47(nums, u3, p3_full)
    ranked = pool_ranked(nums, tp, sel["pool"])
    sel.update({"nige_all": nige_all, "ncomb_pool": len(ranked), "all_buy": len(ranked) <= topn})
    top = [{"rank": rk, "combo": "-".join(str(u) for u in c), "p": round(pr, 6)} for rk, (c, pr) in enumerate(ranked[:topn], 1)]

    # 比較用の記録ref45（買い目には使わない）= 補正なし(u=能力計)で、同じ切り捨て手順・同じ購入帯
    ab3 = [round(a, 3) for a in ability]
    pw45_6 = [round(x, 6) for x in softmax(ability)]      # 丸め前の能力計から作る。考察計算は3桁の能力計との丸め区間で照合する
    tp45 = trio_probs(pw45_6, g)
    sel45 = select_v47(nums, ab3, p3_of(tp45, nh))
    rk45 = pool_ranked(nums, tp45, sel45["pool"])
    sel45.update({"nige_all": nige_all, "ncomb_pool": len(rk45), "all_buy": len(rk45) <= topn})
    ref45 = {"ab": ab3, "p_win": pw45_6, "p1": sel45,
             "top": [{"rank": rk, "combo": "-".join(str(u) for u in c), "p": round(pr, 6)} for rk, (c, pr) in enumerate(rk45[:topn], 1)]}

    if sel["all_buy"]:
        warns.append("残った馬の3頭の組は全%d通り（20通り以下）のため全買い。回収率の評価からは除く" % len(ranked))
    marks = build_marks(top)
    hs = []
    for i in range(nh):
        if styles[i] is None:
            sa_ = fa_ = 0.0
            scl_ = 1.0
        else:
            sa_ = sadj[styles[i]]
            fa_ = fadj[styles[i]]
            scl_ = 1.0 / (1.0 + SETTINGS["wobble_k"] * wobbles[i])
        hs.append({"n": nums[i], "c": [round(P[k] / 100.0 * scale * zf[k][i], 3) + 0.0 for k in HK_NORMAL], "ab": round(ability[i], 3),
                   "sa": round(sa_, 3), "fa": round(fa_, 3), "sc": round(scl_, 3), "adj": round(adj[i], 3), "adj_ref": round(adj_ref[i], 3), "u": round(util[i], 3),
                   "sd": round(wobbles[i], 3), "fm": None if fms[i] is None else round(fms[i], 3), "np": round(nprobs[i], 3), "fr": frs[i],
                   "raw": [None if feats[k][i] is None else round(feats[k][i], 4) for k in HK_NORMAL],
                   "src": srcs[i], "nr": metas[i]["nr"], "sk": metas[i]["sk"]})
    obs = observe(horses, hdr)
    rec = {
        "ver": VERSION, "code": code_sha(), "scale": scale, "mode": "通常", "marks": marks, "race_id": hdr["race_id"], "venue": hdr["venue"], "dist": hdr["dist"],
        "course": hdr["course"], "heads": nh, "nums": nums,
        "p_win": pw6,
        "style": style_names,
        "style_table": row_name, "expected_nige": round(expected_nige, 2),
        "top": top, "p1": sel, "ref45": ref45, "warnings": warns,
        "hk": HK_NORMAL, "hs": hs, "obs": obs, "q": hdr.get("quality"),
        "row": list(row), "sadj": [round(v, 3) for v in sadj], "fadj": [round(v, 3) for v in fadj], "par": par_record(P, scale),
    }

    purchase_record(rec)

    # --- 出力（Markdown表。平文でそのまま貼ると表として表示される）
    def tbl(head, rows):
        out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
        for r in rows:
            out.append("| " + " | ".join(str(x) for x in r) + " |")
        return "\n".join(out)

    print("[コード指紋 sha256先頭12桁=%s]" % code_sha())
    print("")
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
    print("脚質表=%s ／ 逃げ馬の頭数(全出走馬)=%d ／ 逃げ補正=%+.1f（脚質が逃げの馬に一律） ／ 参考:逃げ期待数(最大前5走)=%.2f" % (row_name, nige_all, boost, expected_nige))
    print("")
    print("**馬別 推定勝率**（逃げ補正後）")
    print("")
    print(tbl(["馬番", "馬名", "騎手", "脚質", "推定勝率"],
              [[nums[i], horses[i]["name"], horses[i]["jockey"], rec["style"][i], "%.1f%%" % (pw[i] * 100)]
               for i in sorted(range(nh), key=lambda j: -pw[j])]))
    print("")
    KN = [("ord", "着順"), ("margin", "着差"), ("pos", "位置"), ("l3f", "末脚"), ("apt", "適性"), ("time", "時計"), ("jky", "騎手"), ("wt", "体重")]
    print("**【根拠1】特徴量の生値**（-は取得不可＝中立0。体重は配点0で予想に使わない観察用の値）")
    print("")
    rows = []
    for i in range(nh):
        cells = []
        for k, _ in KN:
            v = feats[k][i]
            cells.append("-" if v is None else ("%.1f" % v if k in ("time", "wt") else "%.3f" % v))
        rows.append([nums[i]] + cells + ["-" if styles[i] is None else STYLES[styles[i]], "%.2f" % wobbles[i]])
    print(tbl(["馬番"] + [nm for _, nm in KN] + ["脚質", "ブレsd"], rows))
    print("")
    print("**【根拠2】能力ユーティリティ** = Σ(配点/100×能力差倍率%.1f×レース内z得点)。各項の寄与（ロジット）" % scale)
    print("")
    print("配点: " + " ／ ".join("%s=%d" % (nm, P[k]) for k, nm in KN))
    print("")
    rows = []
    for i in sorted(range(nh), key=lambda j: -pw[j]):
        c = [P[k] / 100.0 * scale * zf[k][i] + 0.0 for k, _ in KN]
        if styles[i] is None:
            sa = fa = 0.0; scl = 1.0
        else:
            sa = sadj[styles[i]]; fa = fadj[styles[i]]; scl = 1.0 / (1.0 + SETTINGS["wobble_k"] * wobbles[i])
        rows.append([nums[i]] + ["%+.2f" % x for x in c] + ["%+.2f" % ability[i], "%+.2f" % adj[i], "%+.2f" % sa, "%+.2f" % fa, "x%.2f" % scl,
                                                          "%+.2f" % adj_ref[i], "%+.2f" % util[i], "%.1f%%" % (pw[i] * 100)])
    print(tbl(["馬番"] + [nm for _, nm in KN] + ["能力計", "適用:逃げ補正", "参考:会場脚質補正", "参考:逃げ数補正", "参考:ブレ縮小", "参考:補正計", "合計U", "勝率"], rows))
    print("")
    print("勝率 = softmax(合計U)。合計U = 能力計 + 適用:逃げ補正（脚質が逃げの馬だけ一律+%.1f。他の脚質は0）。近走は前5走を同じ重み(0.2)で平均（走数3未満は中立方向へ縮小。能力試験の走は数えない）。体重は配点0（予想に使わない。表の「体重」列は観察用の記録）。「参考:」の列は、v4.0方式の全脚質補正を使った場合の値の観察用で、勝率・買い目には入らない。三連複確率 = ヘンリー型式（1着は勝率、2・3着は勝率のg乗を正規化して計算。g=%.2f）を全頭で計算する。買い目は、切り捨て後に残った馬の3頭の組を、この全頭での確率の高い順に並べて作る（選定馬だけで確率を作り直さない）。" %
          (SETTINGS["nige_boost"], g))
    print("")
    print_low_table(tbl, horses, rec["style"], pw, tp, hs, [nm for _, nm in KN], obs)
    print_p1(tbl, horses, rec["style"], nums, u3, sel, p3_full)
    print("**仮想購入 三連複 連続上位%d点（v4.7方式＝逃げ補正一律+%.1f・体重なし・近走の重みなし・切り捨て後の候補の組から）**" % (len(top), boost))
    print("")
    print(tbl(["順位", "買い目", "全頭での確率"], [[t["rank"], t["combo"], "%.3f%%" % (t["p"] * 100)] for t in top]))
    print_purchase(rec, tbl)
    print_marks(rec["reference_marks"], tbl)
    print("")
    print("予想レコード（下のコードブロックを結果の考察用に保存）:")
    print("")
    print("```")
    print("REC " + json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    print("```")
    return 0

# ============================================================
# result / aggregate: 考察計算v4.7.pyに委譲
# ============================================================

def _kosatsu_module():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "考察計算v4.7.py")
    spec = importlib.util.spec_from_file_location("keiba_v47_kosatsu", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def result(rec_arg, res_str):
    """実購入の厳密照合を共通化し、集計用LEDGERを出力する。"""
    return _kosatsu_module().kosatsu(rec_arg, res_str)


def aggregate(path):
    """v4.6は結果付きRECでなくLEDGERを集計する。"""
    return _kosatsu_module().aggregate(path)


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "predict":
        return predict(a[1], a[2] if len(a) >= 3 else None)
    if len(a) >= 3 and a[0] == "result":
        return result(a[1], " ".join(a[2:]))
    if len(a) >= 2 and a[0] == "aggregate":
        return aggregate(a[1])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
