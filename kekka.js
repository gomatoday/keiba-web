// 結果入力画面：分析出力（REC行を含む）と結果（RES行）を、考察計算v4.9.py の kosatsu にそのまま渡す。
// REC行は書き写さず、分析出力の全文をファイルとして渡す（考察ルール第3条1）。
// 結果の登録は結果ページ（成績・払戻金）からが原則。手入力は例外（同着のあるレースは結果ページから登録する）。
"use strict";

const $ = (id) => document.getElementById(id);
let bunseki = null;      // 分析出力の全文
let nums = [];
let heads = 0;
let lastRes = null;
const TYPES = ["単勝", "複勝", "ワイド", "馬連", "三連複"];

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

function setBunseki(text) {
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
  nums = rec.nums.slice().sort((a, b) => a - b);
  heads = rec.heads;
  const id = rec.race_id;
  $("raceinfo").textContent = "レースID " + id + " ／ " + rec.venue + " " + Number(id.slice(-2)) + "R ／ " + rec.dist + "m ／ " + rec.heads + "頭 ／ モード=" + rec.mode +
    " ／ 出走馬番 " + nums.join(",");
  $("raceinfo").className = "hint";
  buildRows();
}

// ---------------- 手入力（例外） ----------------
function payInput(type, combo) {
  return "<label class='payin'>" + escapeHtml(type) + " <b>" + escapeHtml(combo) + "</b> <input type='number' class='pay' data-t='" + type + "' data-k='" + combo +
    "' min='1' step='10' inputmode='numeric' style='width:7em'> 円</label>";
}

function buildRows() {
  const opt = '<option value="">-</option>' + nums.map((u) => "<option>" + u + "</option>").join("");
  $("rows").innerHTML = "<div class='row resrow'>" + ["1着", "2着", "3着"].map((t, k) => "<label>" + t + " <select class='pos' data-k='" + k + "'>" + opt + "</select></label>").join("") + "</div>" +
    "<div id='payrows'><p class='hint'>着順を3頭選ぶと、払戻を入れる欄が出ます。</p></div>";
  for (const s of document.querySelectorAll(".pos")) s.addEventListener("change", buildPays);
}

function chosen() {
  const p = Array.from(document.querySelectorAll(".pos")).map((s) => s.value);
  return p.some((x) => !x) || new Set(p).size !== 3 ? null : p.map(Number);
}

function buildPays() {
  const p = chosen();
  if (!p) { $("payrows").innerHTML = "<p class='hint'>着順を3頭（重ならないように）選ぶと、払戻を入れる欄が出ます。</p>"; return; }
  const [a, b, c] = p;
  const s2 = (x, y) => [x, y].sort((u, v) => u - v).join("-");
  const place = heads <= 7 ? [a, b] : [a, b, c];
  const items = [["単勝", String(a)]].concat(place.map((u) => ["複勝", String(u)]),
    [[a, b], [a, c], [b, c]].map(([x, y]) => ["ワイド", s2(x, y)]), [["馬連", s2(a, b)]],
    [["三連複", [a, b, c].sort((u, v) => u - v).join("-")]]);
  $("payrows").innerHTML = "<p class='hint'>払戻は100円あたりの金額。三連複は必須（モデルの判定に使う）。単勝・複勝を空欄にすると、そのレースは3案の回収率の集計から外れます。ワイド・馬連は記録用です。</p>" +
    items.map(([t, k]) => payInput(t, k)).join("");
}

function resultText() {
  const p = chosen();
  if (!p) throw new Error("着順を3頭（重ならないように）選んでください。");
  const pays = {};
  for (const t of TYPES) pays[t] = [];
  for (const inp of document.querySelectorAll(".pay")) {
    const v = inp.value.trim();
    if (!v) continue;
    if (!/^\d+$/.test(v) || Number(v) <= 0) throw new Error(inp.dataset.t + " " + inp.dataset.k + " の払戻は正の整数（円）で入力してください。");
    pays[inp.dataset.t].push({ 組: inp.dataset.k, 払戻: Number(v) });
  }
  if (!pays["三連複"].length) throw new Error("三連複の払戻は必須です。");
  const rec = recOf(bunseki);
  return "RES " + JSON.stringify({ race_id: rec.race_id, orders: [p], pays: pays, source: "手入力", pop: null, finish: null });
}

function showSummary(led) {
  const box = $("summary");
  if (!led) { box.classList.add("hidden"); return; }
  const items = [["レースID", led.race_id], ["結果", led.orders.map((o) => o.join("-")).join(" , ")], ["払戻の入力元", led.source || "-"]];
  if (led.plans) {
    for (const k of Object.keys(led.plans)) {
      const v = led.plans[k];
      items.push([k, v.n ? v.n + "点 " + (v.hit ? "的中 " + v.ret + "円" : "不的中") : "見送り"]);
    }
  }
  let h = "<h2>結果の概要</h2><dl class='sum'>";
  for (const [k, v] of items) h += "<div><dt>" + escapeHtml(k) + "</dt><dd>" + escapeHtml(v) + "</dd></div>";
  box.innerHTML = h + "</dl><p class='hint'>モデルの判定の値・3案の結果は下の考察出力のとおり。集計（300レースの判定）は記録の画面で行います。</p>";
  box.classList.remove("hidden");
}

