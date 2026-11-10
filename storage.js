// 端末内の記録（IndexedDB）とバックアップ（v4.8）。v4.7 の記録（keiba_v47）とは別の保存場所を使い、v4.7 の記録には触れない。
// 記録は1レース1件。分析出力と考察出力の全文をそのまま保存する（数値を書き換えない・作り直さない）。
// 正本はバックアップファイル。ブラウザ内の記録は消えることがあるため、定期的にバックアップする。
"use strict";

const STORE = {
  dbName: "keiba_v48",
  db: null,
};
const BACKUP_FORMAT = "keiba-v4.8-backup";
const BACKUP_FORMAT_VER = 1;

function idbOpen(name) {
  return new Promise((ok, ng) => {
    const rq = indexedDB.open(name || STORE.dbName, 1);
    rq.onupgradeneeded = () => {
      const db = rq.result;
      if (!db.objectStoreNames.contains("races")) db.createObjectStore("races", { keyPath: "race_id" });
      if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "key" });
    };
    rq.onsuccess = () => ok(rq.result);
    rq.onerror = () => ng(rq.error);
  });
}

async function storeInit(name) {
  if (name) STORE.dbName = name;
  STORE.db = await idbOpen(STORE.dbName);
  try {
    if (navigator.storage && navigator.storage.persist) await navigator.storage.persist();
  } catch (e) { /* 永続化を頼めなくても続ける */ }
  return STORE.db;
}

function idbReq(storeName, mode, fn) {
  return new Promise((ok, ng) => {
    const tx = STORE.db.transaction(storeName, mode);
    const st = tx.objectStore(storeName);
    let out;
    const r = fn(st);
    if (r) r.onsuccess = () => { out = r.result; };
    tx.oncomplete = () => ok(out);
    tx.onerror = () => ng(tx.error);
    tx.onabort = () => ng(tx.error);
  });
}

const storeGet = (id) => idbReq("races", "readonly", (st) => st.get(id));
const storeAll = () => idbReq("races", "readonly", (st) => st.getAll());
const storePut = (rec) => idbReq("races", "readwrite", (st) => st.put(rec));
const storeDel = (id) => idbReq("races", "readwrite", (st) => st.delete(id));
const storeClear = () => idbReq("races", "readwrite", (st) => st.clear());
const metaGet = async (k) => { const r = await idbReq("meta", "readonly", (st) => st.get(k)); return r ? r.value : null; };
const metaPut = (k, v) => idbReq("meta", "readwrite", (st) => st.put({ key: k, value: v }));

function recFromText(text, tag) {
  const m = text.match(new RegExp("^" + tag + " (\\{.*\\})\\s*$", "m"));
  if (!m) return null;
  try { return JSON.parse(m[1]); } catch (e) { return null; }
}

function nowIso() {
  return new Date().toISOString();
}

// 分析を記録する。結果登録済みのレースは上書きしない（同じレースIDの二重登録を防ぐ）。
async function storeSaveAnalysis(bunsekiStdout) {
  const rec = recFromText(bunsekiStdout, "REC");
  if (!rec || !rec.race_id) return { saved: false, reason: "REC行がないため記録しません" };
  const old = await storeGet(rec.race_id);
  if (old && old.kosatsu_stdout) {
    if (old.bunseki_stdout === bunsekiStdout) return { saved: false, reason: "結果登録済みのレースです（記録は変わりません）" };
    return { saved: false, reason: "このレースは結果登録済みのため、分析の記録を上書きしません" };
  }
  const V = BUNDLE.version;
  await storePut({
    race_id: rec.race_id, venue: rec.venue, rno: Number(rec.race_id.slice(-2)), date: rec.race_id.slice(0, 8), mode: rec.mode,
    version: V.version, code_a: rec.code, code_k: null,
    bunseki_stdout: bunsekiStdout, analyzed_at: (old && old.analyzed_at) || nowIso(),
    result: null, kosatsu_stdout: null, registered_at: null,
  });
  return { saved: true };
}

// 結果（考察出力）を記録する。すでに結果がある場合は記録しない。result は考察計算に渡した RES の1行、pop は結果ページから読んだ全馬の人気（手入力では null）。
async function storeSaveKosatsu(bunsekiStdout, result, kosatsuStdout, pop) {
  const led = recFromText(kosatsuStdout, "LEDGER");
  if (!led) return { saved: false, reason: "LEDGER行がないため記録しません" };
  const old = await storeGet(led.race_id);
  if (old && old.kosatsu_stdout) return { saved: false, reason: "このレースはすでに結果登録済みです（二重登録はしません）" };
  const V = BUNDLE.version;
  await storePut({
    race_id: led.race_id, venue: led.venue, rno: led.rno, date: led.date, mode: led.mode,
    version: led.ver, code_a: led.code_a, code_k: led.code_k,
    bunseki_stdout: bunsekiStdout, analyzed_at: (old && old.analyzed_at) || null,
    result: result, pop: pop || null, kosatsu_stdout: kosatsuStdout, registered_at: nowIso(),
  });
  await metaPut("last_change", nowIso());
  return { saved: true, version_ok: led.ver === V.version && led.code_a === V.code && led.code_k === V.code_k };
}

