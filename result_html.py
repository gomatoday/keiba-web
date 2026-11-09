# -*- coding: utf-8 -*-
"""結果ページ（nankankeiba.com の「成績・払戻金」ページを保存したHTML）から、着順と三連複の払戻を読み取る。
入力の補助で、予測・考察の計算は持たない。読み取った値は "レースID/1着-2着-3着/払戻円" の文字列にして、
考察計算v4.7.py の kosatsu にそのまま渡す（kosatsuがレースIDの一致・馬番・形式を照合する）。
読み取れない・食い違う場合は、推測で補わずに誤りとして返す。"""
import re

VENUE_CODE = {"浦和": "18", "船橋": "19", "大井": "20", "川崎": "21"}


def _txt(x):
    return re.sub(r"\s+", " ", x.get_text(" ", strip=True)).strip()


def parse_result_html(raw_bytes, decode_html):
    """戻り値: dict（race_id, venue, rno, date, finish, trio[{combo, pay}], result, errors）。errorsが空のときだけ使ってよい。"""
    from bs4 import BeautifulSoup
    out = {"race_id": None, "venue": None, "rno": None, "date": None, "finish": [], "trio": [], "result": None, "errors": [], "notes": []}
    s, enc = decode_html(raw_bytes)
    if s is None:
        out["errors"].append("文字コードを判定できません")
        return out
    try:
        soup = BeautifulSoup(s, "lxml")
    except Exception:
        out["errors"].append("lxmlで読めません")
        return out
    text = _txt(soup)
    if "払戻" not in text or "三連複" not in text:
        out["errors"].append("成績・払戻金のページではないようです（「払戻」「三連複」がありません）")
        return out
    # レースの特定: 見出し「7R 2026年6月2日 第3回 船橋競馬 第2日」と、このレースの詳細リンク /syousai/<ID>.do
    m = re.search(r"(\d{1,2})R (\d{4})年(\d{1,2})月(\d{1,2})日 第\d+回\s*(浦和|船橋|大井|川崎)競馬", text.replace("\xa0", " "))
    if not m:
        out["errors"].append("見出し（R番号・日付・会場）を読み取れません")
        return out
    rno, y, mo, d, venue = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5)
    date = "%s%02d%02d" % (y, mo, d)
    ids = sorted({re.search(r"(\d{16})", a["href"]).group(1) for a in soup.find_all("a", href=True) if re.search(r"/syousai/\d{16}\.do", a["href"])})
    ids = [i for i in ids if i[:8] == date and i[8:10] == VENUE_CODE[venue] and int(i[-2:]) == rno]
    if len(ids) != 1:
        out["errors"].append("レースIDを1つに決められません（候補=%s）" % ",".join(ids))
        return out
    out.update({"race_id": ids[0], "venue": venue, "rno": rno, "date": date})
    # 着順表: 見出しに 着・枠・馬番 がある表
    fin = None
    for t in soup.find_all("table"):
        hs = [_txt(x) for x in t.find_all("th")]
        if hs[:3] == ["着", "枠", "馬番"]:
            fin = t
            break
    if fin is None:
        out["errors"].append("着順の表がありません")
        return out
    rows = []
    for tr in fin.find_all("tr"):
        tds = [_txt(x) for x in tr.find_all("td")]
        if len(tds) < 3:
            continue
        rows.append((tds[0], tds[2]))
    prev = None
    for pos, num in rows:
        if pos == "同着" and prev is not None and re.fullmatch(r"\d+", num):  # 同着の馬は、直前の行と同じ着順
            out["finish"].append({"pos": prev, "n": int(num)})
            out["notes"].append("同着: 馬番%s は %d着" % (num, prev))
        elif re.fullmatch(r"\d+", pos) and re.fullmatch(r"\d+", num):
            prev = int(pos)
            out["finish"].append({"pos": prev, "n": int(num)})
        else:
            out["notes"].append("着順が数字でない行: 着=%s 馬番=%s" % (pos, num))
    top3 = [f for f in out["finish"] if f["pos"] <= 3]
    if len(top3) < 3:
        out["errors"].append("3着以内の馬が3頭そろいません")
        return out
    # 三連複の払戻: 行見出し（th）が「三連複」の行と、rowspanで続く行
    trio = []
    for th in soup.find_all("th"):
        if _txt(th) != "三連複" or th.find_parent("thead") is not None:
            continue
        span = int(th.get("rowspan") or 1)
        tr = th.find_parent("tr")
        cur = tr
        for k in range(span):
            if cur is None:
                break
            tds = [_txt(x) for x in cur.find_all("td")]
            if len(tds) >= 2:
                trio.append((tds[0], tds[1]))
            cur = cur.find_next_sibling("tr")
        break
    got = []
    for combo, pay in trio:
        mm = re.fullmatch(r"(\d+)-(\d+)-(\d+)", combo)
        pp = re.fullmatch(r"[\d,]+", pay)
        if not mm or not pp:
            out["notes"].append("三連複の行を読めません: %s %s" % (combo, pay))
            continue
        got.append({"combo": sorted(int(x) for x in mm.groups()), "pay": int(pay.replace(",", ""))})
    if not got:
        out["errors"].append("三連複の払戻を読み取れません（不成立・全額返還の可能性。データに加えない）")
        return out
    if "返還" in text and any(k in text for k in ("不成立", "全額返還")):
        out["errors"].append("不成立・全額返還の表示があります（データに加えない）")
        return out
    out["trio"] = got
    # 着順と三連複の組の整合: 各組の馬はすべて3着以内（同着を含む）にいること
    order_of = {f["n"]: k for k, f in enumerate(out["finish"])}
    pos_of = {f["n"]: f["pos"] for f in out["finish"]}
    in3 = {f["n"] for f in top3}
    parts = []
    for g in got:
        if not set(g["combo"]) <= in3:
            out["errors"].append("三連複の組 %s が着順表の3着以内と合いません" % "-".join(map(str, g["combo"])))
            return out
        o = sorted(g["combo"], key=lambda u: (pos_of[u], order_of[u]))
        g["order"] = o
        parts.append("%d-%d-%d/%d円" % (o[0], o[1], o[2], g["pay"]))
    if len(got) == 1 and len(top3) != 3:
        out["errors"].append("3着以内が%d頭なのに三連複の組が1つです" % len(top3))
        return out
    out["result"] = out["race_id"] + "/" + ",".join(parts)
    return out
