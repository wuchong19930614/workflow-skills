"""xinci 精确措辞的共享归一化规则。

screen_index 与 registrar 必须共用同一实现，避免去重报告“新”但注册器又拒收。
有语义的编程符号 +/# 保留；仅移除排版标点并压缩空白。
"""
import re

_PUNCT = re.compile(r"[(){}\[\]（）【】,，.。:：;；/／\\\-—–_'\"“”‘’!！?？]+")


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (term or "").lower())).strip()


OVERLAP_THRESHOLD = 0.8


def _informative(tokens) -> bool:
    return any(len(x) >= 3 and not x.isdigit() for x in tokens)


def similar(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if (len(na) >= 4 and na in nb) or (len(nb) >= 4 and nb in na):
        return True
    sa, sb = set(na.split()), set(nb.split())
    if min(len(sa), len(sb)) < 2:
        return False
    inter = sa & sb
    return bool(inter and _informative(inter)
                and len(inter) / min(len(sa), len(sb)) >= OVERLAP_THRESHOLD)


def match_kind(a: str, b: str):
    if normalize(a) == normalize(b) and normalize(a):
        return "exact"
    return "probable" if similar(a, b) else None
