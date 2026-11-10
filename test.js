// 一致テスト画面：正解データ（PC版Pythonの出力）とブラウザでの実行結果を比べる。
"use strict";

const $ = (id) => document.getElementById(id);
let report = null;

function setStatus(msg, cls) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status " + (cls || "");
}
$("footer").textContent = footerText(null);

const idOf = (name) => (name.match(/(\d{16})/) || [])[1];

async function runTests() {
  const golds = Array.from($("gold").files).filter((f) => idOf(f.name));
  const inps = new Map(Array.from($("inp").files).map((f) => [idOf(f.name), f]));
  if (!golds.length || !inps.size) {
    setStatus("正解データと出走表HTMLを両方選んでください。", "err");
    return;
  }
  golds.sort((a, b) => a.name.localeCompare(b.name));
  $("run").disabled = true;
  const rows = [];
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>レースID</th><th>判定</th><th>出力全文</th><th>REC</th><th>終了コード</th><th>差の内容</th></tr>";
  $("resbox").classList.remove("hidden");
  for (let k = 0; k < golds.length; k++) {
    const g = golds[k];
    const id = idOf(g.name);
    setStatus("テスト中 " + (k + 1) + "/" + golds.length + "（" + id + "）…");
    await new Promise((ok) => setTimeout(ok, 30));
    let r;
    const inp = inps.get(id);
    if (!inp) {
      r = { race_id: id, ok: false, error: "対応する出走表HTMLがありません" };
    } else {
      try {
        await keibaWriteFile("/work/test.html", inp);
        r = keibaCall("golden_check", "/work/test.html", await g.text());
      } catch (e) {
        r = { race_id: id, ok: false, error: e.message };
      }
    }
    rows.push(r);
    const diff = r.error || (r.first_stdout_diff ? (r.first_stdout_diff.line + "行目 Web: " + r.first_stdout_diff.web + " ／ Python: " + r.first_stdout_diff.python) : "");
    tbl.insertAdjacentHTML("beforeend", "<tr class='" + (r.ok ? "pass" : "fail") + "'><td>" + escapeHtml(id) + "</td><td>" + (r.ok ? "一致" : "不一致") +
      "</td><td>" + (r.stdout_same ? "○" : "×") + "</td><td>" + (r.rec_same ? "○" : "×") + "</td><td>" + (r.rc_same ? "○" : "×") + "</td><td>" + escapeHtml(diff) + "</td></tr>");
  }
  const pass = rows.filter((r) => r.ok).length;
  const allOk = pass === rows.length;
  report = { test: "v49_bunseki", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: rows.length, pass: pass, all_ok: allOk, results: rows };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：全" + rows.length + "レースがPython版と一致" : "不合格：" + (rows.length - pass) + "レースが不一致（Web版は実運用しない）") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("テスト完了（一致 " + pass + "/" + rows.length + "）。", allOk ? "ok" : "err");
  $("run").disabled = false;
}

$("run").addEventListener("click", runTests);

async function runKosatsuTests() {
  const golds = Array.from($("goldk").files).sort((a, b) => a.name.localeCompare(b.name));
  if (!golds.length) {
    setStatus("考察の正解データを選んでください。", "err");
    return;
  }
  $("runk").disabled = true;
  const rows = [];
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>レースID</th><th>内容</th><th>結果</th><th>判定</th><th>終了コード</th><th>差の内容</th></tr>";
  $("resbox").classList.remove("hidden");
  for (let k = 0; k < golds.length; k++) {
    setStatus("考察のテスト中 " + (k + 1) + "/" + golds.length + "…");
    await new Promise((ok) => setTimeout(ok, 20));
    let r;
    try {
      r = keibaCall("kosatsu_check", await golds[k].text());
    } catch (e) {
      r = { race_id: golds[k].name, ok: false, error: e.message };
    }
    rows.push(r);
    const diff = r.error || (r.first_stdout_diff ? r.first_stdout_diff.line + "行目 Web: " + r.first_stdout_diff.web + " ／ Python: " + r.first_stdout_diff.python : "");
    tbl.insertAdjacentHTML("beforeend", "<tr class='" + (r.ok ? "pass" : "fail") + "'><td>" + escapeHtml(r.race_id) + "</td><td>" + escapeHtml(r.kind || "") +
      "</td><td>" + escapeHtml(r.result || "") + "</td><td>" + (r.ok ? "一致" : "不一致") + "</td><td>" + (r.rc_same ? "○" : "×") + "</td><td>" + escapeHtml(diff) + "</td></tr>");
  }
  const pass = rows.filter((r) => r.ok).length;
  const allOk = pass === rows.length;
  report = { test: "v49_kosatsu", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: rows.length, pass: pass, all_ok: allOk, results: rows };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：考察" + rows.length + "件がPython版と一致" : "不合格：" + (rows.length - pass) + "件が不一致") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("考察のテスト完了（一致 " + pass + "/" + rows.length + "）。", allOk ? "ok" : "err");
  $("runk").disabled = false;
}
$("runk").addEventListener("click", runKosatsuTests);

