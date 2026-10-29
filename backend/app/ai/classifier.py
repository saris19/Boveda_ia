"""Automatic document classification: word + character TF-IDF with logistic regression (scikit-learn)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

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


@dataclass
class ModelInfo:
    trained_at: datetime
    seed_samples: int
    feedback_samples: int
    categories: list[str]
    cv_accuracy: float            # 5-fold cross-validated accuracy on seed + feedback
    per_category: dict[str, int] = field(default_factory=dict)


FEEDBACK_WEIGHT = 2  # a human correction counts as two training examples


def _build_pipeline() -> Pipeline:
    """Word TF-IDF (1-2 grams) + character TF-IDF (3-5 grams) -> logistic regression.

    Character n-grams make the model robust to plurals, conjugations and typos; word n-grams keep it
    interpretable (keywords, query intent). Chosen by 5-fold cross-validation over the seed corpus
    (v0.5 word-only Naive Bayes: 0.64; this model: 0.71) and because its probabilities are better
    calibrated than Naive Bayes, which reported 100 % confidence on almost everything.
    """
    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "words",
                            TfidfVectorizer(
                                preprocessor=normalize_text,
                                stop_words=list(SPANISH_STOPWORDS),
                                ngram_range=(1, 2),
                                sublinear_tf=True,
                            ),
                        ),
                        (
                            "chars",
                            TfidfVectorizer(
                                preprocessor=normalize_text, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True
                            ),
                        ),
                    ]
                ),
            ),
            ("model", LogisticRegression(C=3, max_iter=3000)),
        ]
    )


class DocumentClassifier:
    def __init__(self, feedback: list[tuple[str, str]] | None = None) -> None:
        """feedback: list of (training_text, corrected_category) coming from human corrections."""
        self.pipeline = _build_pipeline()
        self.info: ModelInfo | None = None
        self._train(feedback or [])

    def _train(self, feedback: list[tuple[str, str]]) -> None:
        texts, labels = [], []
        for label, samples in TRAINING_SAMPLES.items():
            texts.extend(samples)
            labels.extend([label] * len(samples))
        seed_count = len(texts)
        usable = [(t, c) for t, c in feedback if t.strip() and c != UNCLASSIFIED_LABEL]
        for text, category in usable:
            texts.extend([text] * FEEDBACK_WEIGHT)
            labels.extend([category] * FEEDBACK_WEIGHT)
        self.pipeline.fit(texts, labels)

        # Quality estimate: stratified 5-fold cross-validation on a fresh pipeline
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        try:
            accuracy = float(cross_val_score(_build_pipeline(), texts, labels, cv=folds).mean())
        except ValueError:  # a category with fewer than 5 samples
            accuracy = 0.0
        per_category: dict[str, int] = {}
        for label in labels:
            per_category[label] = per_category.get(label, 0) + 1
        self.info = ModelInfo(
            trained_at=datetime.now(timezone.utc),
            seed_samples=seed_count,
            feedback_samples=len(usable),
            categories=sorted(set(labels)),
            cv_accuracy=round(accuracy, 3),
            per_category=per_category,
        )

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

    @property
    def word_vectorizer(self) -> TfidfVectorizer:
        return dict(self.pipeline.named_steps["features"].transformer_list)["words"]

    def query_intent(self, query: str) -> dict[str, float]:
        """Category probabilities for a short search query ({} when no word is known by the model).

        Lets the search understand that 'pago a proveedores' is about finance even if no document
        contains those exact words.
        """
        if not query.strip() or self.word_vectorizer.transform([query]).nnz == 0:
            return {}
        probabilities = self.pipeline.predict_proba([query])[0]
        return {
            str(label): round(float(p), 3)
            for label, p in sorted(zip(self.pipeline.classes_, probabilities), key=lambda x: -x[1])
        }

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
        domain_vocabulary = self.word_vectorizer.vocabulary_
        return [term for term, _ in ranked if len(term) > 3 and term in domain_vocabulary][:limit]


_classifier: DocumentClassifier | None = None


def get_classifier() -> DocumentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = DocumentClassifier()
    return _classifier


def retrain_classifier(feedback: list[tuple[str, str]]) -> ModelInfo:
    """Train a new model with the seed corpus plus human corrections and swap it in atomically."""
    global _classifier
    model = DocumentClassifier(feedback)
    _classifier = model
    return model.info


CAPITALIZED_WORD = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b")
WORD = re.compile(r"[a-zñ]{3,}")


def privacy_safe_training_text(text: str, max_words: int = 400) -> str:
    """Words usable to retrain the model without keeping personal data.

    Removes numbers, stopwords and every word that appears capitalized somewhere in the document
    (names, surnames, companies) unless it also appears in lowercase as a common word.
    """
    capitalized = {normalize_text(w) for w in CAPITALIZED_WORD.findall(text)}
    lowercase_words = set(WORD.findall(normalize_text(" ".join(re.findall(r"\b[a-záéíóúñ]+\b", text)))))
    blocked = capitalized - lowercase_words
    words = [w for w in WORD.findall(normalize_text(text)) if w not in SPANISH_STOPWORDS and w not in blocked]
    return " ".join(words[:max_words])
