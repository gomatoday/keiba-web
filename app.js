// 分析画面：HTMLを読み込み、keiba_v47.py の predict を実行して、出力をそのまま表示する。
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
  const p1 = rec.p1 || {};
  const items = [
    ["開催日", d ? d.slice(0, 4) + "/" + d.slice(4, 6) + "/" + d.slice(6, 8) : "-"],
    ["会場", rec.venue],
    ["R", id ? Number(id.slice(-2)) + "R" : "-"],
    ["距離", rec.dist + "m"],
    ["頭数", rec.heads + "頭"],
    ["分析モード", rec.mode],
    ["逃げ馬", rec.mode === "通常" ? p1.nige_all + "頭" : "-"],
    ["切り捨て", rec.mode === "通常" ? ((p1.cut || []).join(",") || "なし") : "-"],
    ["全買い", rec.mode === "通常" ? (p1.all_buy ? "はい" : "いいえ") : "-"],
    ["仮想購入", rec.buy_points + "点 ／ " + rec.buy_stake + "円"],
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

storeInit().then(showBkstat).catch((e) => { STORE.db = null; console.log("記録を開けません", e); });
keibaInit((m) => setStatus(m))
  .then((info) => {
    $("footer").textContent = footerText(info);
    setStatus("準備ができました。出走表HTMLを選んで「分析開始」を押してください。", "ok");
    $("run").disabled = false;
  })
  .catch((e) => setStatus("起動できません: " + e.message, "err"));
