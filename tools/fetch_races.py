# -*- coding: utf-8 -*-
"""fetch_races.py  開催日のコード（14桁）から、その日の全レースの出走表・結果ページを取得して .txt で保存する。
GitHub Actions（.github/workflows/fetch-races.yml）から動かす。標準ライブラリだけで動く。

入力（環境変数）
  CODES : 開催日のコード（日付8桁＋会場2桁＋回2桁＋日目2桁）をカンマ・空白・改行区切りで
  KINDS : 「出走表と結果」「出走表のみ」「結果のみ」のどれか（既定は出走表と結果）
  WAIT  : 1回の取得ごとに空ける秒数（既定 2）
使い方: python3 fetch_races.py <出力フォルダ>
出力:
  <出力フォルダ>/出走表/レースID.txt   … /uma_shosai/レースID.do の中身（受け取ったまま、文字コードも変えない）
  <出力フォルダ>/結果/レースID.txt     … /result/レースID.do の中身
  <出力フォルダ>/取得の記録.txt        … 1ページごとの記録（途中で止まっても、そこまでの分が残る）
  <出力フォルダ>/取得報告.txt          … 開催日ごとのレース数・保存数・取れなかったページ
  レースID＝開催日のコード＋レース番号2桁（16桁）
応答の待ち時間は15秒。通信に失敗したページは3回まで取り直す。
通信の失敗（ページなし＝404は除く）が10ページ続いたら、サイトに断られているとみなして打ち切る。
"""
import os, re, sys, time, urllib.request, urllib.error

