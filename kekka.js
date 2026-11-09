// 結果入力画面：分析出力（REC行を含む）と結果を、考察計算v4.7.py の kosatsu にそのまま渡す。
// REC行は書き写さず、分析出力の全文をファイルとして渡す（考察ルール第3条1）。
"use strict";

const $ = (id) => document.getElementById(id);
let bunseki = null;      // 分析出力の全文
let bunsekiName = "";
let nums = [];
let lastRes = null;

function setStatus(msg, cls) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status " + (cls || "");
}
$("footer").textContent = footerText(null);

function recOf(text) {
  const m = text.match(/^REC (\{.*\})\s*$/m);
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch (e) { return null; }
}

function setBunseki(text, name) {
  const rec = recOf(text);
  if (!rec) {
    bunseki = null;
    nums = [];
    $("raceinfo").textContent = "このファイルにはREC行がありません（分析がエラー・停止・見送りだった可能性があります）。";
    $("raceinfo").className = "hint err";
    buildRows();
    return;
  }
  bunseki = text;
  bunsekiName = name;
  nums = rec.nums.slice().sort((a, b) => a - b);
  const id = rec.race_id;
  $("raceinfo").textContent = "レースID " + id + " ／ " + rec.venue + " " + Number(id.slice(-2)) + "R ／ " + rec.dist + "m ／ " + rec.heads + "頭 ／ モード=" + rec.mode +
    " ／ 出走馬番 " + nums.join(",");
  $("raceinfo").className = "hint";
  buildRows();
}

function rowHtml(k) {
  const opt = '<option value="">-</option>' + nums.map((u) => "<option>" + u + "</option>").join("");
  return "<div class='row resrow'>" +
    (k > 0 ? "<span class='hint'>同着の組" + k + "</span>" : "") +
    ["1着", "2着", "3着"].map((t) => "<label>" + t + " <select class='pos'>" + opt + "</select></label>").join("") +
    "<label>三連複払戻 <input type='number' class='pay' min='1' step='10' inputmode='numeric' style='width:8em'> 円</label></div>";
}

function buildRows() {
  $("rows").innerHTML = rowHtml(0);
}

$("addrow").addEventListener("click", () => {
  if (!nums.length) return;
  $("rows").insertAdjacentHTML("beforeend", rowHtml($("rows").children.length));
});

function resultString() {
  const parts = [];
  for (const row of $("rows").children) {
    const p = Array.from(row.querySelectorAll(".pos")).map((s) => s.value);
    const pay = row.querySelector(".pay").value.trim();
    if (p.some((x) => !x) || !pay) throw new Error("着順3頭と払戻をすべて入力してください。");
    if (new Set(p).size !== 3) throw new Error("同じ馬番が重なっています。");
    if (!/^\d+$/.test(pay)) throw new Error("払戻は整数（円）で入力してください。");
    parts.push(p.join("-") + "/" + pay + "円");
  }
  return parts.join(",");
}

function showSummary(led) {
  const box = $("summary");
  if (!led) { box.classList.add("hidden"); return; }
  const b = led.b47;
  const items = [
    ["レースID", led.race_id],
    ["結果", led.orders.map((o) => o.join("-")).join(" , ")],
    ["仮想購入", b.points + "点 ／ " + b.stake + "円"],
    ["的中", b.hit ? "的中（" + b.hit_rank + "位）" : "不的中"],
    ["仮想払戻", b.ret + "円"],
    ["仮想回収率", b.stake ? (100 * b.ret / b.stake).toFixed(1) + "%" : "-"],
  ];
  let h = "<h2>結果の概要</h2><dl class='sum'>";
  for (const [k, v] of items) h += "<div><dt>" + escapeHtml(k) + "</dt><dd>" + escapeHtml(v) + "</dd></div>";
  box.innerHTML = h + "</dl><p class='hint'>Δ・切り捨て・品質などは下の考察出力のとおり。集計（300レースの判定）はPhase 4で行います。</p>";
  box.classList.remove("hidden");
}

