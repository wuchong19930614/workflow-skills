"""新词工作流的中文展示词汇。

磁盘和 Python API 继续使用稳定的英文机器码；所有面向人的命令行输出
统一通过本模块翻译，避免展示层反向污染数据契约。
"""

SESSION_STATUS_LABELS = {
    "active": "运行中",
    "go": "已产出可交付结论",
    "quota_exhausted": "查询额度已用完",
    "budget_reached": "运行预算已用完",
    "resource_exhausted": "会话资源已用完",
    "blocked": "执行受阻",
    "cancelled": "已取消",
}

SESSION_STATUS_ALIASES = {
    **{value: key for key, value in SESSION_STATUS_LABELS.items()},
    "额度已用完": "quota_exhausted",
    "预算已用完": "budget_reached",
    "资源已用完": "resource_exhausted",
    "受阻": "blocked",
    "取消": "cancelled",
}

CANDIDATE_STATE_LABELS = {
    "captured": "已捕获，待补闸",
    "screened": "窗口初筛通过",
    "tracking": "跟踪中",
    "formation_confirmed": "需求形成已确认",
    "qualified": "机会已认定",
    "build_ready": "建站就绪",
    "pilot_ready": "试点就绪",
    "fast_grab_ready": "快速抢占就绪",
    "hold": "暂缓决策",
    "rejected": "已否决",
    "expired": "已过期",
    "superseded": "已被替代",
    "withdrawn": "已撤回",
    "built": "已建成",
    "disqualified": "未通过认定",
    "no_site": "不建站",
}


def session_status_label(value):
    return SESSION_STATUS_LABELS.get(value, f"未知状态（{value}）")


def candidate_state_label(value):
    return CANDIDATE_STATE_LABELS.get(value, f"未知状态（{value}）")


def normalize_session_status(value):
    """接受中文展示值或稳定机器码，返回机器码。"""
    return SESSION_STATUS_ALIASES.get(value, value)


def humanize_text(value):
    """翻译历史说明中常见的机器术语，不改写磁盘原文。"""
    replacements = (
        ("max_rounds", "最大轮次"),
        ("max_hours", "最长时数"),
        ("budget_reached", "运行预算已用完"),
        ("quota_exhausted", "查询额度已用完"),
        ("resource_exhausted", "会话资源已用完"),
        ("unusual traffic", "异常流量提示"),
        ("SERP", "搜索结果页"),
        ("GO", "可交付"),
    )
    text = str(value)
    for old, new in replacements:
        text = text.replace(old, new)
    return text
