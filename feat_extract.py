# -*- coding: utf-8 -*-
"""候補抽出.py（Web版のファイル名は feat_extract.py。中身は同一）
出走表HTMLから、全頭の候補項目を加工せずに抜き出し、FEAT行（1行のJSON）にする。次版の検討用の記録で、予測・考察の計算は持たない。
分析計算v4.7.py（keiba_v47.py）の文字コード判定・見出し・出走馬の抽出をそのまま使い、馬番の並びが分析計算と一致することを確かめる。
候補の値（間隔・乗り替わりなど）の計算はここでは行わない（絞り込み集計で行う。定義を変えても抜き出し直さなくて済むようにするため）。
読み取れない項目は None にし、推測で補わない。
使い方: python 候補抽出.py 出走表.txt   （同じフォルダの 分析計算v4.7.py を読み込む。標準出力に FEAT 行）"""
import re, os, sys, json, hashlib, importlib.util

FEAT_VERSION = "feat-1"
NANKAN = ("浦和", "船橋", "大井", "川崎")
MARKS = "☆▲△◇★"
# 記録だけする欄（絞り込みには使わない）。キー＝セルのclass、値＝記録名
RAW_CELLS = [("cs-ai1", "騎手コース相性"), ("cs-ai2", "騎手調教師相性"), ("mk-wzg", "馬体重"), ("mk-wre", "連対時馬体重"),
             ("mk-btm", "持時計"), ("mk-oky", "距離別着順"), ("mk-ojo", "場別着順"), ("mk-kwc", "騎手別成績_勝利数"),
             ("mk-kwp", "騎手別成績_率"), ("mk-baba", "馬場状態別"), ("mk-intv", "出走間隔別"), ("mk-sire", "種牡馬分析"),
             ("mk-kise", "季節別"), ("mk-kco", "騎手コース別"), ("mk-hrtn", "回収率_競走馬"), ("mk-krtn", "回収率_騎手"),
             ("cs-owner", "馬主_生産")]


def code_sha(path=None):
    """分析計算・考察計算と同じ式（空白・改行を除いたsha256の先頭12桁）。"""
    p = path or os.path.abspath(__file__)
    return hashlib.sha256(re.sub(r"\s+", "", open(p, encoding="utf-8").read()).encode("utf-8")).hexdigest()[:12]


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _int(s):
    s = clean(s)
    return int(s) if re.fullmatch(r"\d+", s) else None


def _strip_marks(s):
    """減量記号を取り除いた文字列と、記号（なければNone）。"""
    s = clean(s)
    mk = "".join(c for c in s if c in MARKS)
    return re.sub(r"[%s]" % MARKS, "", s).strip(), (mk or None)


def jockey_key(name):
    """騎手名の照合用キー: 減量記号・空白を取り除く。"""
    return re.sub(r"[\s%s]" % MARKS, "", name or "")


