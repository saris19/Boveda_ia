"""Automatic document classification: TF-IDF + Multinomial Naive Bayes (scikit-learn)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from app.ai.training_data import TRAINING_SAMPLES

UNCLASSIFIED_LABEL = "Sin clasificar"
MIN_CONFIDENCE = 0.25  # ~1.75x the uniform probability (1/7); below this the document is marked as unclassified

SPANISH_STOPWORDS = {
    "a", "al", "algo", "ante", "antes", "como", "con", "contra", "cual", "cuando", "de", "del", "desde",
    "donde", "durante", "e", "el", "ella", "ellas", "ellos", "en", "entre", "era", "es", "esa", "ese",
    "esta", "este", "esto", "fue", "ha", "hay", "la", "las", "le", "les", "lo", "los", "mas", "me", "mi",
    "muy", "nos", "o", "para", "pero", "por", "que", "se", "segun", "ser", "si", "sin", "sobre", "su",
    "sus", "tambien", "te", "tiene", "todo", "tu", "un", "una", "uno", "unos", "y", "ya",
}


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\d+", " ", text)          # numbers carry no topic information
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    scores: dict[str, float]


class DocumentClassifier:
    def __init__(self) -> None:
        self.pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(
                        preprocessor=normalize_text,
                        stop_words=list(SPANISH_STOPWORDS),
                        ngram_range=(1, 2),
                        sublinear_tf=True,
                    ),
                ),
                ("model", MultinomialNB(alpha=0.3)),
            ]
        )
        self._train()

    def _train(self) -> None:
        texts, labels = [], []
        for label, samples in TRAINING_SAMPLES.items():
            texts.extend(samples)
            labels.extend([label] * len(samples))
        self.pipeline.fit(texts, labels)

    def classify(self, text: str) -> ClassificationResult:
        if not text or len(text.strip()) < 20:
            return ClassificationResult(UNCLASSIFIED_LABEL, 0.0, {})

        probabilities = self.pipeline.predict_proba([text])[0]
        labels = self.pipeline.classes_
        scores = {str(label): round(float(p), 3) for label, p in sorted(zip(labels, probabilities), key=lambda x: -x[1])}
        best_label, best_score = next(iter(scores.items()))
        if best_score < MIN_CONFIDENCE:
            return ClassificationResult(UNCLASSIFIED_LABEL, best_score, scores)
        return ClassificationResult(best_label, best_score, scores)

    def top_keywords(self, text: str, limit: int = 8) -> list[str]:
        """Most relevant terms of the document according to TF-IDF (used later for smart search)."""
        if not text.strip():
            return []
        local_vectorizer = TfidfVectorizer(
            preprocessor=normalize_text, stop_words=sorted(SPANISH_STOPWORDS), use_idf=False, sublinear_tf=True
        )
        try:
            matrix = local_vectorizer.fit_transform([text])
        except ValueError:  # empty vocabulary (only stopwords)
            return []
        terms = local_vectorizer.get_feature_names_out()
        weights = matrix.toarray()[0]
        ranked = sorted(zip(terms, weights), key=lambda x: -x[1])
        # Keywords are stored in clear text, so only domain terms known by the model are kept:
        # this prevents personal names or other free text from leaking out of the encrypted file.
        domain_vocabulary = self.pipeline.named_steps["tfidf"].vocabulary_
        return [term for term, _ in ranked if len(term) > 3 and term in domain_vocabulary][:limit]


_classifier: DocumentClassifier | None = None


def get_classifier() -> DocumentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = DocumentClassifier()
    return _classifier
