// calendar.js  南関東の年間開催日程ページ（calendar/YYYYMM.do を保存したHTML）から開催日を読み取る。
// 開催日のマス（<td>）のうち、レース一覧ページ /program/日付8桁+会場2桁+回2桁+日目2桁.do へのリンクがあるものを拾う。
(function (root) {
  var VENUE = { "18": "浦和", "19": "船橋", "20": "大井", "21": "川崎" };
  var WEEK = ["日", "月", "火", "水", "木", "金", "土"];

  function parseCalendar(html) {
    var days = {};
    var cells = String(html).split(/<td\b/i);
    for (var i = 1; i < cells.length; i++) {
      var cell = cells[i].split(/<\/td>/i)[0];
      var m = /\/program\/(\d{8})(\d{2})(\d{2})(\d{2})\.do/.exec(cell);
      if (!m || m[1] === "00000000" || !VENUE[m[2]]) continue;
      var code = m[1] + m[2] + m[3] + m[4];
      var alt = (/<img[^>]*alt="([^"]*)"/.exec(cell) || [])[1] || "";
      var grades = [];
      var g, gre = /nk23_c-table21__text[^>]*>([^<]*)</g;
      while ((g = gre.exec(cell))) { var t = g[1].trim(); if (t) grades.push(t); }
      var y = +m[1].slice(0, 4), mo = +m[1].slice(4, 6), d = +m[1].slice(6, 8);
      days[code] = {
        code: code,
        date: m[1],
        venueCode: m[2],
        venue: VENUE[m[2]],
        kai: +m[3],
        nichi: +m[4],
        week: WEEK[new Date(y, mo - 1, d).getDay()],
        label: mo + "/" + d,
        time: alt.indexOf("ナイター") >= 0 ? "ナイター" : (alt ? "昼" : ""),
        grades: grades
      };
    }
    return Object.keys(days).sort().map(function (k) { return days[k]; });
  }

  // 開催（会場＋回）ごとにまとめる
  function groupMeetings(days) {
    var map = {}, order = [];
    days.forEach(function (d) {
      var key = d.date.slice(0, 4) + d.venueCode + ("0" + d.kai).slice(-2);
      if (!map[key]) { map[key] = { key: key, venue: d.venue, kai: d.kai, days: [] }; order.push(key); }
      map[key].days.push(d);
    });
    var list = order.map(function (k) { return map[k]; });
    list.sort(function (a, b) { return a.days[0].date < b.days[0].date ? -1 : a.days[0].date > b.days[0].date ? 1 : (a.key < b.key ? -1 : 1); });
    return list;
  }

  var api = { parseCalendar: parseCalendar, groupMeetings: groupMeetings, VENUE: VENUE };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.NankanCalendar = api;
})(this);