def _past_run(td):
    """過去走1欄。欄が空なら None。能試・取消なども欄として残し、異常の種類を記録する。"""
    if td is None:
        return None
    txt = clean(td.get_text(" "))
    if not txt or txt in ("-", "--"):
        return None
    r = {"着順": None, "異常": None, "場": None, "日付": None, "日付の出所": None, "レースID": None, "馬場": None, "コース": None, "距離": None,
         "クラス": None, "頭数": None, "馬番": None, "人気": None, "騎手": None, "減量記号": None, "斤量": None, "体重": None,
         "勝ち馬": None, "タイム": None, "着差": None, "上がり3F": None, "上がり順位": None, "通過順": [], "原文": txt[:300]}
    if txt.startswith("初出走時勝率"):          # 新馬の出走表の欄（走ではない）。原文だけ残す
        r["異常"] = "初出走欄"
        return r
    head = td.select_one("p.nk23_u-d-flex")
    sp = head.find_all("span", recursive=False) if head else []
    fin = clean(sp[0].get_text("")) if sp else ""
    m = re.match(r"(\d+)着?$", fin)
    if m:
        r["着順"] = int(m.group(1))
    else:
        r["異常"] = re.sub(r"着$", "", fin) or ("能試" if "能試" in txt else "不明")
    vd = clean(sp[1].get_text()) if len(sp) > 1 else ""
    mv = re.match(r"(\D+?)(\d{2})\.(\d{1,2})\.(\d{1,2})$", vd)
    r["場"] = mv.group(1) if mv else (vd or None)
    # 日付: rcd_（隠し項目）→ 結果ページへのリンク → 表記「水沢25.12.14」の順（分析計算と同じ優先順。表記は最後の手段）
    rcd = td.select_one('input[id^="rcd_"]')
    rc = td.select_one('input[id^="rc_"]')
    d = clean(rcd.get("value")) if rcd else ""
    link = None
    for a_ in td.select('a[href*="/result/"]'):
        mm = re.search(r"/result/(\d{16})", a_.get("href", ""))
        if mm:
            link = mm.group(1)
            break
    if re.fullmatch(r"\d{8}", d):
        r["日付"], r["日付の出所"] = d, "rcd"
    elif link:
        r["日付"], r["日付の出所"] = link[:8], "リンク"
    elif mv:
        r["日付"], r["日付の出所"] = "20%s%02d%02d" % (mv.group(2), int(mv.group(3)), int(mv.group(4))), "表記"
    rid = clean(rc.get("value")) if rc else ""
    r["レースID"] = rid if re.fullmatch(r"\d{16}", rid) else link
    cd = clean(sp[2].get_text(" ")) if len(sp) > 2 else ""
    mc = re.match(r"(良|稍|重|不)?\s*(.*?)\s*(\d{3,4})$", cd)
    if mc:
        r["馬場"], r["コース"], r["距離"] = mc.group(1), (mc.group(2) or None), int(mc.group(3))
    a = td.select_one("a.race_name_len")
    if a:
        r["クラス"] = clean(a.get("title") or a.get_text())
    pop = td.select_one("span.popularity")
    pt = clean(pop.get_text(" ")) if pop else ""
    for key, pat in (("頭数", r"(\d+)頭"), ("馬番", r"(\d+)番"), ("人気", r"(\d+)人気")):
        mm = re.search(pat, pt)
        r[key] = int(mm.group(1)) if mm else None
    js = pop.find_next_sibling("span") if pop else None
    jt = clean(js.get_text(" ")) if js else ""
    mj = re.match(r"(.*?)\s*([\d.]+)$", jt)
    nm, mk = _strip_marks(mj.group(1) if mj else jt)
    r["騎手"], r["減量記号"] = (jockey_key(nm) or None), mk
    r["斤量"] = float(mj.group(2)) if mj else None
    w = td.select_one("span.weight")
    mw = re.search(r"(\d+)kg", clean(w.get_text())) if w else None
    r["体重"] = int(mw.group(1)) if mw else None
    wn = td.select_one("span.winner")
    r["勝ち馬"] = clean(wn.get_text()) if wn else None
    rt = td.select_one("span.racetime")
    if rt:
        t = clean(rt.get_text(" "))
        mt = re.match(r"([\d:.]+)", t)
        r["タイム"] = mt.group(1) if mt else None
        mm = re.search(r"\(\s*(-?[\d.]+)\s*\)", t)
        r["着差"] = float(mm.group(1)) if mm else None
    ft = td.select_one("span.furlongtime")
    if ft:
        t = clean(ft.get_text(" "))
        mm = re.search(r"3F\s*([\d.]+)", t)
        r["上がり3F"] = float(mm.group(1)) if mm else None
        mm = re.search(r"\(\s*(\d+)\s*\)", t)
        r["上がり順位"] = int(mm.group(1)) if mm else None
    po = td.select_one("p.position")
    if po:
        r["通過順"] = [int(x) for x in re.findall(r"\d+", clean(po.get_text(" ")))]
    return r


def _horse(row, waku):
    h = {"馬番": _int(row.select_one("td.umaban").get_text()), "枠": waku}
    nm = row.select_one("td.pr-umaName-textRound")
    ps = [clean(p.get_text(" ")) for p in nm.find_all("p")] if nm else []
    nn = nm.select_one("span.nk23_u-text16") if nm else None
    h["馬名"] = clean(nn.get_text()) if nn else None
    a = nm.select_one('a[href*="/uma_info/"]') if nm else None
    m = re.search(r"/uma_info/(\d+)", a.get("href", "")) if a else None
    h["馬ID"] = m.group(1) if m else None
    h["父"] = ps[0] if ps else None
    sa = next((p for p in ps if re.search(r"(牡|牝|セ)\d+", p)), "")
    m = re.search(r"(牡|牝|セ)(\d+)\s*(\S+)?\s*(\d{2}\.\d{1,2}\.\d{1,2})?", sa)
    h["性"], h["年齢"] = (m.group(1), int(m.group(2))) if m else (None, None)
    h["毛色"] = m.group(3) if m else None
    h["生年月日"] = m.group(4) if m else None
    rest = ps[ps.index(sa) + 1:] if sa in ps else []
    h["母"] = rest[0] if rest else None
    h["母父"] = rest[1].strip("（）()") if len(rest) > 1 else None
    g1 = row.select_one("td.cs-g1")
    gp = g1.find_all("p") if g1 else []
    lic = g1.select_one('input[name="jockey_license"]') if g1 else None
    h["騎手"] = h["騎手ID"] = h["騎手所属"] = h["負担重量"] = h["減量記号"] = None
    h["調教師"] = h["調教師ID"] = h["調教師所属"] = None
    if gp:
        ja = gp[0].select_one("a")
        h["騎手"] = jockey_key(clean(ja.get_text())) if ja else None
        h["騎手ID"] = clean(lic.get("value")) if lic else None
        sp = gp[0].select_one("span.nk23_u-text10")
        h["騎手所属"] = clean(sp.get_text()).strip("()（）") if sp else None
        kg = gp[0].select_one("span.nk23_u-text12")
        if kg:
            v, mk = _strip_marks(kg.get_text())
            mm = re.fullmatch(r"\d+(\.\d+)?", v)
            h["負担重量"] = float(v) if mm else None
            h["減量記号"] = mk
    if len(gp) > 1:
        ta = gp[1].select_one("a")
        h["調教師"] = clean(ta.get_text()) if ta else None
        m = re.search(r"/cho_info/(\d+)", ta.get("href", "")) if ta else None
        h["調教師ID"] = m.group(1) if m else None
        sp = gp[1].select_one("span.nk23_u-text10")
        h["調教師所属"] = clean(sp.get_text()).strip("()（）") if sp else None
    h["過去走"] = [_past_run(row.select_one("td.mk-z%d" % k)) for k in range(1, 6)]
    h["記録のみ"] = {}
    for cls, name in RAW_CELLS:
        td = row.select_one("td." + cls)
        h["記録のみ"][name] = clean(td.get_text(" ")) if td is not None else None
    return h


