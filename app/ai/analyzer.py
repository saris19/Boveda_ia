"""Single entry point that runs every AI module over a document's text."""
from __future__ import annotations

from app.ai.classifier import get_classifier
from app.ai.sensitive_detector import detect_sensitive_data
from app.schemas import AnalysisResult


def analyze_text(text: str) -> AnalysisResult:
    classifier = get_classifier()
    classification = classifier.classify(text)
    detection = detect_sensitive_data(text)
    return AnalysisResult(
        category=classification.category,
        category_confidence=round(classification.confidence, 3),
        category_scores=classification.scores,
        sensitivity=detection.sensitivity,
        risk_score=detection.risk_score,
        sensitive_findings=detection.findings,
        keywords=classifier.top_keywords(text),
    )
