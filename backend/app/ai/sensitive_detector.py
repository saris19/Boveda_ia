"""Detection of sensitive / personal data (oriented to Colombia, Ley 1581 de 2012).

Hybrid approach: regular expressions + validation (e.g. Luhn for cards, NIT check digit) +
context keywords to reduce false positives. Detected values are always MASKED before being
stored, so the database never contains the sensitive data in clear text.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.models import SensitivityLevel


def luhn_is_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def nit_is_valid(value: str) -> bool:
    """Validates the DIAN check digit of a Colombian NIT (e.g. 900.123.456-7)."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 9:
        return False
    body, check_digit = digits[:-1], int(digits[-1])
    weights = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    total = sum(int(d) * w for d, w in zip(reversed(body), weights))
    remainder = total % 11
    expected = remainder if remainder in (0, 1) else 11 - remainder
    return expected == check_digit


def mask_value(value: str) -> str:
    clean = value.strip()
    if "@" in clean:
        user, _, domain = clean.partition("@")
        return f"{user[:1]}***@{domain}"
    visible = 4 if len(clean) > 8 else 2
    return "*" * max(len(clean) - visible, 3) + clean[-visible:]


@dataclass
class SensitivePattern:
    key: str
    label: str
    regex: re.Pattern
    weight: int                                   # contribution to the risk score
    validator: Callable[[str], bool] | None = None
    context_words: tuple[str, ...] = ()           # if set, one must appear near the match
    value_group: int = 0
    is_special_category: bool = False             # "datos sensibles" per Ley 1581 art. 5


PATTERNS: list[SensitivePattern] = [
    SensitivePattern(
        "credit_card", "Tarjeta de crédito/débito",
        re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), weight=40, validator=luhn_is_valid,
    ),
    SensitivePattern(
        "national_id", "Cédula de ciudadanía",
        re.compile(r"\b(\d{1,3}(?:\.\d{3}){1,3}|\d{6,10})\b"), weight=25,
        context_words=("cédula", "cedula", "c.c", "cc.", "cc:", " cc ", "documento de identidad", "identificado con"),
        value_group=1,
    ),
    SensitivePattern(
        "nit", "NIT",
        re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-\d\b"), weight=10, validator=nit_is_valid,
    ),
    SensitivePattern(
        "bank_account", "Cuenta bancaria",
        re.compile(r"\b(\d{3}-?\d{6}-?\d{2}|\d{8,20})\b"), weight=30,
        context_words=("cuenta", "ahorros", "corriente", "bancolombia", "davivienda", "banco"),
        value_group=1,
    ),
    SensitivePattern(
        "email", "Correo electrónico",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), weight=5,
    ),
    SensitivePattern(
        "phone", "Teléfono",
        re.compile(r"(?:\+?57[ -]?)?\b(3\d{2}[ -]?\d{3}[ -]?\d{4}|60\d[ -]?\d{3}[ -]?\d{4})\b"), weight=8,
        value_group=1,
    ),
    SensitivePattern(
        "address", "Dirección",
        re.compile(
            r"\b(?:calle|cl|carrera|cra|kr|avenida|av|diagonal|dg|transversal|tv)\.?\s*\d+[a-z]?\s*(?:#|no\.?|n°)\s*\d+[a-z]?\s*-\s*\d+",
            re.IGNORECASE,
        ),
        weight=8,
    ),
    SensitivePattern(
        "password", "Contraseña o credencial",
        re.compile(r"\b(?:contraseña|password|passwd|pwd|clave|token|api[_ ]?key)\s*[:=]\s*(\S{4,})", re.IGNORECASE),
        weight=45, value_group=1,
    ),
    SensitivePattern(
        "birth_date", "Fecha de nacimiento",
        re.compile(r"\b(?:fecha de nacimiento|nacido el|f\.? nac\.?)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE),
        weight=10, value_group=1,
    ),
    SensitivePattern(
        "health_data", "Dato de salud",
        re.compile(
            r"\b(diagn[oó]stico|historia cl[ií]nica|enfermedad|tratamiento m[eé]dico|incapacidad m[eé]dica|"
            r"medicamento|hospitalizaci[oó]n|vih|c[aá]ncer|discapacidad|psiqui[aá]trico)\b",
            re.IGNORECASE,
        ),
        weight=30, is_special_category=True,
    ),
    SensitivePattern(
        "special_category", "Dato sensible (Ley 1581)",
        re.compile(
            r"\b(orientaci[oó]n sexual|afiliaci[oó]n pol[ií]tica|partido pol[ií]tico|religi[oó]n|"
            r"origen [eé]tnico|sindicato|huella dactilar|dato biom[eé]trico|antecedentes penales)\b",
            re.IGNORECASE,
        ),
        weight=30, is_special_category=True,
    ),
]

CONTEXT_WINDOW = 40  # characters before the match where a context word must appear
MAX_SAMPLES = 3


@dataclass
class DetectionResult:
    findings: dict = field(default_factory=dict)  # key -> {label, count, samples}
    risk_score: int = 0
    sensitivity: SensitivityLevel = SensitivityLevel.PUBLIC


def _has_context(text: str, start: int, words: tuple[str, ...]) -> bool:
    window = text[max(0, start - CONTEXT_WINDOW):start].lower()
    return any(word in window for word in words)


def detect_sensitive_data(text: str) -> DetectionResult:
    result = DetectionResult()
    if not text:
        return result

    card_spans: list[tuple[int, int]] = []
    score = 0
    has_special_category = False

    for pattern in PATTERNS:
        matches = []
        for match in pattern.regex.finditer(text):
            value = match.group(pattern.value_group) if pattern.value_group else match.group(0)
            start = match.start()
            if pattern.validator and not pattern.validator(value):
                continue
            if pattern.context_words and not _has_context(text, start, pattern.context_words):
                continue
            # Avoid counting the digits of a card as an ID or account as well
            if pattern.key != "credit_card" and any(s <= start < e for s, e in card_spans):
                continue
            if pattern.key == "credit_card":
                card_spans.append((match.start(), match.end()))
            matches.append(value)

        if not matches:
            continue
        unique_values = list(dict.fromkeys(matches))
        samples = (
            [m.lower() for m in unique_values[:MAX_SAMPLES]]   # health terms are not personal values
            if pattern.is_special_category
            else [mask_value(v) for v in unique_values[:MAX_SAMPLES]]
        )
        result.findings[pattern.key] = {"label": pattern.label, "count": len(matches), "samples": samples}
        # Diminishing returns: first hit counts fully, extra hits add a little
        score += pattern.weight + min(len(matches) - 1, 5) * 2
        has_special_category |= pattern.is_special_category

    result.risk_score = min(score, 100)
    result.sensitivity = _score_to_level(result.risk_score, has_special_category, result.findings)
    return result


def _score_to_level(score: int, has_special_category: bool, findings: dict) -> SensitivityLevel:
    if "credit_card" in findings or "password" in findings or score >= 60:
        return SensitivityLevel.RESTRICTED
    if has_special_category or score >= 30:
        return SensitivityLevel.CONFIDENTIAL
    if score > 0:
        return SensitivityLevel.INTERNAL
    return SensitivityLevel.PUBLIC