def extract(raw_bytes, eng):
    """戻り値: (feat dict または None, 停止の理由 または None)。eng は keiba_v47（分析計算v4.7.py）のモジュール。"""
    from bs4 import BeautifulSoup
    s, enc = eng.decode_html(raw_bytes)
    if s is None:
        return None, "文字コードを判定できません"
    soup = BeautifulSoup(s, "lxml")
    warns = []
    hdr = eng.parse_header(soup, s, warns)
    if not hdr.get("race_id") or not re.fullmatch(r"\d{16}", hdr["race_id"]):
        return None, "レースIDを読めません"
    eh = eng.parse_horses(soup, hdr, warns)           # 分析計算と同じ出走馬の抽出（取消・除外の行は除かれる）
    tables = soup.select("table.tb-shousai")
    if not tables:
        return None, "出走表テーブルがありません"
    horses, waku, scratched = [], None, []
    for row in tables[0].select("tr"):
        wk = row.select_one("td.waku")
        if wk is not None:
            waku = _int(wk.get_text())             # 枠のセルは rowspan で次の行に続くことがある
        u = row.select_one("td.umaban")
        if u is None:
            continue
        ut = re.sub(r"\s+", "", clean(u.get_text(" ")))
        if not ut.isdigit():
            scratched.append(ut)
            continue
        horses.append(_horse(row, waku))
    nums_e = [h["num"] for h in eh]
    nums_f = [h["馬番"] for h in horses]
    if nums_e != nums_f:
        return None, "馬番の並びが分析計算の抽出と違います（分析計算=%s、候補抽出=%s）" % (nums_e, nums_f)
    rd = hdr["race_id"][:8]
    late = [(h["馬番"], r["日付"]) for h in horses for r in h["過去走"] if r and r["日付"] and r["日付"] >= rd]
    if late:
        return None, "過去走の日付がレース日以降です: %s" % late[:5]
    for h in horses:
        if h["負担重量"] is None:
            warns.append("%d番の負担重量を読めません" % h["馬番"])
        for k, r in enumerate(h["過去走"], 1):
            if r and r["異常"] is None and r["日付"] is None:
                warns.append("%d番の%d走前の日付を読めません" % (h["馬番"], k))
    heads_row = {}
    for th in tables[0].select("thead th"):
        c = [x for x in th.get("class", []) if x.startswith(("mk-", "cs-"))]
        if c:
            heads_row.setdefault(c[0], []).append(clean(th.get_text(" ")))
    feat = {"fver": FEAT_VERSION, "code_f": code_sha(), "code_a": eng.code_sha(), "race_id": hdr["race_id"], "date": rd,
            "venue": hdr["venue"], "dist": hdr["dist"], "course": hdr.get("course"), "surface": hdr.get("surface"),
            "heads_hdr": hdr.get("heads"), "heads": len(horses), "scratched_cells": scratched, "nums": nums_f,
            "enc": enc, "warnings": warns, "col_heads": heads_row, "horses": horses}
    return feat, None


def feat_line(feat):
    return "FEAT " + json.dumps(feat, ensure_ascii=False, separators=(",", ":"))


def load_engine(path):
    spec = importlib.util.spec_from_file_location("keiba_v47", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    eng_path = next((os.path.join(here, n) for n in ("分析計算v4.7.py", "keiba_v47.py") if os.path.exists(os.path.join(here, n))), None)
    if not eng_path:
        print("【停止】同じフォルダに 分析計算v4.7.py がありません")
        return 1
    eng = load_engine(eng_path)
    feat, err = extract(open(sys.argv[1], "rb").read(), eng)
    if err:
        print("【停止】" + err)
        return 1
    print(feat_line(feat))
    return 0


if __name__ == "__main__":
    sys.exit(main())