BASE = "https://www.nankankeiba.com"
VENUE = {"18": "浦和", "19": "船橋", "20": "大井", "21": "川崎"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
WAIT = float(os.environ.get("WAIT", "2") or 2)
TIMEOUT = 15          # 応答を待つ秒数
TRIES = 3             # 1ページを取る回数の上限
STOP_AFTER = 10       # 通信の失敗がこのページ数続いたら打ち切る
KIND_DIR = {"出走表": ("uma_shosai", "出走表"), "結果": ("result", "結果")}
RESULT_WORDS = [w.encode(e) for w in ("払戻", "着順") for e in ("utf-8", "cp932", "euc_jp")]


class Blocked(Exception):
    pass


class Fetcher:
    def __init__(self, logf):
        self.last = 0.0
        self.fail_run = 0
        self.count = 0
        self.logf = logf
        self.t0 = time.time()

    def log(self, text):
        line = "[%s] %s" % (time.strftime("%M:%S", time.gmtime(time.time() - self.t0)), text)
        print(line, flush=True)
        self.logf.write(line + "\n")
        self.logf.flush()

    def get(self, url):
        """(状態, 中身のbytes)。状態は 200・404・その他のHTTPコード・通信エラー名。"""
        err = None
        for i in range(TRIES):
            gap = WAIT - (time.time() - self.last)
            if gap > 0:
                time.sleep(gap)
            self.last = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    body = r.read()
                self.fail_run = 0
                self.count += 1
                return r.status, body
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self.fail_run = 0
                    self.count += 1
                    return 404, None
                err = "HTTP%d" % e.code
            except Exception as e:  # 応答なし・接続できない など
                err = type(e).__name__
            if i < TRIES - 1:
                self.log("  取り直し %d回目（%s）: %s" % (i + 1, err, url))
                time.sleep(3 * (i + 1))
        self.count += 1
        self.fail_run += 1
        if self.fail_run >= STOP_AFTER:
            raise Blocked("通信の失敗が%dページ続いた（最後: %s）" % (self.fail_run, err))
        return err, None


def parse_codes(s):
    codes, bad = [], []
    for t in re.split(r"[\s,、]+", s or ""):
        if not t:
            continue
        if re.fullmatch(r"\d{8}(18|19|20|21)\d{4}", t):
            if t not in codes:
                codes.append(t)
        else:
            bad.append(t)
    return sorted(codes), bad


def race_numbers(code, page):
    """レース一覧ページに出てくる「開催日のコード＋2桁」からレース番号を拾う。"""
    nums = set()
    for m in re.finditer((code + r"(\d{2})").encode(), page or b""):
        n = int(m.group(1))
        if 1 <= n <= 16:
            nums.add(n)
    return sorted(nums)


def ok_page(kind, rid, body):
    if not body or rid.encode() not in body:
        return False
    if kind == "結果":
        return any(w in body for w in RESULT_WORDS)
    return True


def label(code):
    return "%s/%s %s%d回%d日目" % (int(code[4:6]), int(code[6:8]), VENUE.get(code[8:10], code[8:10]), int(code[10:12]), int(code[12:14]))


def why_missing(kind, st):
    if st == 404:
        return "ページなし"
    if st != 200:
        return "取得失敗(%s)" % st
    return "結果が載っていない（未確定の可能性）" if kind == "結果" else "レースIDが載っていない"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "out"
    os.makedirs(out, exist_ok=True)
    codes, bad = parse_codes(os.environ.get("CODES", ""))
    kinds_in = os.environ.get("KINDS", "出走表と結果")
    kinds = {"出走表のみ": ["出走表"], "結果のみ": ["結果"]}.get(kinds_in, ["出走表", "結果"])
    for k in kinds:
        os.makedirs(os.path.join(out, KIND_DIR[k][1]), exist_ok=True)
    logf = open(os.path.join(out, "取得の記録.txt"), "w", encoding="utf-8")
    F = Fetcher(logf)
    F.log("開始: %d日・%s（○保存 ×取れず）" % (len(codes), "・".join(kinds)))

    rep = ["取得報告", "取得するページ: " + "・".join(kinds), "開催日: %d日" % len(codes)]
    if bad:
        rep.append("【読めなかった入力】" + " ".join(bad))
    saved = {k: 0 for k in kinds}
    missing, done, stopped = [], [], None
    try:
        for di, code in enumerate(codes, 1):
            F.log("%d/%d日目 %s（%s）" % (di, len(codes), label(code), code))
            st, page = F.get("%s/program/%s.do" % (BASE, code))
            nums = race_numbers(code, page)
            how = "レース一覧から"
            if not nums:
                how = "レース一覧から読めず、1Rから順に試した"
                nums = list(range(1, 13))
                F.log("  レース一覧を読めず（%s）。1Rから順に試します" % st)
            else:
                F.log("  %dレース" % len(nums))
            line = {k: 0 for k in kinds}
            tried = 0
            for n in nums:
                rid = "%s%02d" % (code, n)
                got, marks, miss_here = False, [], []
                for k in kinds:
                    path, folder = KIND_DIR[k]
                    st, body = F.get("%s/%s/%s.do" % (BASE, path, rid))
                    if ok_page(k, rid, body):
                        with open(os.path.join(out, folder, rid + ".txt"), "wb") as f:
                            f.write(body)
                        line[k] += 1
                        saved[k] += 1
                        got = True
                        marks.append("%s○" % k)
                    else:
                        w = why_missing(k, st)
                        miss_here.append("%s %s: %s" % (rid, k, w))
                        marks.append("%s×(%s)" % (k, w))
                if how != "レース一覧から" and not got:
                    if n == 1:
                        missing += miss_here
                    else:
                        missing += [x for x in miss_here if "取得失敗" in x]
                    if n == 1:
                        F.log("  1R %s → この日は取れず" % " ".join(marks))
                    else:
                        F.log("  %dR: 取れないのでこの日は%dRまで" % (n, n - 1))
                    break  # 1Rから試している場合、取れなくなったところで終わり
                F.log("  %dR %s" % (n, " ".join(marks)))
                missing += miss_here
                tried += 1
            done.append(code)
            rep.append("%s（%s）: %dレース（%s） 保存 %s" % (
                label(code), code, tried, how, "・".join("%s %d" % (k, line[k]) for k in kinds)))
    except Blocked as e:
        stopped = str(e)
        F.log("【打ち切り】" + stopped)

    rep.append("")
    if stopped:
        rep.append("【打ち切り】%s。サイトに断られている可能性があります。" % stopped)
    redo = [c for c in codes if c not in done or any(x.startswith(c) and "取得失敗" in x for x in missing)]
    if redo:
        rep.append("取り直しが必要な開催日（%d日。通信の失敗があった日と、打ち切りで取っていない日）: %s" % (len(redo), ",".join(redo)))
    rep.append("保存したファイル: " + "・".join("%s %d件" % (k, saved[k]) for k in kinds))
    rep.append("取れなかったページ: %d件" % len(missing))
    rep += ["  " + x for x in missing]
    rep.append("取得したページ数: %d（%d分%d秒）" % (F.count, (time.time() - F.t0) // 60, (time.time() - F.t0) % 60))
    text = "\n".join(rep) + "\n"
    with open(os.path.join(out, "取得報告.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    F.log("終了")
    logf.close()
    print("\n" + text, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("```\n" + text + "```\n")
    if os.environ.get("GITHUB_OUTPUT") and codes:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("name=races_%s-%s_%ddays\n" % (codes[0][:8], codes[-1][:8], len(codes)))
    return 0 if sum(saved.values()) and not stopped else 1


if __name__ == "__main__":
    sys.exit(main())