async function runStoreTests() {
  const files = Array.from($("gold3").files).sort((a, b) => a.name.localeCompare(b.name));
  if (!files.length) { setStatus("考察の正解データを選んでください。", "err"); return; }
  $("run3").disabled = true;
  const checks = [];
  const add = (name, ok, note) => checks.push({ name, ok: !!ok, note: note || "" });
  try {
    await storeInit("keiba_v49_test");
    await storeClear();
    const gs = [];
    for (const f of files) {
      const g = JSON.parse(await f.text());
      if (g.rc === 0 && (g.kind === "通常" || g.kind === "新馬")) gs.push(g);
    }
    setStatus("記録のテスト中（" + gs.length + "件）…");
    let a1 = 0, k1 = 0;
    for (const g of gs) {
      const s1 = await storeSaveAnalysis(g.bunseki_stdout); a1 += s1.saved ? 1 : 0;
      const s2 = await storeSaveKosatsu(g.bunseki_stdout, g.result, g.kosatsu_stdout); k1 += s2.saved ? 1 : 0;
    }
    add("分析と結果の記録", a1 === gs.length && k1 === gs.length, "分析 " + a1 + "件・結果 " + k1 + "件／" + gs.length);
    const dup = await storeSaveKosatsu(gs[0].bunseki_stdout, gs[0].result, gs[0].kosatsu_stdout);
    add("同じレースの二重登録を拒否", !dup.saved, dup.reason);
    const dupA = await storeSaveAnalysis(gs[0].bunseki_stdout);
    add("結果登録済みのレースの分析を上書きしない", !dupA.saved, dupA.reason);
    const before = (await storeAll()).sort((a, b) => a.race_id.localeCompare(b.race_id));
    const bk = await storeBackupObject();
    const text = JSON.stringify(bk);
    add("バックアップの検査", backupCheck(JSON.parse(text)).length === 0, "記録 " + bk.count + "件");
    await storeClear();
    add("全消去", (await storeAll()).length === 0);
    const rs = await storeRestore(JSON.parse(text));
    const after = (await storeAll()).sort((a, b) => a.race_id.localeCompare(b.race_id));
    add("復元で全件が戻る", rs.ok && rs.added === before.length && JSON.stringify(after) === JSON.stringify(before), "追加 " + rs.added + "件");
    const rs2 = await storeRestore(JSON.parse(text));
    add("同じバックアップの再復元は何も変えない", rs2.ok && rs2.added === 0 && rs2.same === before.length && rs2.conflict.length === 0);
    const lines = after.map((r) => r.kosatsu_stdout.split("\n").find((l) => l.startsWith("LEDGER ")));
    const lc = keibaCall("ledger_check", lines.join("\n") + "\n");
    add("復元後のLEDGER行を考察計算で照合", lc.ok && lc.n === gs.length, lc.ok ? lc.n + "件" : lc.error);
    const g0 = gs[0];
    const same = after[0].kosatsu_stdout === gs.slice().sort((a, b) => a.race_id.localeCompare(b.race_id))[0].kosatsu_stdout;
    add("記録した考察出力が正解データと1文字も違わない", same);
    const bad1 = JSON.parse(text); bad1.races.push(bad1.races[0]); bad1.count++;
    add("レースIDの重複したバックアップを拒否", backupCheck(bad1).length > 0);
    const bad2 = JSON.parse(text); bad2.count = 1;
    add("件数の合わないバックアップを拒否", backupCheck(bad2).length > 0);
    const bad3 = JSON.parse(text); bad3.races[0].kosatsu_stdout = bad3.races[1].kosatsu_stdout;
    add("中身のレースIDが違う記録を拒否", backupCheck(bad3).length > 0);
    const bad4 = JSON.parse(text); bad4.format = "other";
    add("形式の違うファイルを拒否", backupCheck(bad4).length > 0);
    const lines2 = lines.concat([lines[0]]);
    const lc2 = keibaCall("ledger_check", lines2.join("\n") + "\n");
    add("LEDGER行の重複を照合で停止", !lc2.ok, lc2.error || "");
    const conf = JSON.parse(text); conf.races[0].result = "x"; conf.races[0].kosatsu_stdout = conf.races[0].kosatsu_stdout.replace("【考察", "【考察 ");
    const rs3 = await storeRestore(conf);
    add("内容の違う記録は上書きしない", rs3.ok && rs3.conflict.length === 1 && (await storeGet(conf.races[0].race_id)).kosatsu_stdout === before[0].kosatsu_stdout);
    await storeClear();
    void g0;
  } catch (e) {
    add("テストの実行", false, e.message);
  }
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>確認項目</th><th>判定</th><th>内容</th></tr>" + checks.map((c) => "<tr class='" + (c.ok ? "pass" : "fail") + "'><td>" + escapeHtml(c.name) +
    "</td><td>" + (c.ok ? "OK" : "NG") + "</td><td>" + escapeHtml(c.note) + "</td></tr>").join("");
  $("resbox").classList.remove("hidden");
  const allOk = checks.every((c) => c.ok);
  report = { test: "v49_store", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: checks.length, pass: checks.filter((c) => c.ok).length, all_ok: allOk, results: checks };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：記録とバックアップの確認 " + checks.length + "項目がすべてOK" : "不合格：NGの項目があります") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("記録のテスト完了。", allOk ? "ok" : "err");
  $("run3").disabled = false;
}
$("run3").addEventListener("click", runStoreTests);

