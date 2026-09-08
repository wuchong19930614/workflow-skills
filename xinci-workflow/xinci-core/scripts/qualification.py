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


def submission_proposal(obs, evidence_ref, by="xinci-qualify", run_id=None):
    """只生成参数，不执行、不推断授权、复核日期或业务理由。"""
    ref = Path(evidence_ref)
    require(not ref.is_absolute() and ".." not in ref.parts
            and len(ref.parts) == 3 and ref.parts[:2] == ("证据", obs["slug"])
            and ref.name.endswith("-qualify.json"), "提交证据须为该候选的数据区相对观察路径")
    require(by in {"xinci-qualify", "xinci-run"}, "认定执行者必须是 xinci-qualify 或 xinci-run")
    require(bool(run_id) == (by == "xinci-run"), "连续模式必须带 run_id，单步模式不得带 run_id")
    result = assess(obs)
    command = "defer-qualify" if result["outcome"] == "defer" else "transition"
    argv = [command, "--slug", obs["slug"], "--by", by, "--evidence", evidence_ref]
    if run_id:
        argv += ["--run-id", run_id]
    missing = []
    if command == "defer-qualify":
        for gap in obs["assessment"]["evidence_gaps"]:
            if gap["decisive"] and not gap["resolved"]:
                argv += ["--pending-evidence", gap["item"]]
        missing = ["--reason", "--pending-until"]
    else:
        argv += ["--to", result["outcome"]]
        gates = obs.get("gates") or {}
        if gates:
            argv += ["--gates", ",".join(f"{k}={v}" for k, v in sorted(gates.items()))]
        if result["score"] is not None:
            argv += ["--score", str(result["score"]), "--income-score", str(result["income_score"]),
                     "--g6-passed-lines", ",".join(result["g6_passed_lines"])]
        if result["outcome"] == "disqualified":
            missing = ["--reason"]
    return {"result": result, "registrar_argv": argv, "missing_arguments": missing,
            "executed": False,
            "boundary": "仅提案；提交前核对当前状态与授权。hold 暂缓不调用 defer-qualify。"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    parser.add_argument("--evidence-ref", help="生成提交提案；数据区相对观察路径")
    parser.add_argument("--by", choices=["xinci-qualify", "xinci-run"], default="xinci-qualify")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        # 使用完整观察校验，避免 CLI 与实际提交接受不同的文件。
        import registrar
        registrar._check_observation(args.observation, args.observation.name, None)
        obs = json.loads(args.observation.read_text(encoding="utf-8"))
        require(args.evidence_ref or (args.by == "xinci-qualify" and not args.run_id),
                "执行者参数需与 --evidence-ref 一起使用")
        if args.evidence_ref:
            require(Path(args.evidence_ref).name == args.observation.name,
                    "提交引用与输入观察文件名必须一致")
        result = (submission_proposal(obs, args.evidence_ref, args.by, args.run_id)
                  if args.evidence_ref else assess(obs))
    except (OSError, ValueError, registrar.RegistrarError) as exc:
        print(f"认定校验拒绝: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