async function run() {
  if (!bunseki) { setStatus("分析出力を選んでください。", "err"); return; }
  let res;
  try { res = resultText(); } catch (e) { setStatus(e.message, "err"); return; }
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
        const sv = await storeSaveKosatsu(bunseki, res, r.stdout, null);
        msg += sv.saved ? "記録しました。" + (sv.version_ok ? "" : "（注意: 現行の版・指紋と違う記録です）") : "記録していません: " + sv.reason;
        await showBkstat();
        await loadPick();
      }
      setStatus(msg + " 必要なら「考察出力を保存」で " + r.race_id + ".txt も保存できます。", "ok");
    } else setStatus("停止しました。出力の内容を確認してください（保存はしません）。", "err");
    $("save").disabled = r.rc !== 0;
  } catch (e) {
    setStatus("実行中にエラーが起きました: " + e.message, "err");
  } finally {
    $("run").disabled = false;
  }
}

$("run").addEventListener("click", run);
$("save").addEventListener("click", () => { if (lastRes && lastRes.rc === 0) downloadText(lastRes.race_id + ".txt", lastRes.stdout); });
$("bfile").addEventListener("change", async () => {
  const f = $("bfile").files[0];
  if (!f) return;
  $("srcfile").checked = true;
  setBunseki(await f.text());
});

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
  setBunseki(r.bunseki_stdout);
}
$("pick").addEventListener("change", pickChanged);
$("srcstore").addEventListener("change", pickChanged);
buildRows();
storeInit().then(async () => { await showBkstat(); await loadPick(); })
  .catch((e) => { STORE.db = null; setStatus("記録を開けません（ファイルから選んでください）: " + e.message, "err"); });

keibaInit((m) => setStatus(m))
  .then((info) => { $("footer").textContent = footerText(info); setStatus("準備ができました。", "ok"); $("run").disabled = false; })
  .catch((e) => setStatus("起動できません: " + e.message, "err"));

// ---------------- 結果ページから登録（まとめて。原則はこちら） ----------------
let parsed = [];
function setR(msg, cls) { const s = $("rstatus"); s.textContent = msg; s.className = "status " + (cls || ""); }

$("rfiles").addEventListener("change", async () => {
  const files = Array.from($("rfiles").files);
  if (!files.length) return;
  if (!KEIBA.py) { setR("Pythonの準備ができてから選んでください。", "err"); return; }
  parsed = [];
  for (const f of files) {
    setR("読み取り中 " + (parsed.length + 1) + "/" + files.length + " …");
    await new Promise((ok) => setTimeout(ok, 5));
    let r;
    try {
      await keibaWriteFile("/work/result_page.html", f);
      r = keibaCall("result_parse", "/work/result_page.html");
    } catch (e) {
      r = { errors: ["読み取り中のエラー: " + e.message], notes: [] };
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
  let h = "<tr><th>登録</th><th>ファイル</th><th>レースID</th><th>会場・R</th><th>着順（1-2-3）</th><th>三連複の払戻</th><th>読めた券種</th><th>状態</th></tr>";
  parsed.forEach((r, k) => {
    const res = r.res || {};
    const ord = (res.orders || []).map((o) => o.join("-")).join(" ／ ");
    const trio = ((res.pays || {})["三連複"] || []).map((t) => t.組 + " " + Number(t.払戻).toLocaleString() + "円").join(" ／ ");
    const nt = TYPES.filter((t) => ((res.pays || {})[t] || []).length).length;
    h += "<tr class='" + (r.ok ? "" : "fail") + "'><td>" + (r.ok ? "<input type='checkbox' class='rchk' data-k='" + k + "' checked>" : "") + "</td><td>" + escapeHtml(r.file) +
      "</td><td>" + escapeHtml(r.race_id || "-") + "</td><td>" + escapeHtml((r.venue || "") + (r.rno ? r.rno + "R" : "")) + "</td><td>" + escapeHtml(ord || "-") +
      "</td><td>" + escapeHtml(trio || "-") + "</td><td>" + (r.res ? nt + "／5" : "-") + "</td><td>" +
      escapeHtml(r.ok ? "登録できます" + ((r.notes || []).length ? "（" + r.notes.join("、") + "）" : "") : r.errors.join("、")) + "</td></tr>";
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
      const res = keibaCall("kosatsu", "/work/分析出力.txt", r.res_text);
      if (res.rc !== 0) { msgs.push(r.race_id + ": 考察が停止（" + res.stdout.trim().split("\n").pop() + "）"); continue; }
      const sv = await storeSaveKosatsu(b, r.res_text, res.stdout, null);
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
