// 記録とバックアップの画面。
"use strict";

const $ = (id) => document.getElementById(id);
let all = [];

function setStatus(msg, cls) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status " + (cls || "");
}
$("footer").textContent = footerText(null);

async function showBackupStatus() {
  const st = await storeBackupStatus();
  const b = $("bkstat");
  b.textContent = st.msg + "　／　記録 " + st.total + "件（うち結果登録 " + st.registered + "件）";
  b.className = "bkstat" + (st.warn ? " warn" : "");
}

function ledgerLines(rows) {
  return rows.filter((r) => r.kosatsu_stdout)
    .map((r) => r.kosatsu_stdout.split("\n").find((l) => l.startsWith("LEDGER ")))
    .filter(Boolean);
}

async function refresh() {
  all = (await storeAll()).sort((a, b) => b.race_id.localeCompare(a.race_id));
  const V = BUNDLE.version;
  const reg = all.filter((r) => r.kosatsu_stdout);
  const normal = reg.filter((r) => r.mode === "通常" && r.code_a === V.code && r.code_k === V.code_k && r.version === V.version);
  const other = reg.length - normal.length;
  $("counts").textContent = "記録 " + all.length + "件 ／ 結果登録済み " + reg.length + "件（うち通常モード・現行の指紋 " + normal.length + "件" +
    (other ? "、新馬モードまたは指紋・版の違うもの " + other + "件" : "") + "） ／ 判定に必要な対象は300レース以上（数え方の詳細はPC版のaggregateに従う）";
  let h = "<tr><th>レースID</th><th>開催日</th><th>会場</th><th>R</th><th>モード</th><th>状態</th><th>結果</th><th>登録日時</th><th>指紋</th><th></th></tr>";
  for (const r of all) {
    const fpOk = r.code_a === V.code && (!r.code_k || r.code_k === V.code_k) && r.version === V.version;
    h += "<tr><td><a href='#' data-id='" + r.race_id + "' class='show'>" + r.race_id + "</a></td><td>" + r.date + "</td><td>" + escapeHtml(r.venue || "") +
      "</td><td>" + r.rno + "</td><td>" + escapeHtml(r.mode || "") + "</td><td>" + (r.kosatsu_stdout ? "結果登録済み" : "分析のみ") +
      "</td><td>" + escapeHtml(r.result || "-") + "</td><td>" + (r.registered_at ? new Date(r.registered_at).toLocaleString("ja-JP") : "-") +
      "</td><td>" + (fpOk ? "現行" : "<span class='errtxt'>違う</span>") + "</td><td>" +
      (r.kosatsu_stdout ? "" : "<a href='kekka.html?race=" + r.race_id + "'>結果入力</a> ／ <a href='#' data-id='" + r.race_id + "' class='del'>削除</a>") + "</td></tr>";
  }
  $("list").innerHTML = h;
  await showBackupStatus();
}

$("list").addEventListener("click", async (ev) => {
  const a = ev.target.closest("a");
  if (!a || !a.dataset.id) return;
  ev.preventDefault();
  const r = all.find((x) => x.race_id === a.dataset.id);
  if (!r) return;
  if (a.classList.contains("del")) {
    if (r.kosatsu_stdout) return;  // 結果登録済みはここから消さない
    if (!confirm(r.race_id + " の分析の記録を削除します（結果は未登録）。よろしいですか？")) return;
    await storeDel(r.race_id);
    await refresh();
    return;
  }
  $("dtitle").textContent = r.race_id + "（" + (r.kosatsu_stdout ? "考察出力" : "分析出力") + "）";
  $("dbody").textContent = r.kosatsu_stdout || r.bunseki_stdout;
  $("detail").classList.remove("hidden");
  $("detail").scrollIntoView({ behavior: "smooth" });
});
$("closeDetail").addEventListener("click", () => $("detail").classList.add("hidden"));

$("backup").addEventListener("click", async () => {
  const obj = await storeBackupDownload();
  setStatus("バックアップを保存しました（記録 " + obj.count + "件、うち結果登録 " + obj.count_registered + "件）。保存先のフォルダを確認してください。", "ok");
  await showBackupStatus();
});

