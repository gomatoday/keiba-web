# -*- coding: utf-8 -*-
"""odds_html.py  オッズ入りの出走表（nankankeiba.com の出走表を、オッズが表示された状態で保存したもの）から、全馬の単勝・複勝のオッズと人気を読む。
想定オッズ帯の検討用（次の版の検討。v4.9 の分析・考察・判定には使わない）。標準のPython＋beautifulsoup4 で書く。
  読む場所: 詳しい出走表の「オッズ」欄（td.cs-odds）。各馬の欄は
      <script>writeOddsForMY(馬番);</script><span>単勝</span><span>(人気)</span>
      <script>writeFukuOddsForMY(馬番);</script><span>複勝の下限-上限</span><span>(人気)</span>
    の形。馬番はスクリプトの引数から取る（見本の行など、スクリプトのない欄は読まない）。
  オッズの時点: id="oddsUpdateTime" の文字（「最終オッズ」または「MM/DD HH:MM現在」など）をそのまま記録する。
  blank_odds(): 同じHTMLからオッズの値だけを消した文字列を返す（分析計算がオッズの欄を読まないことの確認に使う）。"""
import re
from bs4 import BeautifulSoup

VERSION = "odds_html 1"
_NUM = re.compile(r"^\d+(\.\d+)?$")


def _clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def _spans_after(script):
    out = []
    for sib in script.next_siblings:
        name = getattr(sib, "name", None)
        if name == "span":
            out.append(_clean(sib.get_text()))
        elif name == "script":
            break
    return out


def _float(s):
    return float(s) if s and _NUM.match(s) else None


def _pop(s):
    m = re.search(r"(\d+)\s*人", s or "")
    return int(m.group(1)) if m else None


def parse(raw_bytes, decode_html):
    """戻り値: {"race_id", "status"（オッズの時点の文字）, "odds": {馬番: {...}}, "n", "errors"}。
    1頭の値: tan（単勝。数値でなければ None）・tan_pop・fuku_lo・fuku_hi・fuku_pop・tan_raw・fuku_raw（読んだ文字のまま。取消などの確認用）。"""
    s, enc = decode_html(raw_bytes)
    out = {"race_id": None, "status": None, "odds": {}, "n": 0, "errors": [], "encoding": enc}
    if s is None:
        out["errors"].append("文字コードを判定できません")
        return out
    m = re.search(r'id="_cc_proId"\s+value="(\d+)"', s)
    out["race_id"] = m.group(1) if m else None
    if not out["race_id"]:
        out["errors"].append("レースIDを読めません")
    try:
        soup = BeautifulSoup(s, "lxml")
    except Exception:
        soup = BeautifulSoup(s, "html.parser")
    ut = soup.select_one("#oddsUpdateTime")
    if ut:
        for sc in ut.find_all("script"):
            sc.extract()
        out["status"] = _clean(ut.get_text(" ")) or None
    od = {}
    for sc in soup.find_all("script"):
        t = sc.string or ""
        mt = re.search(r"write(Fuku)?OddsForMY\((\d+)\)", t)
        if not mt:
            continue
        num = int(mt.group(2))
        sp = _spans_after(sc)
        h = od.setdefault(num, {"tan": None, "tan_pop": None, "fuku_lo": None, "fuku_hi": None, "fuku_pop": None, "tan_raw": None, "fuku_raw": None})
        if mt.group(1):
            if h["fuku_raw"] is not None:
                continue
            raw = sp[0] if sp else ""
            h["fuku_raw"] = raw
            mm = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$", raw)
            if mm:
                h["fuku_lo"], h["fuku_hi"] = float(mm.group(1)), float(mm.group(2))
            h["fuku_pop"] = _pop(sp[1]) if len(sp) > 1 else None
        else:
            if h["tan_raw"] is not None:
                continue
            raw = sp[0] if sp else ""
            h["tan_raw"] = raw
            h["tan"] = _float(raw)
            h["tan_pop"] = _pop(sp[1]) if len(sp) > 1 else None
    out["odds"] = {str(k): od[k] for k in sorted(od)}
    out["n"] = sum(1 for v in od.values() if v["tan"] is not None)
    if not od:
        out["errors"].append("オッズの欄が見つかりません")
    elif out["n"] == 0:
        out["errors"].append("オッズの値がありません（オッズが出る前に保存したページの可能性）")
    return out


_BLANK = [
    # 詳しい出走表: スクリプトの直後の <span>値</span><span>(人気)</span>
    (re.compile(r"(write(?:Fuku)?OddsForMY\(\d+\);\s*</script>)\s*<span[^>]*>[^<]*</span>\s*<span[^>]*>[^<]*</span>"), r"\1"),
    # 簡易の表: writeOdds(n); の直後の <span>値</span>、またはスクリプトの直後の文字
    (re.compile(r"(writeOdds\(\d+\);\s*</script>)\s*<span[^>]*>[^<]*</span>"), r"\1"),
    (re.compile(r"(writeOdds\(\d+\);\s*</script>)[^<]+"), r"\1"),
    # オッズの時点の文字
    (re.compile(r'(<div id="oddsUpdateTime"[^>]*>\s*<script[^>]*>[^<]*</script>)[^<]*'), r"\1"),
]


def blank_odds(raw_bytes, decode_html):
    """オッズの値（単勝・複勝・人気・時点）だけを消したHTMLの文字列。読めないときは None。"""
    s, _ = decode_html(raw_bytes)
    if s is None:
        return None
    for pat, rep in _BLANK:
        s = pat.sub(rep, s)
    return s
