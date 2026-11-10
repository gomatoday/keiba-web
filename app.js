// 分析画面：HTMLを読み込み、keiba_v49.py の predict を実行して、出力をそのまま表示する。
"use strict";

const $ = (id) => document.getElementById(id);
let lastOut = null;
let lastId = null;

function setStatus(msg, cls) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status " + (cls || "");
}

for (let r = 1; r <= 12; r++) {
  const o = document.createElement("option");
  o.value = String(r);
  o.textContent = r + "R";
  $("rno").appendChild(o);
}
$("footer").textContent = footerText(null);

function showSummary(res) {
  const box = $("summary");
  const rec = res.rec;
  if (!rec) {
    box.classList.add("hidden");
    return;
  }
  const id = rec.race_id || "";
  const d = id.slice(0, 8);
  const plans = rec.plans || {};
  const plan = (k) => (rec.mode === "通常" ? ((plans[k] || []).length ? plans[k].length + "点" : "見送り") : "-");
  const items = [
    ["開催日", d ? d.slice(0, 4) + "/" + d.slice(4, 6) + "/" + d.slice(6, 8) : "-"],
    ["会場", rec.venue],
    ["R", id ? Number(id.slice(-2)) + "R" : "-"],
    ["距離", rec.dist + "m"],
    ["頭数", rec.heads + "頭"],
    ["分析モード", rec.mode],
    ["案A（予測1位の単勝）", plan("案A")],
    ["案B（複勝 期待値0.9以上）", plan("案B")],
    ["案C（予測1位の複勝）", plan("案C")],
  ];
  let h = "<h2>概要</h2><dl class='sum'>";
  for (const [k, v] of items) h += "<div><dt>" + escapeHtml(k) + "</dt><dd>" + escapeHtml(v) + "</dd></div>";
  h += "</dl>";
  const w = rec.warnings || [];
  if (w.length) h += "<div class='warn'><strong>警告</strong><ul>" + w.map((x) => "<li>" + escapeHtml(x) + "</li>").join("") + "</ul></div>";
  box.innerHTML = h;
  box.classList.remove("hidden");
}

async function run() {
  const f = $("html").files[0];
  if (!f) {
    setStatus("出走表HTMLを選んでください。", "err");
    return;
  }
  const v = $("venue").value, r = $("rno").value;
  if ((v && !r) || (!v && r)) {
    setStatus("会場とRは、両方選ぶか、両方「HTMLから読み取る」にしてください。", "err");
    return;
  }
  const expect = v && r ? v + r + "R" : "";
  $("run").disabled = true;
  setStatus("分析中…（数秒〜数十秒かかります）");
  await new Promise((ok) => setTimeout(ok, 30));
  try {
    await keibaWriteFile("/work/race.html", f);
    const res = keibaCall("analyze", "/work/race.html", expect);
    lastOut = res.stdout;
    lastId = res.rec ? res.rec.race_id : null;
    let saveMsg = "";
    if (res.rc === 0 && res.rec && STORE.db) {
      const sv = await storeSaveAnalysis(res.stdout);
      saveMsg = sv.saved ? "（記録しました）" : "（" + sv.reason + "）";
      await showBkstat();
    }
    showSummary(res);
    $("out").innerHTML = renderOutput(res.stdout);
    $("result").classList.remove("hidden");
    if (res.rc === 0 && res.rec) { setStatus("分析が完了しました（レースID " + res.rec.race_id + "）" + saveMsg + "。", "ok"); $("tokekka").href = "kekka.html?race=" + res.rec.race_id; }
    else if (res.rc === 0) setStatus("完了しました（見送りなど、買い目のない出力です）。", "ok");
    else setStatus("エラー・停止の出力です。内容を確認してください。", "err");
  } catch (e) {
    setStatus("実行中にエラーが起きました: " + e.message, "err");
  } finally {
    $("run").disabled = false;
  }
}

$("run").addEventListener("click", run);
$("save").addEventListener("click", () => {
  if (lastOut !== null) downloadText((lastId ? lastId + "_" : "") + "分析出力.txt", lastOut);
});

// ---------------- まとめて分析 ----------------
let bulkRows = [];
function setB(msg, cls) { const s = $("bstatus"); s.textContent = msg; s.className = "status " + (cls || ""); }
$("brun").addEventListener("click", async () => {
  const files = Array.from($("bfiles").files).sort((a, b) => a.name.localeCompare(b.name));
  if (!files.length) { setB("出走表のファイルを選んでください。", "err"); return; }
  $("brun").disabled = true; $("run").disabled = true;
  $("btbl").innerHTML = "<tr><th>#</th><th>ファイル</th><th>レースID</th><th>会場・R</th><th>モード</th><th>状態</th><th>備考</th></tr>";
  const t0 = Date.now();
  bulkRows = await bulkAnalyze(files, (k, n, r) => {
    const sec = (Date.now() - t0) / 1000;
    setB("分析中 " + k + "/" + n + "（残り約" + Math.round(sec / k * (n - k) / 60) + "分）…");
    const bad = !/記録しました/.test(r.status);
    $("btbl").insertAdjacentHTML("beforeend", "<tr class='" + (bad ? "fail" : "") + "'><td>" + k + "</td><td>" + escapeHtml(r.file) + "</td><td>" + escapeHtml(r.race_id || "-") +
      "</td><td>" + escapeHtml(r.venue + (r.rno ? r.rno + "R" : "")) + "</td><td>" + escapeHtml(r.mode) + "</td><td>" + escapeHtml(r.status) + "</td><td>" + escapeHtml(r.note) + "</td></tr>");
  });
  const ok = bulkRows.filter((r) => r.status === "記録しました").length;
  setB("完了: 記録 " + ok + "件／" + bulkRows.length + "件。記録しなかったものは一覧の赤い行を確認してください（見送り・停止は検証の対象外）。", ok === bulkRows.length ? "ok" : "err");
  $("btools").classList.remove("hidden");
  await showBkstat();
  $("brun").disabled = false; $("run").disabled = false;
});
$("bsave").addEventListener("click", () => {
  const q = (v) => '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
  const csv = "\ufeffファイル,レースID,会場,R,モード,状態,備考\n" + bulkRows.map((r) => [r.file, r.race_id, r.venue, r.rno, r.mode, r.status, r.note].map(q).join(",")).join("\n") + "\n";
  downloadText("まとめて分析_一覧.csv", csv);
});

storeInit().then(showBkstat).catch((e) => { STORE.db = null; console.log("記録を開けません", e); });
keibaInit((m) => setStatus(m))
  .then((info) => {
    $("footer").textContent = footerText(info);
    setStatus("準備ができました。出走表HTMLを選んで「分析開始」を押してください。", "ok");
    $("run").disabled = false;
    $("brun").disabled = false;
  })
  .catch((e) => setStatus("起動できません: " + e.message, "err"));
