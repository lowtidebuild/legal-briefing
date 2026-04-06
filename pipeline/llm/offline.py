"""Lightweight offline LLM provider for sample-mode runs without API keys."""
from __future__ import annotations

import re

from pipeline.llm.base import LLMProvider


class OfflineLLMProvider(LLMProvider):
    """Regex-based heuristics for sample-mode runs."""

    def __init__(self):
        super().__init__(max_retries=0, request_timeout_seconds=0)

    def _call_api(self, prompt: str, system: str | None = None) -> str:
        raise RuntimeError("Offline fallback provider does not make remote calls")

    def generate_json(self, prompt: str, system: str | None = None) -> dict | list:
        if "selected_indices" in prompt:
            match = re.search(r"select the (\d+)", prompt, flags=re.IGNORECASE)
            top_n = int(match.group(1)) if match else 10
            article_count = len(re.findall(r"^\[\d+\]", prompt, flags=re.MULTILINE))
            return {"selected_indices": list(range(min(top_n, article_count)))}

        title_match = re.search(r"(?:Article title|제목):\s*(.+)", prompt)
        description_match = re.search(r"(?:Description|내용):\s*(.+)", prompt, flags=re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        description = description_match.group(1).strip() if description_match else ""
        text = f"{title} {description}".lower()

        if "summary_ko" in prompt:
            jurisdiction_ko = "글로벌"
            if "eu" in text or "europe" in text:
                jurisdiction_ko = "EU"
            elif "korea" in text or "south korean" in text:
                jurisdiction_ko = "한국"
            elif "ftc" in text or "u.s." in text or "us " in text:
                jurisdiction_ko = "미국"

            focus_ko = "게임 규제 동향"
            if "loot box" in text:
                focus_ko = "루트박스 규제"
            elif "age-rating" in text or "age rating" in text:
                focus_ko = "연령등급 규정"
            elif "privacy" in text or "coppa" in text or "data" in text:
                focus_ko = "개인정보 규제"

            return {
                "summary_ko": [
                    f"{jurisdiction_ko}에서 {focus_ko} 관련 움직임이 포착됐다.",
                    "게임사 실무에 미칠 영향과 후속 집행 가능성을 함께 볼 필요가 있다.",
                    "원문 확인 후 대응 우선순위를 정리하기 좋은 이슈다.",
                ]
            }

        jurisdiction = "Global"
        if "eu" in text or "europe" in text:
            jurisdiction = "EU"
        elif "korea" in text or "south korean" in text:
            jurisdiction = "KR"
        elif "ftc" in text or "u.s." in text or " us " in f" {text} ":
            jurisdiction = "US"

        category = "ETC"
        game_mechanic = None
        if "loot box" in text or "microtransaction" in text:
            category = "CONSUMER_MONETIZATION"
            game_mechanic = "loot_box"
        elif "age rating" in text or "age-rating" in text or "esrb" in text or "pegi" in text:
            category = "CONTENT_AGE"
            game_mechanic = "age_rating"
        elif "privacy" in text or "coppa" in text or "gdpr" in text or "data" in text:
            category = "PRIVACY_SECURITY"
            game_mechanic = "data_collection"

        event_type = "policy"
        regulatory_phase = "proposed"
        if any(keyword in text for keyword in ["settlement", "fine", "probe", "enforcement"]):
            event_type = "enforcement"
            regulatory_phase = "enforced"
        elif any(keyword in text for keyword in ["enacted", "law", "regulation", "rules", "guidance"]):
            event_type = "legislation"
            regulatory_phase = "enacted"

        actors = []
        if jurisdiction == "EU":
            actors.append("EU regulators")
        elif jurisdiction == "KR":
            actors.append("Korean regulators")
        elif jurisdiction == "US":
            actors.append("FTC")

        object_label = "game regulation"
        if game_mechanic == "loot_box":
            object_label = "loot box mechanics"
        elif game_mechanic == "age_rating":
            object_label = "mobile game age-rating guidance"
        elif game_mechanic == "data_collection":
            object_label = "children's privacy in gaming"

        action = "issued an update"
        if regulatory_phase == "enforced":
            action = "took enforcement action"
        elif regulatory_phase == "enacted":
            action = "advanced or published new rules"

        return {
            "category": category,
            "jurisdiction": jurisdiction,
            "event_type": event_type,
            "regulatory_phase": regulatory_phase,
            "actors": actors,
            "object": object_label,
            "action": action,
            "game_mechanic": game_mechanic,
            "time_hint": "",
        }
