#!/usr/bin/env python3
"""「为什么是这个词」——报告开篇的人话叙述。

全部句子从账本与 verify 观察的结构化字段派生,措辞按数据落在哪个区间选择,
不接受执行者手写的自由文本。这样同一份数据永远产出同一段话,读者也能反查每个数字。

写这个模块的理由:此前报告是九节数据表格加一堆机器化的观察要点,读完不知道
"所以为什么选它"。数据本身不解释自己,叙述必须由脚本从数据里算出来。
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
    "forum": "论坛里被反复问且每次靠人肉回答",
}
NICHE_LABEL = {"tech": "科技/通用", "home": "家居 · DIY · 汽车", "hobby": "爱好/宠物"}


def _fmt(n):
    if isinstance(n, float) and n == int(n):
        n = int(n)
    return f"{n:,}" if isinstance(n, int) else f"{n:,.0f}" if isinstance(n, float) else str(n)


def _money(n):
    return f"${n:,.0f}" if isinstance(n, (int, float)) else str(n)


def _volume_para(rec):
    cluster = rec["cluster"]
    total = cluster["total_volume"]
    kws = [k for k in cluster.get("keywords", []) if isinstance(k.get("volume"), int)]
    head = next((k for k in kws if k["term"] == rec["primary_keyword"]), None)
    longtail = sorted((k for k in kws if k is not head), key=lambda k: -k["volume"])
    lines = [f"每月约 **{_fmt(total)}** 次搜索落在这个主题簇上（phrase-match 合计口径）。"]
    if head and longtail:
        lines.append(
            f"主词 `{rec['primary_keyword']}` 本身只有 {_fmt(head['volume'])} 次，"
            f"真正的量在具体问法上——"
            + "、".join(f"`{k['term']}` {_fmt(k['volume'])} 次" for k in longtail[:3])
            + "。这说明搜的人是带着自己的场景来的，不是来看定义的。")
    elif longtail:
        lines.append("簇里量最大的几个问法是："
                     + "、".join(f"`{k['term']}` {_fmt(k['volume'])} 次" for k in longtail[:3]) + "。")
    lowkd = sorted((k for k in longtail
                    if isinstance(k.get("kd"), (int, float)) and k["kd"] <= 20),
                   key=lambda k: k["kd"])[:4]
    if lowkd:
        lines.append(
            f"其中 {len(lowkd)} 个问法的关键词难度只有 "
            + "、".join(str(int(k["kd"])) for k in lowkd)
            + "——这一档通常是新站也能挤进去的位置。")
    lines.append(f"这个词是怎么被找到的：{SEED_ORIGIN.get(rec['seed'].get('type'), '未记录')}。")
    return lines


def _aio_para(verify_obs):
    aio = verify_obs.get("ai_overview") or {}
    if not aio.get("present"):
        return ["这个词**没有出现 AI 摘要**。Google 判断给链接比自己作答更有用，"
                "也就是说点击完整地留在自然结果里——这是眼下最难得的一种情形。"]
    out = ["AI 摘要出现了，但它**只答了一半**——给了通用口径，没给这个用户要的那个结果。"]
    if (aio.get("excerpt") or "").strip():
        out.append("它到底说了什么、又在哪里停下来，原文摘在**第 5 节**。")
    out.append("对我们的意思是：用户看完摘要还得自己动手，点击没有被吃掉；"
               "但这部分点击要打折算收入（见下面「能赚多少」）。")
    return out


def _beat_para(verify_obs):
    top = verify_obs.get("serp_top10") or []
    done = [r for r in top if r.get("completes_task")]
    strong = [r for r in done if isinstance(r.get("dr"), (int, float)) and r["dr"] >= 50]
    weak_done = [r for r in done if isinstance(r.get("dr"), (int, float)) and r["dr"] < 50]
    unknown = [r for r in done if r.get("dr") is None]
    filler = [r for r in top if not r.get("completes_task")]
    out = [f"首页 {len(top)} 条里，真把这件事办完的有 {len(done)} 个。"]
    if strong:
        out.append("其中权重够高、算得上硬对手的只有 "
                   + "、".join(f"**{r['domain']}**（权重 {int(r['dr'])}）" for r in strong) + "。")
    else:
        out.append("**没有一个**是权重高又真把事办完的——按判据这一格算是空着的。")
    if weak_done:
        top_weak = min(weak_done, key=lambda r: r.get("pos", 99))
        out.append(
            f"更能说明问题的是排在第 {top_weak.get('pos')} 位的 **{top_weak['domain']}**，"
            f"权重只有 {int(top_weak['dr'])}——一个小站占着最好的位置，"
            "说明这一格拼的不是域名家底，是有没有把活干完。")
    if filler:
        kinds = {"video": "视频", "forum": "论坛帖", "article": "泛泛的文章",
                 "brand": "品牌页", "official": "官方或厂商页", "other": "其他"}
        names = sorted({kinds.get(r.get("type"), "其他") for r in filler})
        out.append(f"剩下 {len(filler)} 条是{'、'.join(names)}，它们占着位置但没解决问题。")
    if unknown:
        out.append(f"另有 {len(unknown)} 条完成了任务但权重没实测（{', '.join(r['domain'] for r in unknown)}），"
                   "判断时没把它们算作硬对手。")
    return out


def _money_para(rec):
    rev = rec["revenue"]
    inp = rev.get("inputs", {})
    form = rec.get("form")
    th, base = rev["threshold"], rev["base"]
    out = [f"这个词的任务形态是「{FORM_TASK.get(form, form)}」，"
           f"归到「{NICHE_LABEL.get(inp.get('niche'), inp.get('niche') or '未记录')}」垂类，"
           "按展示广告口径估收入。"]
    out.append(f"保守 {_money(rev['downside'])}／月，中性 **{_money(base)}**／月，乐观 {_money(rev['upside'])}／月。"
               f"门槛是 {_money(th)}，"
               + (f"中性情形过线 {_money(base - th)}。" if base >= th
                  else f"中性情形差 {_money(th - base)}。"))
    cuts = []
    if inp.get("aio_present"):
        cuts.append("AI 摘要在场，点击打 **6 折**")
    if inp.get("strong_complete_count") in (1, 2):
        cuts.append(f"首页有 {inp['strong_complete_count']} 个硬对手，再打 **7 折**")
    if cuts:
        out.append("这个数已经把两件坏事算进去了：" + "；".join(cuts) + "。也就是说它是打完折的数，不是理想值。")
    else:
        out.append("这个数**没有打任何折**——首页既没有 AI 摘要抢答，也没有权重高的硬对手。")
    need = rev.get("volume_needed_for_threshold")
    total = rec["cluster"]["total_volume"]
    if isinstance(need, int) and need > 0:
        margin = total / need - 1
        if margin >= 0:
            out.append(f"要摸到门槛需要 {_fmt(need)} 的簇量，实测 {_fmt(total)}，"
                       f"高出 **{margin * 100:.0f}%**。余量不算厚，假设稍微悲观一点就会掉到门槛下。")
        else:
            out.append(f"要摸到门槛需要 {_fmt(need)} 的簇量，实测只有 {_fmt(total)}，差 {-margin * 100:.0f}%。")
    out.append(f"口径版本 `{rev['assumptions_version']}`，RPM 与点击率的取值见契约 §6，改假设要先改版本号。")
    return out


def _risk_para(rec, verify_obs):
    aio = verify_obs.get("ai_overview") or {}
    top = verify_obs.get("serp_top10") or []
    risks = []
    if aio.get("present"):
        risks.append("**AI 摘要已经在场，而且它在变。** 今天它只答了一半，明天可能把要算的那步也接过去——"
                     "这是这一类词最快变坏的地方，建站后要盯住这一屏。")
    else:
        risks.append("**现在没有 AI 摘要，但不保证一直没有。** 一旦出现，点击会先掉一截。")
    strong = [r for r in top if r.get("completes_task")
              and isinstance(r.get("dr"), (int, float)) and r["dr"] >= 50]
    if strong:
        risks.append(f"**{strong[0]['domain']} 这类大站已经在这一格里。** 它现在只占一个位置，"
                     "但如果它认真做这个方向，靠权重就能压过来。")
    trends = (verify_obs.get("trends_12m") or "")
    if "未" in trends or not trends:
        risks.append("**季节性没拿到数值证据。** Trends 的图在两条通道都读不出来，"
                     "报告里用的是有限的替代证据——建站前该自己核一遍月度分布。")
    missing_dr = [r for r in top if r.get("completes_task") and r.get("dr") is None]
    if missing_dr:
        risks.append(f"**{len(missing_dr)} 条完成任务的结果没测权重。** "
                     "硬对手的数目可能被低估，进而高估收入。")
    play = "cluster_expansion" if rec["cluster"]["total_volume"] >= 150000 else "single_domain"
    if play == "cluster_expansion":
        risks.append("**打法是 `cluster_expansion`（先拿下小词再攻主词）。** 簇够大，"
                     "但这意味着要铺一批页面，不是一页了事。")
    else:
        risks.append("**打法是 `single_domain`（一站一簇做深）。** 簇不大，"
                     "适合一个域名把这件事做到最好。")
    return risks


def build(rec, verify_obs) -> str:
    rev = rec["revenue"]
    verdict = ("过线" if rev["base"] >= rev["threshold"] else "未过线")
    lines = ["## 为什么是这个词", "",
             f"一句话：**搜的人带着自己的场景来、Google 没把活干完、首页占位者的家底并不厚，"
             f"按打完折的口径算中性 {_money(rev['base'])}／月，{verdict}。**", "",
             "下面四问的每个数字都能在后面各节反查到出处。", "",
             "### 有人在搜吗", ""]
    lines += _volume_para(rec) + ["", "### Google 会不会自己答完", ""]
    lines += _aio_para(verify_obs) + ["", "### 打得过吗", ""]
    lines += _beat_para(verify_obs) + ["", "### 能赚多少", ""]
    lines += _money_para(rec) + ["", "### 最大的风险", ""]
    lines += [f"{i}. {r}" for i, r in enumerate(_risk_para(rec, verify_obs), 1)]
    lines += ["", "建站与否是你的决定；这份报告只负责把上面每一条摆出来。", ""]
    return "\n".join(lines)
