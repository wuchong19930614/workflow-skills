#!/usr/bin/env python3
"""认定提议的公共校验与计分；只读，registrar 与 CLI 共用。"""
import argparse
import json
import sys
from pathlib import Path

from _common import is_http_url
from _constants import MONETIZATION_LINES

WEIGHTS = {"trigger": 15, "task": 12, "language": 8,
           "competition": 30, "alignment": 15, "income": 20}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def assess(obs):
    """返回建议出口与派生字段，不把证据不足转为低分。"""
    a = obs.get("assessment")
    require(obs.get("stage") == "qualify", "assessment 只适用于 qualify")
    require(isinstance(a, dict) and set(a) == {"evidence_gaps", "scores", "risks", "seo"},
            "assessment 必须包含 evidence_gaps/scores/risks/seo")
    gaps = a["evidence_gaps"]
    require(isinstance(gaps, list), "evidence_gaps 必须是数组")
    for gap in gaps:
        require(isinstance(gap, dict) and set(gap) == {"item", "kind", "decisive", "resolved", "reason"},
                "证据缺口字段不完整")
        require(isinstance(gap["kind"], str) and gap["kind"] in {"structural", "access", "coverage", "unverified"}
                and type(gap["decisive"]) is bool and type(gap["resolved"]) is bool
                and nonempty(gap["item"]) and nonempty(gap["reason"]), "证据缺口取值非法")
    risks = a["risks"]
    require(isinstance(risks, list), "risks 必须是数组")
    seen, deductions = set(), {**dict.fromkeys(WEIGHTS, 0), "red_team": 0}
    for risk in risks:
        require(isinstance(risk, dict) and set(risk) == {"id", "charged_to", "deduction", "reason"},
                "risk 字段不完整")
        require(nonempty(risk["id"]) and nonempty(risk["reason"]), "风险必须有 id 与理由")
        key = risk["id"].strip().casefold()
        require(key not in seen, "同一风险 id 不得重复扣分")
        seen.add(key)
        target = risk["charged_to"]
        require(isinstance(target, str) and target in deductions and integer(risk["deduction"], 0, 100), "风险扣分非法")
        deductions[target] += risk["deduction"]
    gates = obs.get("gates") or {}
    veto = any(str(v).startswith("veto") for v in gates.values())
    blocked = any(g["decisive"] and not g["resolved"] for g in gaps)
    if veto or blocked:
        require(a["scores"] is None and not risks and a["seo"] is None
                and obs.get("income_score") is None, "硬否决或决定性缺口不得产生分数或扣分")
        return {"outcome": "disqualified" if veto else "defer",
                "score": None, "income_score": None, "g6_passed_lines": []}
    scores = a["scores"]
    require(isinstance(scores, dict) and set(scores) == set(WEIGHTS), "必须填写六维分数")
    for key, weight in WEIGHTS.items():
        require(integer(scores[key], 0, weight), f"{key} 分数超出 0–{weight}")
        require(deductions[key] <= weight - scores[key], f"{key} 已记录扣分未体现在维度分中")
    require(all(gates.get(g) == "pass" for g in ("G6", "G7", "G8")), "评分前 G6/G7/G8 必须通过")
    lines = obs.get("g6_lines") or {}
    require(set(lines) == MONETIZATION_LINES
            and all(isinstance(v, str) and v in {"pass", "veto", "N/A", "inconclusive"} for v in lines.values()),
            "正式认定必须记录完整六线")
    passed = sorted(k for k, v in lines.items() if v == "pass")
    require(bool(passed), "评分前至少一条盈利线已通过")
    seo = a["seo"]
    require(isinstance(seo, dict) and set(seo) == {"query", "gap", "source_urls"}
            and nonempty(seo["query"]) and nonempty(seo["gap"]), "缺 SEO 查询与任务缺口证据")
    urls = seo["source_urls"]
    require(isinstance(urls, list) and bool(urls)
            and all(is_http_url(u) and u in obs.get("source_urls", []) for u in urls),
            "SEO 来源必须来自本次观察的 source_urls")
    require(obs.get("income_score") == scores["income"] and scores["income"] >= 1,
            "income_score 必须与 income 维度一致且至少 1")
    total = max(0, sum(scores.values()) - deductions["red_team"])
    return {"outcome": "qualified" if total >= 80 else "disqualified", "score": total,
            "income_score": scores["income"], "g6_passed_lines": passed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    args = parser.parse_args(argv)
    try:
        # 使用完整观察校验，避免 CLI 与实际提交接受不同的文件。
        import registrar
        registrar._check_observation(args.observation, args.observation.name, None)
        result = assess(json.loads(args.observation.read_text(encoding="utf-8")))
    except (OSError, ValueError, registrar.RegistrarError) as exc:
        print(f"认定校验拒绝: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
