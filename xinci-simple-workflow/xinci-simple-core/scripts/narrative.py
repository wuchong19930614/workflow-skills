#!/usr/bin/env python3
"""「为什么是这个词」——报告开篇的人话叙述。

写法上只有一条硬规矩:**每个小节的第一句必须是加粗的大白话结论**(有/没有、会/不会、
打得过/难打、多少钱),之后才是两三句支撑。此前的版本每节都是分析堆砌,读完不知道
答案是"能"还是"不能",这是用户明确指出的问题。

所有句子从账本与 verify 观察的结构化字段派生,措辞按数据落在哪个区间选择,
不接受执行者手写的自由文本,也不把观察 points 与 ai_overview.excerpt 的原文
倒进来(那些是机器化的采集记录,叙述只讲判断并指向原文所在的节次)。
同一份数据永远产出同一段话,读者能反查每个数字。
"""

FORM_TASK = {
    "info": "查一个解释或清单",
    "lookup": "按对象查一个数或一个判断",
    "tool": "输入几个参数、算出一个结果",
    "commercial": "挑一个要买的东西",
    "mixed": "既要查也要挑",
}
SEED_ORIGIN = {
    "root": "Semrush 词根轮换",
    "small_site": "低权重小站反推",
    "forum": "论坛里被反复问、每次靠人肉回答",
}
NICHE_LABEL = {"tech": "科技/通用", "home": "家居 · DIY · 汽车", "hobby": "爱好/宠物"}
FILLER_KIND = {"video": "视频", "forum": "论坛帖", "article": "泛泛的文章",
               "brand": "品牌页", "official": "官方或厂商页", "other": "其他"}


def _fmt(n):
    return f"{n:,}" if isinstance(n, int) else (f"{n:,.0f}" if isinstance(n, float) else str(n))


def _money(n):
    return f"${n:,.0f}" if isinstance(n, (int, float)) else str(n)


def _volume(rec):
    cluster = rec["cluster"]
    total = cluster["total_volume"]
    kws = [k for k in cluster.get("keywords", []) if isinstance(k.get("volume"), int)]
    head = next((k for k in kws if k["term"] == rec["primary_keyword"]), None)
    longtail = sorted((k for k in kws if k is not head), key=lambda k: -k["volume"])
    scattered = bool(head and total and head["volume"] / total < 0.1)
    if total >= 200000:
        verdict = f"**有，量很足。每月约 {_fmt(total)} 次。"
    elif total >= 100000:
        verdict = f"**有。每月约 {_fmt(total)} 次。"
    else:
        verdict = f"**量偏小，每月约 {_fmt(total)} 次。"
    verdict += ("而且搜的人带着自己的场景来，不是来看定义的。**" if scattered else "**")
    out = [verdict, ""]
    if head and longtail:
        out.append(f"主词 `{rec['primary_keyword']}` 自己只占 {_fmt(head['volume'])} 次，量都在具体问法上——"
                   + "、".join(f"`{k['term']}` {_fmt(k['volume'])}" for k in longtail[:3]) + "。")
    elif longtail:
        out.append("量最大的几个问法："
                   + "、".join(f"`{k['term']}` {_fmt(k['volume'])}" for k in longtail[:3]) + "。")
    lowkd = sorted((k for k in longtail if isinstance(k.get("kd"), (int, float)) and k["kd"] <= 20),
                   key=lambda k: k["kd"])[:4]
    tail = (f"其中 {len(lowkd)} 个问法的难度只有 " + "、".join(str(int(k['kd'])) for k in lowkd)
            + "，这一档新站挤得进去。") if lowkd else ""
    out.append(f"{tail}来源：{SEED_ORIGIN.get(rec['seed'].get('type'), '未记录')}。".lstrip())
    return out


def _aio(verify_obs):
    aio = verify_obs.get("ai_overview") or {}
    if not aio.get("present"):
        return ["**不会——这个词连 AI 摘要都没有，点击完整留在自然结果里。**", "",
                "Google 判断给链接比自己作答更有用。这是眼下最难得的一种情形，收入不用为它打折。"]
    out = ["**不会。它只给了通用口径，用户要的那个结果还得自己动手。**", ""]
    if (aio.get("excerpt") or "").strip():
        out.append("它到底说了什么、又在哪里停下来，原文摘在下面「完整数据与证据」的第 5 节。")
    out.append("代价是这部分点击要打折算收入（见「能赚多少」）。")
    return out


def _beat(verify_obs):
    top = verify_obs.get("serp_top10") or []
    done = [r for r in top if r.get("completes_task")]
    strong = [r for r in done if isinstance(r.get("dr"), (int, float)) and r["dr"] >= 50]
    weak = [r for r in done if isinstance(r.get("dr"), (int, float)) and r["dr"] < 50]
    unknown = [r for r in done if r.get("dr") is None]
    filler = [r for r in top if not r.get("completes_task")]
    top_weak = min(weak, key=lambda r: r.get("pos", 99)) if weak else None
    if len(strong) >= 3:
        verdict = f"**难打。首页有 {len(strong)} 个权重高又真把事办完的对手。**"
    elif not strong:
        verdict = "**打得过。首页没有一个权重高又真把事办完的对手。**"
    elif top_weak:
        verdict = (f"**打得过。硬对手只有 {len(strong)} 个，"
                   f"而排第 {top_weak.get('pos')} 位的是权重仅 {int(top_weak['dr'])} 的小站。**")
    else:
        verdict = f"**有机会。首页 {len(strong)} 个硬对手，其余都没解决问题。**"
    out = [verdict, ""]
    detail = [f"首页 {len(top)} 条里真把这件事办完的有 {len(done)} 个"]
    if strong:
        detail.append("硬对手是 " + "、".join(f"**{r['domain']}**（权重 {int(r['dr'])}）" for r in strong))
    if top_weak:
        detail.append(f"**{top_weak['domain']}** 权重只有 {int(top_weak['dr'])} 却占着第 "
                      f"{top_weak.get('pos')} 位——这一格拼的不是域名家底，是有没有把活干完")
    if filler:
        detail.append(f"剩下 {len(filler)} 条是"
                      + "、".join(sorted({FILLER_KIND.get(r.get('type'), '其他') for r in filler}))
                      + "，占着位置但没解决问题")
    out.append("；".join(detail) + "。")
    if unknown:
        out.append(f"另有 {len(unknown)} 条办完了任务但权重没实测"
                   f"（{', '.join(r['domain'] for r in unknown)}），没算作硬对手——"
                   "硬对手可能被低估。")
    return out


