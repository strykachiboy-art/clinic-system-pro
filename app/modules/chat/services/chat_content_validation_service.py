from __future__ import annotations

import re
from typing import Any

from app.extensions import db
from app.core.exceptions import ValidationError
from app.modules.settings.models.clinic_settings import ClinicSettings


MAX_CONTENT_LENGTH = 10_000


class ChatContentValidationService:
    DEFAULT_SETTINGS: dict[str, bool] = {
        "chat_content_moderation_enabled": True,
        "clinical_sensitive_content_allowed": True,
        "profanity_filter_enabled": False,
        "abusive_content_blocked": True,
        "spam_content_blocked": True,
        "external_links_allowed": True,
    }

    HARD_BLOCK_PATTERNS: tuple[
        tuple[str, re.Pattern[str]],
        ...
    ] = (
        (
            "sexual_solicitation",
            re.compile(
                r"""
                \b
                (?:
                    lets?\s+have\s+sex
                    |
                    wanna\s+have\s+sex
                    |
                    want\s+to\s+have\s+sex
                    |
                    looking\s+for\s+sex
                    |
                    looking\s+for\s+porn
                    |
                    send\s+(?:me\s+)?(?:your\s+)?nudes?
                    |
                    send\s+(?:me\s+)?(?:your\s+)?naked\s+
                    (?:photo|photos|picture|pictures|pic|pics)
                    |
                    send\s+(?:me\s+)?(?:your\s+)?dick\s+pic
                    |
                    send\s+(?:me\s+)?(?:your\s+)?sex\s+
                    (?:video|videos|tape|tapes)
                    |
                    show\s+(?:me\s+)?(?:your\s+)?nudes?
                    |
                    show\s+(?:me\s+)?(?:your\s+)?naked\s+
                    (?:photo|photos|picture|pictures)
                    |
                    show\s+(?:me\s+)?(?:your\s+)?(?:genitals|body)
                )
                \b
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
        (
            "pornographic_content",
            re.compile(
                r"""
                \b
                (?:
                    porn\s+video
                    |
                    porn\s+videos
                    |
                    porn\s+clip
                    |
                    porn\s+clips
                    |
                    porn\s+pictures?
                    |
                    porn\s+pics?
                    |
                    porn\s+site
                    |
                    pornographic\s+video
                    |
                    pornographic\s+image
                    |
                    sex\s+tape
                    |
                    sex\s+tapes
                    |
                    xxx\s+video
                    |
                    xxx\s+videos
                    |
                    xxx\s+image
                    |
                    xxx\s+images
                )
                \b
                """,
                re.IGNORECASE | re.VERBOSE,
            ),
        ),
    )

    PROFANITY_PATTERNS: tuple[
        re.Pattern[str],
        ...
    ] = (
        re.compile(
            r"\bfuck(?:ing|ed|er|ers)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bshit(?:ty)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\basshole\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bbitch(?:es)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bmotherfucker(?:s)?\b",
            re.IGNORECASE,
        ),
    )

    ABUSIVE_PATTERNS: tuple[
        re.Pattern[str],
        ...
    ] = (
        re.compile(
            r"\bi(?:'m| am)?\s+going\s+to\s+kill\s+you\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bi(?:'m| am)?\s+going\s+to\s+hurt\s+you\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bi(?:'ll| will)\s+kill\s+you\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bi(?:'ll| will)\s+hurt\s+you\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\byou\s+deserve\s+to\s+die\b",
            re.IGNORECASE,
        ),
    )

    SENSITIVE_CLINICAL_TERMS: tuple[
        str,
        ...
    ] = (
        "sex",
        "sexual",
        "intercourse",
        "genital",
        "genitals",
        "vagina",
        "vaginal",
        "vulva",
        "penis",
        "penile",
        "testicle",
        "testicular",
        "semen",
        "ejaculation",
        "erection",
        "breast",
        "nipple",
        "cervical",
        "cervix",
        "uterus",
        "ovary",
        "ovarian",
        "pregnancy",
        "pregnant",
        "gestation",
        "miscarriage",
        "abortion",
        "contraception",
        "menstruation",
        "menstrual",
        "fertility",
        "infertility",
        "sexual-assault",
        "sexual assault",
    )

    CLINICAL_CONTEXT_TERMS: tuple[
        str,
        ...
    ] = (
        "patient",
        "clinical",
        "medical",
        "diagnosis",
        "diagnosed",
        "history",
        "examination",
        "exam",
        "procedure",
        "treatment",
        "symptom",
        "symptoms",
        "surgery",
        "surgical",
        "biopsy",
        "lesion",
        "bleeding",
        "infection",
        "disease",
        "medication",
        "medicine",
        "dose",
        "therapy",
        "screening",
        "follow-up",
        "follow up",
        "forensic",
        "consent",
        "assault",
        "injury",
        "injuries",
        "laboratory",
        "lab",
        "test",
        "results",
        "diagnostic",
        "consultation",
        "pregnancy",
        "pregnant",
        "obstetric",
        "gynecology",
        "gynaecology",
        "urology",
    )

    URL_PATTERN = re.compile(
        r"\bhttps?://[^\s<>()]+",
        re.IGNORECASE,
    )

    WORD_PATTERN = re.compile(
        r"\b[\w'-]+\b",
        re.UNICODE,
    )

    REPEATED_WORD_PATTERN = re.compile(
        r"\b([A-Za-z0-9'-]+)(?:\s+\1){4,}\b",
        re.IGNORECASE,
    )

    REPEATED_CHARACTER_PATTERN = re.compile(
        r"(.)\1{9,}",
        re.DOTALL,
    )

    @classmethod
    def _validate_clinic_id(
        cls,
        clinic_id: int,
    ) -> int:
        if (
            isinstance(clinic_id, bool)
            or not isinstance(clinic_id, int)
            or clinic_id <= 0
        ):
            raise ValidationError(
                "Clinic ID must be a positive integer"
            )

        return clinic_id

    @classmethod
    def _get_settings(
        cls,
        clinic_id: int,
    ) -> ClinicSettings | None:
        clinic_id = cls._validate_clinic_id(
            clinic_id,
        )

        statement = db.select(
            ClinicSettings
        ).where(
            ClinicSettings.clinic_id == clinic_id,
        )

        return db.session.execute(
            statement,
        ).scalar_one_or_none()

    @classmethod
    def _get_chat_security_preferences(
        cls,
        clinic_id: int,
    ) -> dict[str, Any]:
        settings = cls._get_settings(
            clinic_id,
        )

        if settings is None:
            return {}

        preferences = settings.security_preferences

        if not isinstance(
            preferences,
            dict,
        ):
            raise ValidationError(
                "Clinic security preferences must be "
                "a JSON object"
            )

        chat_preferences = preferences.get(
            "chat",
            {},
        )

        if not isinstance(
            chat_preferences,
            dict,
        ):
            raise ValidationError(
                "Chat security preferences must be "
                "a JSON object"
            )

        return chat_preferences

    @classmethod
    def _get_feature_flags(
        cls,
        clinic_id: int,
    ) -> dict[str, Any]:
        settings = cls._get_settings(
            clinic_id,
        )

        if settings is None:
            return {}

        feature_flags = settings.feature_flags

        if not isinstance(
            feature_flags,
            dict,
        ):
            raise ValidationError(
                "Clinic feature flags must be "
                "a JSON object"
            )

        return feature_flags

    @classmethod
    def _get_boolean_setting(
        cls,
        clinic_id: int,
        key: str,
    ) -> bool:
        preferences = cls._get_chat_security_preferences(
            clinic_id,
        )

        if key not in preferences:
            return cls.DEFAULT_SETTINGS[key]

        value = preferences[key]

        if not isinstance(
            value,
            bool,
        ):
            raise ValidationError(
                f"Chat setting '{key}' must be boolean"
            )

        return value

    @classmethod
    def _is_moderation_enabled(
        cls,
        clinic_id: int,
    ) -> bool:
        feature_flags = cls._get_feature_flags(
            clinic_id,
        )

        key = "chat_content_moderation_enabled"

        if key not in feature_flags:
            return cls.DEFAULT_SETTINGS[key]

        value = feature_flags[key]

        if not isinstance(
            value,
            bool,
        ):
            raise ValidationError(
                f"Feature flag '{key}' must be boolean"
            )

        return value

    @classmethod
    def normalize_text(
        cls,
        content: str,
    ) -> str:
        if not isinstance(
            content,
            str,
        ):
            raise ValidationError(
                "Chat content must be a string"
            )

        content = content.strip()

        if not content:
            raise ValidationError(
                "Chat content cannot be empty"
            )

        if len(content) > MAX_CONTENT_LENGTH:
            raise ValidationError(
                f"Chat content cannot exceed "
                f"{MAX_CONTENT_LENGTH} characters"
            )

        return content

    @classmethod
    def _contains_pattern(
        cls,
        content: str,
        pattern: re.Pattern[str],
    ) -> bool:
        return pattern.search(
            content,
        ) is not None

    @classmethod
    def _is_clinical_sensitive_content(
        cls,
        content: str,
    ) -> bool:
        normalized = content.lower()

        has_sensitive_term = any(
            term in normalized
            for term in cls.SENSITIVE_CLINICAL_TERMS
        )

        if not has_sensitive_term:
            return False

        return any(
            term in normalized
            for term in cls.CLINICAL_CONTEXT_TERMS
        )

    @classmethod
    def _matches_hard_block(
        cls,
        content: str,
    ) -> tuple[str, str] | None:
        for category, pattern in cls.HARD_BLOCK_PATTERNS:
            if cls._contains_pattern(
                content,
                pattern,
            ):
                return (
                    category,
                    "Sexually explicit content is not allowed in clinical chat",
                )

        return None

    @classmethod
    def _matches_profanity(
        cls,
        content: str,
    ) -> bool:
        return any(
            cls._contains_pattern(
                content,
                pattern,
            )
            for pattern in cls.PROFANITY_PATTERNS
        )

    @classmethod
    def _matches_abuse(
        cls,
        content: str,
    ) -> bool:
        return any(
            cls._contains_pattern(
                content,
                pattern,
            )
            for pattern in cls.ABUSIVE_PATTERNS
        )

    @classmethod
    def _matches_spam(
        cls,
        content: str,
    ) -> bool:
        if cls.REPEATED_CHARACTER_PATTERN.search(
            content,
        ):
            return True

        if cls.REPEATED_WORD_PATTERN.search(
            content,
        ):
            return True

        words = cls.WORD_PATTERN.findall(
            content,
        )

        if not words:
            return False

        normalized_words = [
            word.lower()
            for word in words
        ]

        longest_run = 1
        current_run = 1

        for index in range(
            1,
            len(normalized_words),
        ):
            if (
                normalized_words[index]
                == normalized_words[index - 1]
            ):
                current_run += 1
                longest_run = max(
                    longest_run,
                    current_run,
                )
            else:
                current_run = 1

        return longest_run >= 5

    @classmethod
    def _contains_external_link(
        cls,
        content: str,
    ) -> bool:
        return cls.URL_PATTERN.search(
            content,
        ) is not None

    @classmethod
    def validate_text(
        cls,
        clinic_id: int,
        content: str,
    ) -> dict[str, Any]:
        clinic_id = cls._validate_clinic_id(
            clinic_id,
        )

        normalized = cls.normalize_text(
            content,
        )

        hard_block = cls._matches_hard_block(
            normalized,
        )

        clinical_sensitive = (
            cls._is_clinical_sensitive_content(
                normalized,
            )
        )

        if hard_block is not None:
            category, reason = hard_block

            if not clinical_sensitive:
                return {
                    "allowed": False,
                    "category": category,
                    "reason": reason,
                    "normalized_content": normalized,
                }

        moderation_enabled = (
            cls._is_moderation_enabled(
                clinic_id,
            )
        )

        if not moderation_enabled:
            return {
                "allowed": True,
                "category": None,
                "reason": None,
                "normalized_content": normalized,
            }

        if clinical_sensitive:
            clinical_allowed = (
                cls._get_boolean_setting(
                    clinic_id,
                    "clinical_sensitive_content_allowed",
                )
            )

            if not clinical_allowed:
                return {
                    "allowed": False,
                    "category": "clinical_sensitive",
                    "reason": (
                        "Sensitive clinical content "
                        "is disabled by clinic policy"
                    ),
                    "normalized_content": normalized,
                }

        if (
            cls._get_boolean_setting(
                clinic_id,
                "profanity_filter_enabled",
            )
            and cls._matches_profanity(
                normalized,
            )
        ):
            return {
                "allowed": False,
                "category": "profanity",
                "reason": (
                    "Profanity is not allowed "
                    "under the current clinic chat policy"
                ),
                "normalized_content": normalized,
            }

        if (
            cls._get_boolean_setting(
                clinic_id,
                "abusive_content_blocked",
            )
            and cls._matches_abuse(
                normalized,
            )
        ):
            return {
                "allowed": False,
                "category": "abusive",
                "reason": (
                    "Abusive or threatening content "
                    "is not allowed"
                ),
                "normalized_content": normalized,
            }

        if (
            cls._get_boolean_setting(
                clinic_id,
                "spam_content_blocked",
            )
            and cls._matches_spam(
                normalized,
            )
        ):
            return {
                "allowed": False,
                "category": "spam",
                "reason": (
                    "Spam-like content is not allowed"
                ),
                "normalized_content": normalized,
            }

        if (
            not cls._get_boolean_setting(
                clinic_id,
                "external_links_allowed",
            )
            and cls._contains_external_link(
                normalized,
            )
        ):
            return {
                "allowed": False,
                "category": "external_link",
                "reason": (
                    "External links are disabled "
                    "by clinic chat policy"
                ),
                "normalized_content": normalized,
            }

        return {
            "allowed": True,
            "category": (
                "clinical_sensitive"
                if clinical_sensitive
                else None
            ),
            "reason": (
                "Clinical sensitive content allowed"
                if clinical_sensitive
                else None
            ),
            "normalized_content": normalized,
        }

    @classmethod
    def ensure_text_allowed(
        cls,
        clinic_id: int,
        content: str,
    ) -> str:
        result = cls.validate_text(
            clinic_id,
            content,
        )

        if not result["allowed"]:
            raise ValidationError(
                result["reason"]
                or "Chat content is not allowed"
            )

        return result["normalized_content"]

    @classmethod
    def is_text_allowed(
        cls,
        clinic_id: int,
        content: str,
    ) -> bool:
        result = cls.validate_text(
            clinic_id,
            content,
        )

        return bool(
            result["allowed"]
        )