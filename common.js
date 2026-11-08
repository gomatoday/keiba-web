// 共通処理：Pyodideの起動、計算エンジンの読み込み、指紋の確認。
// 計算はすべて keiba_v47.py（分析計算v4.7.py と同一）が行う。このファイルは受け渡しだけを行う。
"use strict";

const KEIBA = {
  py: null,
  info: null,
};

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function keibaInit(setStatus) {
  const V = BUNDLE.version;
  setStatus("Python（Pyodide " + V.pyodide + "）を読み込んでいます…（初回は1分ほどかかります）");
  if (typeof loadPyodide !== "function") {
    throw new Error("Pyodideを読み込めませんでした。インターネット接続を確認してください。");
  }
  const py = await loadPyodide({ indexURL: V.pyodide_url });
  if (py.version !== V.pyodide) {
    throw new Error("Pyodideの版が違います（読み込んだ版=" + py.version + "、指定=" + V.pyodide + "）。");
  }
  setStatus("解析ライブラリ（beautifulsoup4・lxml）を読み込んでいます…");
  await py.loadPackage(["beautifulsoup4", "lxml"]);
  py.FS.mkdirTree("/app");
  py.FS.mkdirTree("/work");
  py.FS.writeFile("/app/keiba_v47.py", b64ToBytes(BUNDLE.files["keiba_v47.py"]));
  py.FS.writeFile("/app/kosatsu_v47.py", b64ToBytes(BUNDLE.files["kosatsu_v47.py"]));
  py.FS.writeFile("/app/runner.py", b64ToBytes(BUNDLE.files["runner.py"]));
  py.runPython("import sys\nif '/app' not in sys.path: sys.path.insert(0, '/app')\nimport runner");
  const info = JSON.parse(py.runPython("runner.load_engine()"));
  if (info.code !== V.code) {
    throw new Error("計算エンジンの指紋が違います（実行=" + info.code + "、正本=" + V.code + "）。使用を中止してください。");
  }
  if (info.code_k !== V.code_k || info.version_k !== V.version) {
    throw new Error("考察計算の指紋・版が違います（実行=" + info.code_k + "、正本=" + V.code_k + "）。使用を中止してください。");
  }
  if (info.version !== V.version) {
    throw new Error("版が違います（実行=" + info.version + "、正本=" + V.version + "）。");
  }
  if (!info.lxml) {
    throw new Error("lxmlを使えません。PC版と解析結果が変わるおそれがあるため停止します（計画書■6）。");
  }
  info.pyodide = py.version;
  KEIBA.py = py;
  KEIBA.info = info;
  return info;
}

async function keibaWriteFile(path, file) {
  const buf = new Uint8Array(await file.arrayBuffer());
  KEIBA.py.FS.writeFile(path, buf);
}

function keibaCall(fn, ...args) {
  // 文字列の引数をPythonの関数に渡し、JSONで受け取る
  const f = KEIBA.py.globals.get("runner")[fn];
  const r = f(...args);
  if (typeof f.destroy === "function") f.destroy();
  return JSON.parse(r);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function inlineMd(s) {
  return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

// 分析計算の出力（Markdownの表・太字・コードブロック）を表示用HTMLにする。数値・文字は書き換えない。
function renderOutput(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  const html = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (ln.startsWith("```")) {
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      html.push('<pre class="code">' + escapeHtml(buf.join("\n")) + "</pre>");
      continue;
    }
    if (ln.trim().startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++].trim());
      const cells = (r) => r.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      let t = '<div class="tblwrap"><table>';
      rows.forEach((r, k) => {
        if (/^\|[\s\-:|]+\|$/.test(r)) return;
        const tag = k === 0 ? "th" : "td";
        t += "<tr>" + cells(r).map((c) => "<" + tag + ">" + inlineMd(c) + "</" + tag + ">").join("") + "</tr>";
      });
      html.push(t + "</table></div>");
      continue;
    }
    if (ln.startsWith("REC ")) {
      html.push('<pre class="code rec">' + escapeHtml(ln) + "</pre>");
    } else if (ln.trim() === "") {
      html.push("");
    } else {
      html.push("<p>" + inlineMd(ln) + "</p>");
    }
    i++;
  }
  return html.join("\n");
}

function downloadText(name, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

async function showBkstat() {
  const b = document.getElementById("bkstat");
  if (!b || typeof storeBackupStatus !== "function" || !STORE.db) return;
  const st = await storeBackupStatus();
  b.innerHTML = escapeHtml(st.msg + "　／　記録 " + st.total + "件（うち結果登録 " + st.registered + "件）") + "　<a href='data.html'>バックアップ →</a>";
  b.className = "bkstat" + (st.warn ? " warn" : "");
}

function footerText(info) {
  const V = BUNDLE.version;
  return "版 " + V.version + " ／ 指紋 分析計算 " + (info ? info.code : V.code) + "・考察計算 " + (info ? info.code_k : V.code_k) + " ／ Pyodide " +
    (info ? info.pyodide : V.pyodide) + "（Python " + (info ? info.python : "-") + "） ／ 仮想購入のみ（実際の馬券は購入しません）";
}
