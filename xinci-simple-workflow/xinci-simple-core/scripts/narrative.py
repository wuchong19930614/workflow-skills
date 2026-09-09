"""从已核验任务组生成简短、可复核的报告叙述。"""
import qualification as Q


def build_groups(rec, observations):
    """已通过任务组的短叙述；只描述覆盖范围内的现场及模型结果。"""
    rev = rec['revenue']
    volume = rev['inputs']['cluster_volume']
    raw = rec['cluster']['total_volume']
    counts = [len(Q.strong_results(o)[0]) for o in observations]
    aio_count = sum(o['ai_overview']['present'] for o in observations)
    return '\n'.join([
        '## 为什么是这个词', '', '### 有人在搜吗', '',
        f'**有。已核验任务组覆盖月搜索量 {volume:,}。**', '',
        f'原始查询总量为 {raw:,}；其余 {raw-volume:,} 未计入收入。搜索量不是本站预计访问量。', '',
        '### Google 会不会自己答完', '',
        '**本次代表查询没有被首屏完整回答。**', '',
        f'共核验 {len(observations)} 组，其中 {aio_count} 组出现未完成任务的 AI 摘要，分别应用 6 折。结论只覆盖已核验的任务组。', '',
        '### 打得过吗', '', '**有机会，仍需实际争取排名。**', '',
        f'各组满足完整任务、AS ≥ 50、新鲜且格式正确的强对手数为 {"、".join(map(str, counts))}；不是排名保证。', '',
        '### 能赚多少', '', f"**当前假设下 base 为 ${rev['base']:,.2f}/月，门槛 ${rev['threshold']}/月。**", '',
        f"downside ${rev['downside']:,.2f}，upside ${rev['upside']:,.2f}。每组按自身形态、垂类与折减计算后相加。", '',
        '### 最大的风险', '', '**收入是模型估算，未覆盖词量和实际排名仍有不确定性。**', '',
        '证据是一次现场快照；三情景仅改变 CTR，不能代替对佣金、RPM 和代表查询覆盖范围的复核。', ''
    ])
