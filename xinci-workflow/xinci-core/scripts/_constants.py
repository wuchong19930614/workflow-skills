#!/usr/bin/env python3
"""跨模块共享的常量,各留一份;原模块通过 import 继续暴露同名符号。

放在独立模块里是为了避免循环 import:registrar / run_controller / run_manifest /
validate_ledger 之间互相依赖,常量若留在其中任何一个里都可能形成环。
"""
import re

RUN_ID_RE = re.compile(r"^run-\d{8}T\d{6}Z-[a-f0-9]{8}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 设计终态词汇为前五个;disqualified/no_site 是决策终局,除 superseded 外无出边,并入终态集
TERMINAL = {"rejected", "expired", "superseded", "withdrawn", "built", "disqualified", "no_site"}
GO_STATES = {"build_ready", "pilot_ready", "fast_grab_ready"}

# 形成期以周计(生命周期契约):-track 观察最早与最新须相隔 ≥7 个自然日,单次连续运行凑不出形成确认。
# 按自然日而不按满 24 小时算的理由与唯一实现见 _common.span_days;两处判据曾各写一遍并互相矛盾。
MIN_TRACK_SPAN_DAYS = 7

MONETIZATION_LINES = {"subscription", "lead_generation", "affiliate", "transaction",
                      "paid_report", "advertising"}

ROUND_TYPES = {"discovery", "progression", "tracking", "calibration"}
REVIEW_OUTCOMES = {"reviewed_no_transition", "same_day_skipped", "not_due",
                   "awaiting_external_evidence", "deferred_existing_evidence"}
CALIBRATION_TARGETS = {"G6": 10, "G7": 10, "G5": 5, "G1": 5, "G3": 5}
