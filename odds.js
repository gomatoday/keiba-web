// オッズ入り出走表の抽出画面。計算は keiba_v49.py（分析）・result_v49.py（結果ページ）・odds_html.py（オッズ）が行う。このファイルは受け渡しだけを行う。
// v4.9 の記録（IndexedDB の keiba_v49）には読み書きしない。レースの選び方・分け方には関わらない（選ばれたファイルをすべて読む）。
"use strict";

const $ = (id) => document.getElementById(id);
let ROWS = [];
let META = null;

function setStatus(msg, cls) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status " + (cls || "");
}

function oddsCall(fn, ...args) {
  const f = KEIBA.py.globals.get("odds_runner")[fn];
  const r = f(...args);
  if (typeof f.destroy === "function") f.destroy();
  return JSON.parse(r);
}

async function init() {
  $("footer").textContent = footerText(null);
  try {
    const info = await keibaInit(setStatus);
    const py = KEIBA.py;
    for (const name of Object.keys(ODDS_BUNDLE.files)) py.FS.writeFile("/app/" + name, b64ToBytes(ODDS_BUNDLE.files[name]));
    py.runPython("import odds_runner");
    const oi = oddsCall("info");
    const V = ODDS_BUNDLE.version;
    if (oi.code_odds !== V.code_odds || oi.code_odds_runner !== V.code_odds_runner) {
      throw new Error("オッズの読み取りの指紋が違います（実行=" + oi.code_odds + "・" + oi.code_odds_runner + "、正本=" + V.code_odds + "・" + V.code_odds_runner + "）。");
    }
    KEIBA.oddsInfo = oi;
    $("footer").textContent = footerText(info) + " ／ オッズの読み取り " + oi.code_odds + "・" + oi.code_odds_runner;
    setStatus("準備ができました。名前を入れて、ファイルを選んでください。", "ok");
    updateButton();
  } catch (e) {
    setStatus("停止: " + e.message, "err");
  }
}

function updateButton() {
  $("run").disabled = !(KEIBA.py && $("label").value.trim() && $("cards").files.length && $("results").files.length);
}
["label", "cards", "results"].forEach((id) => $(id).addEventListener(id === "label" ? "input" : "change", updateButton));

const tick = () => new Promise((ok) => setTimeout(ok, 10));

$("run").addEventListener("click", async () => {
  const label = $("label").value.trim();
  const cards = Array.from($("cards").files);
  const results = Array.from($("results").files);
  const checkBlank = $("blank").checked;
  $("run").disabled = true;
  $("done").classList.add("hidden");
  const started = new Date();
  const C = {}, R = {}, dupC = [], dupR = [], badC = [], badR = [];
  try {
    for (let k = 0; k < cards.length; k++) {
      setStatus("出走表 " + (k + 1) + "／" + cards.length + " を読んでいます…（" + cards[k].name + "）");
      await tick();
      let r;
      try {
        await keibaWriteFile("/work/odds_card.html", cards[k]);
        r = oddsCall("card", "/work/odds_card.html", checkBlank);
      } catch (e) {
        badC.push(cards[k].name + "（" + e.message + "）");
        continue;
      }
      r.file = cards[k].name;
      if (!r.race_id) { badC.push(cards[k].name + "（レースIDを読めません）"); continue; }
      if (C[r.race_id]) { dupC.push(r.race_id + "（" + C[r.race_id].file + " と " + r.file + "）"); continue; }
      C[r.race_id] = r;
    }
    for (let k = 0; k < results.length; k++) {
      setStatus("結果ページ " + (k + 1) + "／" + results.length + " を読んでいます…（" + results[k].name + "）");
      await tick();
      let r;
      try {
        await keibaWriteFile("/work/odds_result.html", results[k]);
        r = oddsCall("result", "/work/odds_result.html");
      } catch (e) {
        badR.push(results[k].name + "（" + e.message + "）");
        continue;
      }
      r.file = results[k].name;
      if (!r.race_id) { badR.push(results[k].name + "（レースIDを読めません: " + (r.errors || []).join("、") + "）"); continue; }
      if (R[r.race_id]) { dupR.push(r.race_id + "（" + R[r.race_id].file + " と " + r.file + "）"); continue; }
      R[r.race_id] = r;
    }
  } catch (e) {
    setStatus("停止: " + e.message, "err");
    $("run").disabled = false;
    return;
  }
  const ids = Array.from(new Set(Object.keys(C).concat(Object.keys(R)))).sort();
  ROWS = ids.map((id) => {
    const c = C[id], r = R[id];
    const heads = c && c.rec ? c.rec.nums.length : null;
    const o = c ? c.odds : null;
    const issues = [];
    if (!c) issues.push("出走表なし");
    if (!r) issues.push("結果なし");
    if (c && c.analysis !== "通常") issues.push("分析=" + c.analysis);
    if (c && c.blank === "不一致") issues.push("オッズを消すと分析が変わる");
    if (o && o.errors.length) issues.push(o.errors.join("、"));
    if (o && heads && o.n !== heads) issues.push("オッズの頭数" + o.n + "≠出走" + heads);
    if (o && o.status && o.status.indexOf("最終オッズ") < 0) issues.push("最終オッズではない（" + o.status + "）");
    if (r && (r.errors || []).length) issues.push("結果: " + r.errors.join("、"));
    if (r && r.res && !r.res.pop) issues.push("全馬の人気なし");
    return {
      race_id: id, label: label, card_file: c ? c.file : null, result_file: r ? r.file : null,
      analysis: c ? c.analysis : null, rc: c ? c.rc : null, note: c ? c.note : null, blank: c ? c.blank : null,
      odds_status: o ? o.status : null, odds_n: o ? o.n : null, heads: heads,
      ok: issues.length === 0, issues: issues,
      rec: c ? c.rec : null, odds: o ? o.odds : null,
      result: r ? { res: r.res, errors: r.errors, notes: r.notes } : null,
    };
  });
  const n = ROWS.length, nok = ROWS.filter((x) => x.ok).length;
  META = {
    kind: "odds-extract", format_ver: 1, label: label, created_at: new Date().toISOString(), seconds: Math.round((new Date() - started) / 1000),
    files_cards: cards.length, files_results: results.length, races: n, races_ok: nok, blank_checked: checkBlank,
    dup_cards: dupC, dup_results: dupR, unread_cards: badC, unread_results: badR,
    version: BUNDLE.version.version, code: KEIBA.info.code, code_k: KEIBA.info.code_k, code_m: KEIBA.info.code_m, code_p: KEIBA.info.code_p,
    code_a47: KEIBA.info.code_a47, code_f: KEIBA.info.code_f, code_m48: KEIBA.info.code_m48, code_p48: KEIBA.info.code_p48,
    code_odds: KEIBA.oddsInfo.code_odds, code_odds_runner: KEIBA.oddsInfo.code_odds_runner, pyodide: KEIBA.info.pyodide, python: KEIBA.info.python,
  };
  showResult();
  setStatus("終わりました。" + n + "レース（問題なし " + nok + "）。下の「抽出ファイルを保存」で保存してください。", nok === n ? "ok" : "");
  $("run").disabled = false;
});

