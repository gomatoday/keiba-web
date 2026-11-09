// 出走表のまとめて分析。1ファイルずつ keiba_v47.py の predict を実行し、結果を記録する（計算は1レースずつと同じ）。
"use strict";

// files: Fileの配列。onProgress(k, n, row)。戻り値: 行の配列 {file, race_id, venue, rno, mode, rc, status, note, stdout}
async function bulkAnalyze(files, onProgress, opts) {
  const keepStdout = opts && opts.keepStdout;
  const rows = [];
  for (let k = 0; k < files.length; k++) {
    const f = files[k];
    const row = { file: f.name, race_id: null, venue: "", rno: null, mode: "", rc: null, status: "", note: "" };
    await new Promise((ok) => setTimeout(ok, 15));
    try {
      await keibaWriteFile("/work/bulk_race.html", f);
      const res = keibaCall("analyze", "/work/bulk_race.html", "");
      row.rc = res.rc;
      if (keepStdout) row.stdout = res.stdout;
      const lines = res.stdout.trim().split("\n");
      if (res.rc === 0 && res.rec) {
        const rec = res.rec;
        row.race_id = rec.race_id; row.venue = rec.venue; row.rno = Number(rec.race_id.slice(-2)); row.mode = rec.mode;
        if (STORE.db) {
          const sv = await storeSaveAnalysis(res.stdout);
          row.status = sv.saved ? "記録しました" : "記録なし";
          row.note = sv.saved ? (rec.warnings || []).length + "件の警告" : sv.reason;
        } else {
          row.status = "分析のみ（記録を開けません）";
        }
      } else if (res.rc === 0) {
        row.status = "見送り・買い目なし";
        row.note = lines.slice(-3).join(" ").slice(0, 200);
      } else {
        row.status = "エラー・停止";
        row.note = lines.filter((l) => /エラー|停止/.test(l)).join(" ").slice(0, 200) || lines.pop().slice(0, 200);
      }
      const m = res.stdout.match(/(\d{16})/);
      if (!row.race_id && m) row.race_id = m[1];
    } catch (e) {
      row.status = "実行エラー";
      row.note = e.message;
    }
    rows.push(row);
    if (onProgress) onProgress(k + 1, files.length, row);
  }
  return rows;
}