def _money_sec(rec):
    rev = rec["revenue"]
    inp = rev.get("inputs", {})
    th, base = rev["threshold"], rev["base"]
    gap = base - th
    verdict = (f"**中性 {_money(base)}／月，比门槛 {_money(th)} 高 {_money(gap)}。这已经是打完折的数。**"
               if gap >= 0 else
               f"**中性 {_money(base)}／月，差 {_money(-gap)} 到门槛 {_money(th)}。**")
    out = [verdict, "",
           f"保守 {_money(rev['downside'])}／乐观 {_money(rev['upside'])}。任务形态是"
           f"「{FORM_TASK.get(rec.get('form'), rec.get('form'))}」，"
           f"归到「{NICHE_LABEL.get(inp.get('niche'), inp.get('niche') or '未记录')}」垂类，按展示广告口径估。"]
    cuts = []
    if inp.get("aio_present"):
        cuts.append("AI 摘要在场，点击打 **6 折**")
    if inp.get("strong_complete_count") in (1, 2):
        cuts.append(f"有 {inp['strong_complete_count']} 个硬对手，再打 **7 折**")
    need, total = rev.get("volume_needed_for_threshold"), rec["cluster"]["total_volume"]
    margin = ""
    if isinstance(need, int) and need > 0:
        pct = total / need - 1
        margin = (f"到门槛需要 {_fmt(need)} 的簇量，实测 {_fmt(total)}，高出 **{pct * 100:.0f}%**——"
                  "余量不厚，假设悲观一点就会掉下去。" if pct >= 0
                  else f"到门槛需要 {_fmt(need)} 的簇量，实测只有 {_fmt(total)}。")
    if cuts:
        out.append("坏事已经算进去了：" + "；".join(cuts) + "。" + margin)
    else:
        out.append("这个数**没有打任何折**——既没有 AI 摘要抢答，也没有权重高的硬对手。" + margin)
    return out


def _risks(rec, verify_obs):
    aio = verify_obs.get("ai_overview") or {}
    top = verify_obs.get("serp_top10") or []
    strong = [r for r in top if r.get("completes_task")
              and isinstance(r.get("dr"), (int, float)) and r["dr"] >= 50]
    items = []
    if aio.get("present"):
        items.append(("AI 摘要会继续往前吃",
                      "今天它只答了一半，明天可能把要算的那步也接过去。建站后要盯这一屏。"))
    else:
        items.append(("现在没有 AI 摘要，但不保证一直没有",
                      "一旦出现，点击会先掉一截。"))
    if strong:
        items.append((f"{strong[0]['domain']} 这类大站已经在场",
                      "它现在只占一个位置，但认真做这个方向就能靠权重压过来。"))
    if "未" in (verify_obs.get("trends_12m") or "") or not verify_obs.get("trends_12m"):
        items.append(("季节性没拿到数值证据",
                      "Trends 的图在两条通道都读不出来，报告里用的是替代证据。建站前自己核一遍月度分布。"))
    missing = [r for r in top if r.get("completes_task") and r.get("dr") is None]
    if missing:
        items.append((f"{len(missing)} 条办完任务的结果没测权重", "硬对手可能被低估，收入可能被高估。"))
    big = rec["cluster"]["total_volume"] >= 150000
    items.append(("打法是 `cluster_expansion`（先拿小词再攻主词）" if big
                  else "打法是 `single_domain`（一站一簇做深）",
                  "簇够大，要铺一批页面，不是一页了事。" if big else "簇不大，适合一个域名把这件事做到最好。"))
    out = [f"**最需要盯的是：{items[0][0]}。**", ""]
    out += [f"{i}. **{t}。** {d}" for i, (t, d) in enumerate(items, 1)]
    return out


def build(rec, verify_obs) -> str:
    rev = rec["revenue"]
    passed = rev["base"] >= rev["threshold"]
    lines = ["## 为什么是这个词", "",
             f"一句话：**有人在搜、Google 没把活干完、首页占位者家底不厚，"
             f"打完折算中性 {_money(rev['base'])}／月，{'过线' if passed else '未过线'}。**", "",
             "### 有人在搜吗", ""]
    lines += _volume(rec) + ["", "### Google 会不会自己答完", ""]
    lines += _aio(verify_obs) + ["", "### 打得过吗", ""]
    lines += _beat(verify_obs) + ["", "### 能赚多少", ""]
    lines += _money_sec(rec) + ["", "### 最大的风险", ""]
    lines += _risks(rec, verify_obs)
    lines += ["", "建站与否是你的决定。每个数字的出处在下面「完整数据与证据」里。", ""]
    return "\n".join(lines)