function showResult() {
  const M = META;
  const cnt = (f) => ROWS.filter(f).length;
  const items = [
    ["名前", M.label], ["選んだ出走表", M.files_cards + "件"], ["選んだ結果ページ", M.files_results + "件"], ["レース（どちらかがあるもの）", M.races],
    ["問題なし", M.races_ok], ["分析が通常モード", cnt((x) => x.analysis === "通常")], ["最終オッズ", cnt((x) => x.odds_status && x.odds_status.indexOf("最終オッズ") >= 0)],
    ["オッズを消しても分析が同じ", M.blank_checked ? cnt((x) => x.blank === "一致") : "確かめていない"], ["かかった時間", M.seconds + "秒"],
  ];
  let h = "<dl class='sum'>" + items.map(([k, v]) => "<div><dt>" + escapeHtml(k) + "</dt><dd>" + escapeHtml(String(v)) + "</dd></div>").join("") + "</dl>";
  const warn = [];
  if (M.dup_cards.length) warn.push("同じレースの出走表が2件以上（2件目以降は使っていません）: " + M.dup_cards.join(" ／ "));
  if (M.dup_results.length) warn.push("同じレースの結果ページが2件以上（2件目以降は使っていません）: " + M.dup_results.join(" ／ "));
  if (M.unread_cards.length) warn.push("読めない出走表: " + M.unread_cards.join(" ／ "));
  if (M.unread_results.length) warn.push("読めない結果ページ: " + M.unread_results.join(" ／ "));
  if (warn.length) h += "<div class='warn'><ul>" + warn.map((w) => "<li>" + escapeHtml(w) + "</li>").join("") + "</ul></div>";
  $("summary").innerHTML = h;
  let t = "<tr><th>レースID</th><th>分析</th><th>頭数</th><th>オッズ</th><th>オッズの時点</th><th>オッズを消した確認</th><th>結果</th><th>問題</th></tr>";
  for (const x of ROWS) {
    t += "<tr" + (x.ok ? "" : " class='fail'") + "><td>" + x.race_id + "</td><td>" + escapeHtml(x.analysis || "-") + "</td><td>" + (x.heads || "-") +
      "</td><td>" + (x.odds_n == null ? "-" : x.odds_n + "頭") + "</td><td>" + escapeHtml(x.odds_status || "-") + "</td><td>" + escapeHtml(x.blank || "-") +
      "</td><td>" + (x.result && x.result.res ? "読めた" : (x.result ? "読めない" : "なし")) + "</td><td>" + escapeHtml(x.issues.join("、") || "") + "</td></tr>";
  }
  $("tbl").innerHTML = t;
  $("done").classList.remove("hidden");
}

function safeName(s) {
  return s.replace(/[\\/:*?"<>|\s]+/g, "_");
}

$("save").addEventListener("click", () => {
  const lines = ["ODDSMETA " + JSON.stringify(META)].concat(ROWS.map((x) => "ODDSRACE " + JSON.stringify(x)));
  downloadText("odds_" + safeName(META.label) + "_" + ROWS.length + "races.txt", lines.join("\n") + "\n");
});

$("savecsv").addEventListener("click", () => {
  const q = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
  const head = ["レースID", "出走表のファイル", "結果ページのファイル", "分析", "頭数", "オッズの頭数", "オッズの時点", "オッズを消した確認", "問題"];
  const body = ROWS.map((x) => [x.race_id, x.card_file, x.result_file, x.analysis, x.heads, x.odds_n, x.odds_status, x.blank, x.issues.join("、")].map(q).join(","));
  downloadText("odds_" + safeName(META.label) + "_一覧.csv", "﻿" + [head.map(q).join(",")].concat(body).join("\r\n") + "\r\n");
});

init();