$("restore").addEventListener("change", async () => {
  const f = $("restore").files[0];
  if (!f) return;
  let obj;
  try { obj = JSON.parse(await f.text()); } catch (e) { setStatus("バックアップファイルを読めません: " + e.message, "err"); return; }
  const V = BUNDLE.version;
  if (obj.version !== V.version || obj.code_a !== V.code || obj.code_k !== V.code_k) {
    if (!confirm("このバックアップは、現在のアプリと版・指紋が違います（バックアップ: " + obj.version + " / " + obj.code_a + " / " + obj.code_k +
      "）。指紋の違う記録は判定に使えません。それでも記録として取り込みますか？")) { setStatus("復元を中止しました。"); return; }
  }
  const r = await storeRestore(obj);
  if (!r.ok) { setStatus("復元できません: " + r.errors.slice(0, 5).join(" ／ "), "err"); return; }
  setStatus("復元しました: 追加 " + r.added + "件、結果を追加 " + r.upgraded + "件、同じ内容のため飛ばした " + r.same + "件" +
    (r.conflict.length ? "、内容が違うため上書きしなかった " + r.conflict.length + "件（" + r.conflict.join(",") + "）" : "") + "。", r.conflict.length ? "err" : "ok");
  $("restore").value = "";
  await refresh();
});

$("exportLedger").addEventListener("click", () => {
  const lines = ledgerLines(all.slice().sort((a, b) => a.race_id.localeCompare(b.race_id)));
  if (!lines.length) { setStatus("結果登録済みのレースがありません。", "err"); return; }
  downloadText("LEDGER_v4.7.txt", lines.join("\n") + "\n");
  setStatus("LEDGER行 " + lines.length + "件を書き出しました。", "ok");
});

$("checkLedger").addEventListener("click", () => {
  const lines = ledgerLines(all);
  if (!lines.length) { setStatus("結果登録済みのレースがありません。", "err"); return; }
  const r = keibaCall("ledger_check", lines.join("\n") + "\n");
  if (r.ok) setStatus("照合OK: LEDGER行 " + r.n + "件（版・指紋・再計算・重複を考察計算v4.7.pyで確認）。", "ok");
  else setStatus("照合で停止: " + r.error, "err");
});

let aggText = null;
$("agg").addEventListener("click", async () => {
  const st = $("study").value.trim();
  if (st && !/^\d{8}$/.test(st)) { setStatus("開始日は8桁の数字（例: 20261110）で入力してください。", "err"); return; }
  const lines = ledgerLines(all.slice().sort((a, b) => a.race_id.localeCompare(b.race_id)));
  if (!lines.length) { setStatus("結果登録済みのレースがありません。", "err"); return; }
  const text = (st ? 'STUDY {"start":"' + st + '"}\n' : "") + lines.join("\n") + "\n";
  $("agg").disabled = true;
  setStatus("集計中…（300レース以上では1分ほどかかることがあります）");
  await new Promise((ok) => setTimeout(ok, 30));
  try {
    const r = keibaCall("aggregate", text);
    aggText = r.stdout;
    $("aggout").innerHTML = renderOutput(r.stdout);
    $("aggbox").classList.remove("hidden");
    setStatus(r.rc === 0 ? "集計しました。" : "集計は停止しました。出力を確認してください。", r.rc === 0 ? "ok" : "err");
  } catch (e) {
    setStatus("集計中にエラーが起きました: " + e.message, "err");
  } finally {
    $("agg").disabled = false;
  }
});
$("aggsave").addEventListener("click", () => { if (aggText) downloadText("aggregate_v4.7.txt", aggText); });

storeInit().then(refresh).then(() => setStatus("記録を読み込みました。", "ok"))
  .catch((e) => setStatus("記録を開けません: " + e.message, "err"));
keibaInit(() => {})
  .then((info) => { $("footer").textContent = footerText(info); $("checkLedger").disabled = false; $("agg").disabled = false; })
  .catch((e) => setStatus("Pythonを起動できません（照合だけ使えません）: " + e.message, "err"));