async function runAggTests() {
  const golds = Array.from($("golda").files).sort((a, b) => a.name.localeCompare(b.name));
  if (!golds.length) { setStatus("集計の正解データを選んでください。", "err"); return; }
  $("runa").disabled = true;
  const rows = [];
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>ケース</th><th>判定</th><th>終了コード</th><th>差の内容</th></tr>";
  $("resbox").classList.remove("hidden");
  for (let k = 0; k < golds.length; k++) {
    setStatus("集計のテスト中 " + (k + 1) + "/" + golds.length + "…（1件に1分ほどかかることがあります）");
    await new Promise((ok) => setTimeout(ok, 30));
    let r;
    try { r = keibaCall("aggregate_check", await golds[k].text()); } catch (e) { r = { race_id: golds[k].name, ok: false, error: e.message }; }
    rows.push(r);
    const diff = r.error || (r.first_stdout_diff ? r.first_stdout_diff.line + "行目 Web: " + r.first_stdout_diff.web + " ／ Python: " + r.first_stdout_diff.python : "");
    tbl.insertAdjacentHTML("beforeend", "<tr class='" + (r.ok ? "pass" : "fail") + "'><td>" + escapeHtml(r.race_id) + "</td><td>" + (r.ok ? "一致" : "不一致") +
      "</td><td>" + (r.rc_same ? "○" : "×") + "</td><td>" + escapeHtml(diff) + "</td></tr>");
  }
  const pass = rows.filter((r) => r.ok).length;
  const allOk = pass === rows.length;
  report = { test: "v49_aggregate", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: rows.length, pass: pass, all_ok: allOk, results: rows };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：集計" + rows.length + "件がPython版と一致" : "不合格：" + (rows.length - pass) + "件が不一致") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("集計のテスト完了（一致 " + pass + "/" + rows.length + "）。", allOk ? "ok" : "err");
  $("runa").disabled = false;
}
$("runa").addEventListener("click", runAggTests);

async function runResultTests() {
  const golds = Array.from($("goldr").files).sort((a, b) => a.name.localeCompare(b.name));
  const inps = new Map(Array.from($("inpr").files).map((f) => [f.name, f]));
  if (!golds.length || !inps.size) { setStatus("正解データと結果ページを両方選んでください。", "err"); return; }
  $("runr").disabled = true;
  const rows = [];
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>レースID</th><th>判定</th><th>Web</th><th>Python</th></tr>";
  $("resbox").classList.remove("hidden");
  for (const gf of golds) {
    const g = JSON.parse(await gf.text());
    const f = inps.get(g.file);
    let r;
    if (!f) r = { race_id: g.parse.race_id, ok: false, web: "結果ページ " + g.file + " がありません" };
    else {
      try { await keibaWriteFile("/work/result_test.html", f); r = keibaCall("result_check", "/work/result_test.html", JSON.stringify(g)); }
      catch (e) { r = { race_id: g.parse.race_id, ok: false, web: e.message }; }
    }
    rows.push(r);
    tbl.insertAdjacentHTML("beforeend", "<tr class='" + (r.ok ? "pass" : "fail") + "'><td>" + escapeHtml(r.race_id) + "</td><td>" + (r.ok ? "一致" : "不一致") +
      "</td><td>" + escapeHtml(r.web || "") + "</td><td>" + escapeHtml(r.python || "") + "</td></tr>");
  }
  const pass = rows.filter((r) => r.ok).length;
  const allOk = pass === rows.length;
  report = { test: "result_parse", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: rows.length, pass: pass, all_ok: allOk, results: rows };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：読み取り" + rows.length + "件がPython版と一致" : "不合格：" + (rows.length - pass) + "件が不一致") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("読み取りのテスト完了（一致 " + pass + "/" + rows.length + "）。", allOk ? "ok" : "err");
  $("runr").disabled = false;
}
$("runr").addEventListener("click", runResultTests);