async function run() {
  if (!bunseki) {
    setStatus("分析出力ファイルを選んでください。", "err");
    return;
  }
  let res;
  try { res = resultString(); } catch (e) { setStatus(e.message, "err"); return; }
  $("run").disabled = true;
  setStatus("考察を計算しています…");
  await new Promise((ok) => setTimeout(ok, 30));
  try {
    KEIBA.py.FS.writeFile("/work/分析出力.txt", new TextEncoder().encode(bunseki));
    const r = keibaCall("kosatsu", "/work/分析出力.txt", res);
    lastRes = r;
    $("out").textContent = r.stdout;
    $("result").classList.remove("hidden");
    showSummary(r.ledger);
    if (r.rc === 0) {
      let msg = "考察が完了しました。";
      if (STORE.db) {
        const sv = await storeSaveKosatsu(bunseki, res, r.stdout);
        msg += sv.saved ? "記録しました。" + (sv.version_ok ? "" : "（注意: 現行の版・指紋と違う記録です）") : "記録していません: " + sv.reason;
        await showBkstat();
        await loadPick();
      }
      setStatus(msg + " 必要なら「考察出力を保存」で " + r.race_id + ".txt も保存できます。", "ok");
    }
    else setStatus("停止しました。出力の内容を確認してください（保存はしません）。", "err");
    $("save").disabled = r.rc !== 0;
  } catch (e) {
    setStatus("実行中にエラーが起きました: " + e.message, "err");
  } finally {
    $("run").disabled = false;
  }
}

$("run").addEventListener("click", run);
$("save").addEventListener("click", () => {
  if (lastRes && lastRes.rc === 0) downloadText(lastRes.race_id + ".txt", lastRes.stdout);
});

$("bfile").addEventListener("change", async () => {
  const f = $("bfile").files[0];
  if (!f) return;
  $("srcfile").checked = true;
  setBunseki(await f.text(), f.name);
});

// 記録（分析済み・結果未登録）から選ぶ
async function loadPick() {
  const rows = (await storeAll()).filter((r) => !r.kosatsu_stdout).sort((a, b) => b.race_id.localeCompare(a.race_id));
  const sel = $("pick");
  sel.innerHTML = '<option value="">-</option>' + rows.map((r) => "<option value='" + r.race_id + "'>" + r.race_id + " " + escapeHtml(r.venue) + r.rno + "R</option>").join("");
  const want = new URLSearchParams(location.search).get("race");
  if (want && rows.some((r) => r.race_id === want)) { sel.value = want; await pickChanged(); }
  else if (want) {
    const r = await storeGet(want);
    $("raceinfo").textContent = r && r.kosatsu_stdout ? want + " は結果登録済みです（記録の画面で考察を見られます）。" : want + " は記録にありません。";
    $("raceinfo").className = "hint err";
  }
}
async function pickChanged() {
  const id = $("pick").value;
  $("srcstore").checked = true;
  if (!id) { bunseki = null; nums = []; buildRows(); return; }
  const r = await storeGet(id);
  setBunseki(r.bunseki_stdout, id);
}
$("pick").addEventListener("change", pickChanged);
$("srcstore").addEventListener("change", pickChanged);
buildRows();
storeInit().then(async () => { await showBkstat(); await loadPick(); })
  .catch((e) => { STORE.db = null; setStatus("記録を開けません（ファイルから選んでください）: " + e.message, "err"); });

keibaInit((m) => setStatus(m))
  .then((info) => {
    $("footer").textContent = footerText(info);
    setStatus("準備ができました。", "ok");
    $("run").disabled = false;
  })
  .catch((e) => setStatus("起動できません: " + e.message, "err"));

// ---------------- 結果ページから登録（まとめて） ----------------
let parsed = [];
function setR(msg, cls) { const s = $("rstatus"); s.textContent = msg; s.className = "status " + (cls || ""); }

