// xinci-bench 新词快道:在 trends.google.com 的页面里运行,调 Trends 内部接口取数(curl 直接请求会 429)。
// 用法:内置浏览器先打开 https://trends.google.com/trends/explore?hl=en-US,再把本文件全文加一行调用,在同一次执行里交给页面:
//   await xinciTrends({geo: "GB", terms: ["<新词>", "<锚词>"]})    // 某国 30 天逐日曲线,新词与锚词同一次查询
// 每次执行的作用域互不相通,函数定义不会保留,所以每次都要带全文。返回的 JSON 原样存下,交给 trends_volume.py。
// 脚本内部两次请求间隔 1.5 秒;遇到 HTTP 429 停下,不要连续重试。按地区分布的接口(comparedgeo)2026-10-14 实测连续 429,不用。
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