async function runBulkTests() {
  const golds = new Map();
  for (const f of Array.from($("gold").files)) { const id = idOf(f.name); if (id) golds.set(id, f); }
  const inps = Array.from($("inp").files).filter((f) => idOf(f.name)).sort((a, b) => a.name.localeCompare(b.name));
  if (!golds.size || !inps.length) { setStatus("一番上の欄で、expected のJSONと input のファイルを選んでください。", "err"); return; }
  $("runb").disabled = true;
  await storeInit("keiba_v49_test");
  await storeClear();
  const tbl = $("tbl");
  tbl.innerHTML = "<tr><th>レースID</th><th>判定</th><th>状態</th><th>差の内容</th></tr>";
  $("resbox").classList.remove("hidden");
  const rows = await bulkAnalyze(inps, (k, n) => setStatus("まとめて分析のテスト中 " + k + "/" + n + "…"), { keepStdout: true });
  const out = [];
  for (const r of rows) {
    const id = idOf(r.file);
    let ok = false, note = "";
    const gf = golds.get(id);
    if (!gf) note = "正解データがありません";
    else {
      const g = JSON.parse(await gf.text());
      const st = await storeGet(id);
      if (r.stdout !== g.stdout) note = "出力が正解データと違います";
      else if (!g.rec) {
        // 見送り（REC行なし）: 記録しないのが正しい
        if (st) note = "見送りのレースが記録されています";
        else if (r.status !== "見送り・買い目なし") note = r.status;
        else ok = true;
      }
      else if (!st || st.bunseki_stdout !== g.stdout) note = "記録が正解データと違います";
      else if (r.status !== "記録しました") note = r.status;
      else ok = true;
    }
    out.push({ race_id: id, ok, note });
    tbl.insertAdjacentHTML("beforeend", "<tr class='" + (ok ? "pass" : "fail") + "'><td>" + escapeHtml(id) + "</td><td>" + (ok ? "一致" : "不一致") + "</td><td>" + escapeHtml(r.status) + "</td><td>" + escapeHtml(note) + "</td></tr>");
  }
  await storeClear();
  const pass = out.filter((r) => r.ok).length;
  const allOk = pass === out.length;
  report = { test: "bulk_analyze", tested_at: new Date().toISOString(), env: KEIBA.info, user_agent: navigator.userAgent, races: out.length, pass: pass, all_ok: allOk, results: out };
  $("verdict").innerHTML = "<h2>" + (allOk ? "合格：まとめて分析" + out.length + "件が正解データと一致" : "不合格：" + (out.length - pass) + "件が不一致") + "</h2>";
  $("verdict").className = allOk ? "ok" : "err";
  setStatus("まとめて分析のテスト完了（一致 " + pass + "/" + out.length + "）。", allOk ? "ok" : "err");
  $("runb").disabled = false;
}
$("runb").addEventListener("click", runBulkTests);
$("save").addEventListener("click", () => {
  if (report) downloadText("v4.9_" + ({ v49_bunseki: "分析", v49_kosatsu: "考察", v49_store: "記録", v49_aggregate: "集計", result_parse: "読み取り", bulk_analyze: "まとめて分析" }[report.test] || "") + "テスト結果.json", JSON.stringify(report, null, 1));
});

keibaInit((m) => setStatus(m))
  .then((info) => {
    $("footer").textContent = footerText(info);
    setStatus("準備ができました。ファイルを選んで「テスト開始」を押してください。", "ok");
    $("run").disabled = false;
    $("runk").disabled = false;
    $("run3").disabled = false;
    $("runa").disabled = false;
    $("runr").disabled = false;
    $("runb").disabled = false;
  })
  .catch((e) => setStatus("起動できません: " + e.message, "err"));