async function storeBackupObject() {
  const races = (await storeAll()).sort((a, b) => a.race_id.localeCompare(b.race_id));
  const V = BUNDLE.version;
  const body = {
    format: BACKUP_FORMAT, format_ver: BACKUP_FORMAT_VER, created_at: nowIso(),
    version: V.version, code_a: V.code, code_k: V.code_k, pyodide: V.pyodide,
    count: races.length, count_registered: races.filter((r) => r.kosatsu_stdout).length,
    races: races,
  };
  return body;
}

// バックアップの検査。形式・版・指紋・件数・レースIDの重複・各記録の中身（RECとLEDGERのレースID）を確かめる。
function backupCheck(obj) {
  const errs = [];
  if (!obj || obj.format !== BACKUP_FORMAT) errs.push("バックアップの形式が違います");
  if (obj && obj.format_ver !== BACKUP_FORMAT_VER) errs.push("バックアップ形式の版が違います");
  if (!obj || !Array.isArray(obj.races)) { errs.push("記録の一覧がありません"); return errs; }
  if (obj.count !== obj.races.length) errs.push("件数が合いません（記載=" + obj.count + "、実際=" + obj.races.length + "）");
  const ids = new Set();
  for (const r of obj.races) {
    if (!r.race_id || ids.has(r.race_id)) errs.push("レースIDの欠落・重複: " + r.race_id);
    ids.add(r.race_id);
    const rec = r.bunseki_stdout ? recFromText(r.bunseki_stdout, "REC") : null;
    if (!rec || rec.race_id !== r.race_id) errs.push(r.race_id + ": 分析出力のREC行がない、またはレースIDが違います");
    if (r.kosatsu_stdout) {
      const led = recFromText(r.kosatsu_stdout, "LEDGER");
      if (!led || led.race_id !== r.race_id) errs.push(r.race_id + ": 考察出力のLEDGER行がない、またはレースIDが違います");
    }
  }
  return errs;
}

// 復元（追加のみ）。端末にない記録を足す。同じ内容は飛ばす。内容が違うものは上書きせず、件数を報告する。
async function storeRestore(obj) {
  const errs = backupCheck(obj);
  if (errs.length) return { ok: false, errors: errs };
  let added = 0, same = 0, conflict = [], upgraded = 0;
  for (const r of obj.races) {
    const old = await storeGet(r.race_id);
    if (!old) { await storePut(r); added++; continue; }
    if (old.bunseki_stdout === r.bunseki_stdout && old.kosatsu_stdout === r.kosatsu_stdout) { same++; continue; }
    if (!old.kosatsu_stdout && r.kosatsu_stdout && old.bunseki_stdout === r.bunseki_stdout) { await storePut(r); upgraded++; continue; }
    conflict.push(r.race_id);
  }
  await metaPut("last_change", nowIso());
  return { ok: true, added, same, upgraded, conflict };
}

function backupFileName() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return "keiba_v4.8_backup_" + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "_" + p(d.getHours()) + p(d.getMinutes()) + ".json";
}

async function storeBackupDownload() {
  const obj = await storeBackupObject();
  downloadText(backupFileName(), JSON.stringify(obj));
  await metaPut("last_backup", { at: obj.created_at, count: obj.count, count_registered: obj.count_registered });
  return obj;
}

// 最終バックアップの状況（画面の上部に常に出す）
async function storeBackupStatus() {
  const lb = await metaGet("last_backup");
  const lc = await metaGet("last_change");
  const all = await storeAll();
  const reg = all.filter((r) => r.kosatsu_stdout).length;
  let msg, warn = false;
  if (!lb) {
    msg = "まだバックアップしていません";
    warn = reg > 0;
  } else {
    const t = new Date(lb.at);
    msg = "最終バックアップ: " + t.toLocaleString("ja-JP") + "（結果登録 " + lb.count_registered + "件）";
    if (lc && lc > lb.at) { msg += " ／ その後に記録が増えています"; warn = true; }
  }
  return { msg, warn, total: all.length, registered: reg };
}
