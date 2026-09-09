"""形成信号须匹配候选的用户与任务；主题建议不能独自出闸。"""
def validate(obs):
    rows = obs.get("formation_evidence", [])
    if obs.get("stage") != "track" or not isinstance(rows, list):
        raise ValueError("formation_evidence 只适用于 track 数组")
    for row in rows:
        if (not isinstance(row, dict)
                or set(row) != {"signal", "scope", "query", "source_url", "task_match"}
                or row.get("signal") not in obs.get("formation_signals", [])
                or row.get("scope") not in {"topic", "task", "product"}
                or row.get("source_url") not in obs.get("source_urls", [])
                or not all(isinstance(row.get(k), str) and row[k].strip()
                           for k in ("query", "task_match"))):
            raise ValueError("每项须有 signal/scope/query/source_url/task_match，且来源与信号对应本次观察")


def task_signal(obs):
    validate(obs)
    return (obs.get("naming_status") == "stabilized" and obs.get("gates", {}).get("G1") == "pass"
            and any(r["scope"] in {"task", "product"} for r in obs.get("formation_evidence", [])))
