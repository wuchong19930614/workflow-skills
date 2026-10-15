// xinci-bench 新词快道:在 trends.google.com 的页面里运行,调 Trends 内部接口取数(curl 直接请求会 429)。
// 用法:内置浏览器先打开 https://trends.google.com/trends/explore?hl=en-US,再把本文件全文加一行调用,在同一次执行里交给页面:
//   await xinciTrends({geo: "GB", terms: ["<新词>", "<锚词>"]})    // 某国 30 天逐日曲线,新词与锚词同一次查询
//   await xinciTrendsRising({term: "beta", cat: 8})                 // 某个种子词近 7 天的飙升相关查询(cat 8 = 游戏分类)
//   await xinciTrendsFirstSeen({term: "huss valley"})                // 查不到开玩日期时:对象名近 90 天第一次有热度的那天
// 每次执行的作用域互不相通,函数定义不会保留,所以每次都要带全文。返回的 JSON 原样存下:
// 曲线交给 trends_volume.py;飙升词由执行者挑出对象与说法,写进 quick_signal(source=trends_rising)。
// 脚本内部两次请求间隔 1.5 秒;遇到 HTTP 429 停下,不要连续重试。按地区分布的接口(comparedgeo)2026-10-14 实测连续 429,不用。
// 飙升词 2026-10-14 实测:间隔 6 秒连查到第 3 次就 429,所以两次执行之间隔 30 秒以上,每次运行最多查 6 个种子词。
async function xinciTrends({geo, terms, time = "today 1-m"}) {
  const EN = ["US", "GB", "CA", "AU", "NZ", "IE"];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const get = async url => {
    const res = await fetch(url, {credentials: "include"});
    if (!res.ok) throw new Error(`HTTP ${res.status}:${url.slice(0, 90)}`);
    const text = await res.text();
    return JSON.parse(text.slice(text.indexOf("{")));            // 切掉 )]}' 前缀
  };
  if (!Array.isArray(terms) || terms.length !== 2 || !EN.includes(geo)) {
    throw new Error("须给 2 个词(新词、锚词)和英文区国家代码 US/GB/CA/AU/NZ/IE");
  }
  const req = {comparisonItem: terms.map(k => ({keyword: k, geo, time})), category: 0, property: ""};
  const explore = await get(`/trends/api/explore?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(req))}`);
  const w = explore.widgets.find(x => x.id === "TIMESERIES");
  if (!w) throw new Error("没有 TIMESERIES 组件");
  await sleep(1500);
  const data = await get(`/trends/api/widgetdata/multiline?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(w.request))}&token=${w.token}`);
  const rows = data.default.timelineData.filter(p => !p.isPartial);   // 去掉当天还没走完的点
  return {geo, terms, time,
          url: `https://trends.google.com/trends/explore?date=${encodeURIComponent(time)}&geo=${geo}&q=${encodeURIComponent(terms.join(","))}&hl=en-US`,
          dates: rows.map(p => new Date(Number(p.time) * 1000).toISOString().slice(0, 10)),
          values: rows.map(p => p.value.map(Number))};
}


async function xinciTrendsRising({term, geo = "US", time = "now 7-d", cat = 0}) {
  const EN = ["US", "GB", "CA", "AU", "NZ", "IE"];
  const NOISE = /crossword|clue|wordle/i;                          // 游戏分类里混着填字游戏提示词,丢掉
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const get = async url => {
    const res = await fetch(url, {credentials: "include"});
    if (!res.ok) throw new Error(`HTTP ${res.status}:${url.slice(0, 90)}`);
    const text = await res.text();
    return JSON.parse(text.slice(text.indexOf("{")));
  };
  if (typeof term !== "string" || !term.trim() || !EN.includes(geo)) {
    throw new Error("须给 1 个种子词和英文区国家代码 US/GB/CA/AU/NZ/IE");
  }
  const req = {comparisonItem: [{keyword: term, geo, time}], category: cat, property: ""};
  const explore = await get(`/trends/api/explore?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(req))}`);
  const w = explore.widgets.find(x => x.id === "RELATED_QUERIES");
  if (!w) throw new Error("没有 RELATED_QUERIES 组件(量太小时 Trends 不给相关查询)");
  await sleep(1500);
  const data = await get(`/trends/api/widgetdata/relatedsearches?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(w.request))}&token=${w.token}`);
  const [top = {}, rising = {}] = data.default.rankedList;
  const keep = list => (list.rankedKeyword || []).filter(k => !NOISE.test(k.query));
  return {geo, term, time, cat,
          url: `https://trends.google.com/trends/explore?date=${encodeURIComponent(time)}&geo=${geo}&q=${encodeURIComponent(term)}&cat=${cat}&hl=en-US`,
          top: keep(top).map(k => ({query: k.query, value: k.value})),
          rising: keep(rising).map(k => ({query: k.query, rising: k.formattedValue === "Breakout" ? "breakout" : Number(k.value)})),
          dropped_noise: (rising.rankedKeyword || []).length - keep(rising).length};
}


async function xinciTrendsFirstSeen({term, geo = "US", time = "today 3-m"}) {
  // 用户 2026-10-15 定:Roblox 这类从对象页面和首页都读不到开玩日期的,用 Trends 上对象名第一次有热度的那天当开玩日。
  // 窗口开头至少 7 天全为 0 才认首次出现日;开头就有热度说明早于窗口(约 90 天),Q1 不过;一直为 0 则读不出,Q1 仍记 null。
  const EN = ["US", "GB", "CA", "AU", "NZ", "IE"];
  const LEAD_ZERO_DAYS = 7;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const get = async url => {
    const res = await fetch(url, {credentials: "include"});
    if (!res.ok) throw new Error(`HTTP ${res.status}:${url.slice(0, 90)}`);
    const text = await res.text();
    return JSON.parse(text.slice(text.indexOf("{")));
  };
  if (typeof term !== "string" || !term.trim() || !EN.includes(geo)) {
    throw new Error("须给 1 个对象名和英文区国家代码 US/GB/CA/AU/NZ/IE");
  }
  const req = {comparisonItem: [{keyword: term, geo, time}], category: 0, property: ""};
  const explore = await get(`/trends/api/explore?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(req))}`);
  const w = explore.widgets.find(x => x.id === "TIMESERIES");
  if (!w) throw new Error("没有 TIMESERIES 组件");
  await sleep(1500);
  const data = await get(`/trends/api/widgetdata/multiline?hl=en-US&tz=0&req=${encodeURIComponent(JSON.stringify(w.request))}&token=${w.token}`);
  const rows = data.default.timelineData.filter(p => !p.isPartial);
  const dates = rows.map(p => new Date(Number(p.time) * 1000).toISOString().slice(0, 10));
  const values = rows.map(p => Number(p.value[0]));
  const i = values.findIndex(v => v > 0);
  return {geo, term, time,
          url: `https://trends.google.com/trends/explore?date=${encodeURIComponent(time)}&geo=${geo}&q=${encodeURIComponent(term)}&hl=en-US`,
          dates, values,
          first_seen: i >= LEAD_ZERO_DAYS ? dates[i] : null,
          before_window: i >= 0 && i < LEAD_ZERO_DAYS,
          never: i < 0};
}