$("rfiles").addEventListener("change", async () => {
  const files = Array.from($("rfiles").files);
  if (!files.length) return;
  if (!KEIBA.py) { setR("Pythonの準備ができてから選んでください。", "err"); return; }
  setR("読み取り中…");
  await new Promise((ok) => setTimeout(ok, 20));
  parsed = [];
  for (const f of files) {
    setR("読み取り中 " + (parsed.length + 1) + "/" + files.length + " …");
    await new Promise((ok) => setTimeout(ok, 5));
    let r;
    try {
      await keibaWriteFile("/work/result_page.html", f);
      r = keibaCall("result_parse", "/work/result_page.html");
    } catch (e) {
      r = { errors: ["読み取り中のエラー: " + e.message] };
    }
    r.file = f.name;
    let st = null;
    if (!r.errors.length) {
      st = STORE.db ? await storeGet(r.race_id) : null;
      if (!st) r.errors.push("このレースは分析の記録にありません（先に分析してください）");
      else if (st.kosatsu_stdout) r.errors.push("結果登録済みです");
    }
    r.ok = !r.errors.length;
    r.stored = st;
    parsed.push(r);
  }
  parsed.sort((a, b) => String(a.race_id).localeCompare(String(b.race_id)));
  let h = "<tr><th>登録</th><th>ファイル</th><th>レースID</th><th>会場・R</th><th>着順（1-2-3）</th><th>三連複の払戻</th><th>状態</th></tr>";
  parsed.forEach((r, k) => {
    const trio = (r.trio || []).map((t) => t.combo.join("-") + " " + t.pay.toLocaleString() + "円").join(" ／ ");
    const ord = (r.trio || []).map((t) => (t.order || []).join("-")).join(" ／ ");
    h += "<tr class='" + (r.ok ? "" : "fail") + "'><td>" + (r.ok ? "<input type='checkbox' class='rchk' data-k='" + k + "' checked>" : "") + "</td><td>" + escapeHtml(r.file) +
      "</td><td>" + escapeHtml(r.race_id || "-") + "</td><td>" + escapeHtml((r.venue || "") + (r.rno ? r.rno + "R" : "")) + "</td><td>" + escapeHtml(ord || "-") +
      "</td><td>" + escapeHtml(trio || "-") + "</td><td>" + escapeHtml(r.ok ? "登録できます" + (r.notes.length ? "（" + r.notes.join("、") + "）" : "") : r.errors.join("、")) + "</td></tr>";
  });
  $("rtbl").innerHTML = h;
  const n = parsed.filter((r) => r.ok).length;
  $("rreg").classList.toggle("hidden", n === 0);
  setR("読み取りました: 登録できるもの " + n + "件／" + parsed.length + "件。着順と払戻を確認してから登録してください。", n ? "ok" : "err");
});

$("rreg").addEventListener("click", async () => {
  const ks = Array.from(document.querySelectorAll(".rchk")).filter((c) => c.checked).map((c) => Number(c.dataset.k));
  if (!ks.length) { setR("登録するレースにチェックを入れてください。", "err"); return; }
  $("rreg").disabled = true;
  let okN = 0;
  const msgs = [];
  for (const k of ks) {
    const r = parsed[k];
    setR("登録中 " + (ks.indexOf(k) + 1) + "/" + ks.length + "（" + r.race_id + "）…");
    await new Promise((ok) => setTimeout(ok, 20));
    try {
      const b = r.stored.bunseki_stdout;
      KEIBA.py.FS.writeFile("/work/分析出力.txt", new TextEncoder().encode(b));
      const res = keibaCall("kosatsu", "/work/分析出力.txt", r.result);
      if (res.rc !== 0) { msgs.push(r.race_id + ": 考察が停止（" + res.stdout.trim().split("\n").pop() + "）"); continue; }
      const sv = await storeSaveKosatsu(b, r.result, res.stdout);
      if (sv.saved) okN++; else msgs.push(r.race_id + ": " + sv.reason);
    } catch (e) {
      msgs.push(r.race_id + ": エラー " + e.message);
    }
  }
  await showBkstat();
  await loadPick();
  setR("登録しました: " + okN + "件" + (msgs.length ? "。登録できなかったもの: " + msgs.join(" ／ ") : "。") + " 記録の画面でバックアップしてください。", msgs.length ? "err" : "ok");
  $("rreg").classList.add("hidden");
  $("rreg").disabled = false;
});
