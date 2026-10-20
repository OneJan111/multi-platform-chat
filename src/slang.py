"""Streaming slang overrides applied before machine translation."""
from __future__ import annotations

import re


_TARGETS = ("zh-CN", "zh-TW", "en", "ja", "ko")
_TERMS: dict[str, dict[str, str]] = {}


def _add(terms: tuple[str, ...], translations: tuple[str, str, str, str, str]) -> None:
    values = dict(zip(_TARGETS, translations))
    for term in terms:
        _TERMS[term] = values


_add(("醒目留言", "超級留言", "超级留言", "Super Chat", "スーパーチャット", "슈퍼챗"),
     ("醒目留言", "醒目留言", "Super Chat", "スーパーチャット", "슈퍼챗"))
_add(("舰长", "艦長"), ("舰长", "艦長", "Captain membership", "キャプテン", "캡틴"))
_add(("提督",), ("提督", "提督", "Admiral membership", "提督", "제독"))
_add(("总督", "總督"), ("总督", "總督", "Governor membership", "総督", "총독"))
_add(("上舰", "上艦"), ("上舰", "上艦", "become a Captain member", "キャプテンに加入", "캡틴 가입"))
_add(("舰长续费", "艦長續費"),
     ("舰长续费", "艦長續費", "renew a Captain membership", "キャプテンを更新", "캡틴 멤버십 갱신"))
_add(("舰长礼物", "艦長禮物"),
     ("舰长礼物", "艦長禮物", "Captain membership gift", "キャプテンギフト", "캡틴 선물"))
_add(("弹幕", "彈幕"), ("弹幕", "彈幕", "live chat", "弾幕コメント", "실시간 채팅"))
_add(("房管",), ("房管", "房管", "stream moderator", "配信モデレーター", "방송 관리자"))
_add(("粉丝牌", "粉絲牌"), ("粉丝牌", "粉絲牌", "fan badge", "ファンバッジ", "팬 배지"))
_add(("高能榜",), ("高能榜", "高能榜", "top supporter leaderboard", "サポーターランキング", "후원자 순위"))
_add(("一键三连", "一鍵三連"),
     ("一键三连", "一鍵三連", "like, coin, and favorite", "いいね・コイン・お気に入り", "좋아요·코인·즐겨찾기"))
_add(("打call", "打CALL"), ("打call", "打call", "cheer", "応援", "응원"))
_add(("开播", "開播"), ("开播", "開播", "go live", "配信開始", "방송 시작"))
_add(("下播",), ("下播", "下播", "end the stream", "配信終了", "방송 종료"))
_add(("抽奖", "抽獎"), ("抽奖", "抽獎", "giveaway", "プレゼント企画", "경품 이벤트"))
_add(("连击", "連擊"), ("连击", "連擊", "gift combo", "ギフトコンボ", "선물 콤보"))

_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(term) for term in sorted(_TERMS, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def protect(text: str, target: str) -> tuple[str, dict[str, str]]:
    """Replace known slang with stable tokens and return their target-language overrides."""
    replacements: dict[str, str] = {}
    prefix = "MPCGLOSSARYTOKEN"
    suffix = 0
    while prefix in text.upper():
        suffix += 1
        prefix = f"MPCGLOSSARY{suffix}TOKEN"

    def replace(match: re.Match) -> str:
        nonlocal suffix
        term = match.group(0)
        translations = _TERMS.get(term)
        if translations is None:
            translations = next(
                (value for key, value in _TERMS.items() if key.casefold() == term.casefold()), None
            )
        if translations is None or target not in translations:
            return term
        token = f"{prefix}{suffix}END"
        suffix += 1
        replacements[token] = translations[target]
        return token

    return _PATTERN.sub(replace, text), replacements


def restore(text: str, replacements: dict[str, str]) -> str:
    """Replace protected tokens with their glossary translations."""
    for token, translation in replacements.items():
        pattern = re.escape(token).replace(
            "GLOSSARY", r"(?:GLOSSARY|用語集)"
        )
        text = re.sub(pattern, lambda _: translation, text, flags=re.IGNORECASE)
    return text


def apply(text: str, target: str) -> str:
    """Apply glossary terms to text without invoking a translation provider."""
    protected, replacements = protect(text, target)
    return restore(protected, replacements)
