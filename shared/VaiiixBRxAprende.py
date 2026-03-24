
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import logging

import numpy as np
import pandas as pd

from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("VAIIIxBRxAprende")

@dataclass
class LearningConfig:
    symbol: str = "ITUB4"
    storage_dir: str = "./vaiiixbrxaprende_data"
    memory_csv: str = "trade_memory.csv"
    stats_json: str = "learning_stats.json"
    retrain_min_samples: int = 80
    min_train_samples_per_class: int = 12
    test_size: float = 0.25
    random_state: int = 42
    reward_clip_min: float = -2.0
    reward_clip_max: float = 2.0
    approve_threshold: float = 0.62
    watchlist_threshold: float = 0.54
    reject_threshold: float = 0.45
    confidence_floor: float = 0.05
    confidence_ceiling: float = 0.98
    adaptive_learning_rate: float = 0.15
    min_weight_per_strategy: float = 0.10
    max_weight_per_strategy: float = 0.70

@dataclass
class TradeRecord:
    symbol: str
    timestamp_open: str
    timestamp_close: Optional[str]
    side: str
    regime: str
    vaiiixbr_signal: str
    vaiiixbr_confidence: float
    hybrid_signal: str
    hybrid_confidence: float
    final_signal: str
    final_confidence: float
    entry_price: float
    exit_price: Optional[float]
    stop_price: Optional[float]
    take_price: Optional[float]
    return_pct: Optional[float]
    pnl_abs: Optional[float]
    max_drawdown_pct: Optional[float]
    bars_held: Optional[int]
    rel_volume: Optional[float]
    rsi_14: Optional[float]
    atr_pct: Optional[float]
    dist_vwap_pct: Optional[float]
    body_pct: Optional[float]
    trend_spread: Optional[float]
    long_trend_spread: Optional[float]
    was_possible_entry: bool = False
    was_guaranteed_entry: bool = False
    stopped_out: bool = False
    take_hit: bool = False
    low_volume_entry: bool = False
    aligned_with_regime: bool = True
    result_binary: Optional[int] = None
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TrainingReport:
    trained: bool
    samples: int
    accuracy: Optional[float]
    auc: Optional[float]
    brier: Optional[float]
    positive_rate: Optional[float]
    notes: List[str] = field(default_factory=list)

@dataclass
class LearningDecision:
    approved_signal: str
    adjusted_confidence: float
    success_probability: Optional[float]
    decision_label: str
    suggested_weights: Dict[str, float]
    reasons: List[str]
    model_ready: bool

def ensure_symbol(symbol: str) -> None:
    if symbol != "ITUB4":
        raise ValueError("VAIIIxBRxAprende é fixado exclusivamente em ITUB4.")

def clamp(value: float, vmin: float, vmax: float) -> float:
    return max(vmin, min(vmax, value))

def safe_float(value: Any, default: float = np.nan) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default

class TradeMemory:
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self.base_dir = Path(self.config.storage_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.memory_path = self.base_dir / self.config.memory_csv
        self.stats_path = self.base_dir / self.config.stats_json

    def append(self, record: TradeRecord) -> None:
        ensure_symbol(record.symbol)
        row = asdict(record)
        row["meta"] = json.dumps(row.get("meta", {}), ensure_ascii=False)
        df_new = pd.DataFrame([row])
        if self.memory_path.exists():
            df_old = pd.read_csv(self.memory_path)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new
        df_all.to_csv(self.memory_path, index=False)

    def load(self) -> pd.DataFrame:
        if not self.memory_path.exists():
            return pd.DataFrame()
        df = pd.read_csv(self.memory_path)
        if "meta" in df.columns:
            df["meta"] = df["meta"].apply(lambda x: {} if pd.isna(x) else json.loads(x))
        return df

    def attach_reward_column(self, rewards: pd.Series) -> None:
        df = pd.read_csv(self.memory_path)
        df["reward"] = rewards.values
        df.to_csv(self.memory_path, index=False)

class RewardEngine:
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

    def compute_reward(self, row: pd.Series) -> float:
        ret = safe_float(row.get("return_pct"), 0.0)
        dd = abs(safe_float(row.get("max_drawdown_pct"), 0.0))
        bars = safe_float(row.get("bars_held"), 0.0)
        result = safe_float(row.get("result_binary"), 0.0)
        low_volume = 1.0 if bool(row.get("low_volume_entry", False)) else 0.0
        aligned = 1.0 if bool(row.get("aligned_with_regime", True)) else 0.0
        take_hit = 1.0 if bool(row.get("take_hit", False)) else 0.0
        stopped_out = 1.0 if bool(row.get("stopped_out", False)) else 0.0
        reward = 1.00 * ret - 0.70 * dd + 0.40 * result - 0.03 * bars - 0.50 * low_volume + 0.20 * aligned + 0.15 * take_hit - 0.25 * stopped_out
        return clamp(reward, self.config.reward_clip_min, self.config.reward_clip_max)

    def compute_rewards(self, df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=float)
        return df.apply(self.compute_reward, axis=1)

class FeatureBuilder:
    NUMERIC_COLUMNS = ["vaiiixbr_confidence","hybrid_confidence","final_confidence","entry_price","stop_price","take_price","rel_volume","rsi_14","atr_pct","dist_vwap_pct","body_pct","trend_spread","long_trend_spread","bars_held"]
    CATEGORICAL_COLUMNS = ["regime","side","vaiiixbr_signal","hybrid_signal","final_signal"]
    BOOLEAN_COLUMNS = ["was_possible_entry","was_guaranteed_entry","low_volume_entry","aligned_with_regime","stopped_out","take_hit"]

    @classmethod
    def build_model_frame(cls, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        out = pd.DataFrame(index=df.index)
        for col in cls.NUMERIC_COLUMNS:
            out[col] = pd.to_numeric(df.get(col), errors="coerce")
        for col in cls.CATEGORICAL_COLUMNS:
            out[col] = df.get(col, pd.Series(index=df.index, dtype=object)).astype(str)
        for col in cls.BOOLEAN_COLUMNS:
            out[col] = df.get(col, pd.Series(index=df.index, dtype=bool)).fillna(False).astype(int)
        return pd.get_dummies(out, columns=cls.CATEGORICAL_COLUMNS, dummy_na=False)

    @staticmethod
    def target(df: pd.DataFrame) -> pd.Series:
        return pd.to_numeric(df.get("result_binary"), errors="coerce")

class MetaLearner:
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self.feature_columns: List[str] = []
        self.model = None
        self.calibrator = None
        self.last_report: Optional[TrainingReport] = None

    def _prepare_xy(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        X = FeatureBuilder.build_model_frame(df)
        y = FeatureBuilder.target(df)
        mask = y.notna()
        return X.loc[mask].copy(), y.loc[mask].astype(int).copy()

    def _build_base_model(self):
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler(with_mean=False)), ("clf", LogisticRegression(random_state=self.config.random_state, max_iter=500, class_weight="balanced"))])

    def _build_secondary_model(self):
        return Pipeline([("imputer", SimpleImputer(strategy="median")), ("clf", RandomForestClassifier(n_estimators=250, max_depth=6, min_samples_leaf=4, random_state=self.config.random_state, class_weight="balanced_subsample"))])

    def train(self, memory_df: pd.DataFrame) -> TrainingReport:
        X, y = self._prepare_xy(memory_df)
        notes: List[str] = []
        if len(X) < self.config.retrain_min_samples:
            report = TrainingReport(False, len(X), None, None, None, None, [f"Amostras insuficientes: {len(X)}"])
            self.last_report = report
            return report
        class_counts = y.value_counts().to_dict()
        if min(class_counts.values()) < self.config.min_train_samples_per_class:
            report = TrainingReport(False, len(X), None, None, None, float(y.mean()), [f"Classes insuficientes: {class_counts}"])
            self.last_report = report
            return report
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=self.config.test_size, random_state=self.config.random_state, stratify=y)
        model_a = self._build_base_model()
        model_b = self._build_secondary_model()
        model_a.fit(X_train, y_train)
        model_b.fit(X_train, y_train)
        brier_a = brier_score_loss(y_test, model_a.predict_proba(X_test)[:, 1])
        brier_b = brier_score_loss(y_test, model_b.predict_proba(X_test)[:, 1])
        self.model = model_a if brier_a <= brier_b else model_b
        notes.append("Modelo selecionado: " + ("LogisticRegression" if self.model is model_a else "RandomForestClassifier"))
        self.calibrator = CalibratedClassifierCV(self.model, method="sigmoid", cv="prefit")
        self.calibrator.fit(X_train, y_train)
        test_proba = self.calibrator.predict_proba(X_test)[:, 1]
        preds = (test_proba >= 0.5).astype(int)
        report = TrainingReport(True, len(X), float(accuracy_score(y_test, preds)), float(roc_auc_score(y_test, test_proba)), float(brier_score_loss(y_test, test_proba)), float(y.mean()), notes)
        self.feature_columns = list(X.columns)
        self.last_report = report
        return report

    def is_ready(self) -> bool:
        return self.model is not None and self.calibrator is not None and len(self.feature_columns) > 0

    def _align_features(self, X: pd.DataFrame) -> pd.DataFrame:
        aligned = X.copy()
        for col in self.feature_columns:
            if col not in aligned.columns:
                aligned[col] = 0
        extra = [c for c in aligned.columns if c not in self.feature_columns]
        if extra:
            aligned = aligned.drop(columns=extra)
        return aligned[self.feature_columns]

    def predict_success_proba(self, snapshot: Dict[str, Any]) -> Optional[float]:
        if not self.is_ready():
            return None
        X = FeatureBuilder.build_model_frame(pd.DataFrame([snapshot]))
        X = self._align_features(X)
        return float(self.calibrator.predict_proba(X)[:, 1][0])

class ConfidenceCalibrator:
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

    def calibrate(self, base_confidence: float, success_probability: Optional[float], regime: str) -> float:
        conf = float(base_confidence)
        if success_probability is not None:
            conf = 0.60 * conf + 0.40 * success_probability
        if regime == "low_volume":
            conf -= 0.08
        elif regime == "breakout":
            conf += 0.03
        elif regime == "trend":
            conf += 0.02
        elif regime == "reversal":
            conf -= 0.01
        return clamp(conf, self.config.confidence_floor, self.config.confidence_ceiling)

class AdaptiveWeightUpdater:
    DEFAULT_WEIGHTS = {
        "trend": {"holly_like": 0.30, "quant_like": 0.45, "ea_like": 0.25},
        "breakout": {"holly_like": 0.38, "quant_like": 0.32, "ea_like": 0.30},
        "reversal": {"holly_like": 0.26, "quant_like": 0.29, "ea_like": 0.45},
        "low_volume": {"holly_like": 0.20, "quant_like": 0.55, "ea_like": 0.25},
        "neutral": {"holly_like": 0.33, "quant_like": 0.34, "ea_like": 0.33},
    }

    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()

    def suggest(self, regime: str, success_probability: Optional[float], base_weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        regime = regime if regime in self.DEFAULT_WEIGHTS else "neutral"
        weights = dict(base_weights or self.DEFAULT_WEIGHTS[regime])
        if success_probability is not None:
            lr = self.config.adaptive_learning_rate
            if success_probability >= 0.65:
                if regime == "trend":
                    weights["quant_like"] += lr * 0.7; weights["holly_like"] += lr * 0.2; weights["ea_like"] -= lr * 0.9
                elif regime == "breakout":
                    weights["holly_like"] += lr * 0.6; weights["ea_like"] += lr * 0.3; weights["quant_like"] -= lr * 0.9
                elif regime == "reversal":
                    weights["ea_like"] += lr * 0.8; weights["holly_like"] -= lr * 0.4; weights["quant_like"] -= lr * 0.4
            elif success_probability <= 0.45:
                weights["quant_like"] += lr * 0.8; weights["holly_like"] -= lr * 0.4; weights["ea_like"] -= lr * 0.4
        clipped = {k: clamp(v, self.config.min_weight_per_strategy, self.config.max_weight_per_strategy) for k, v in weights.items()}
        total = sum(clipped.values())
        return {k: float(v / total) for k, v in clipped.items()}

class ConsistencyAuditor:
    REQUIRED_SNAPSHOT_FIELDS = ["symbol","regime","vaiiixbr_signal","hybrid_signal","final_signal","final_confidence","rel_volume","rsi_14","atr_pct","dist_vwap_pct"]

    def audit_snapshot(self, snapshot: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        if snapshot.get("symbol") != "ITUB4":
            issues.append("Somente ITUB4 é permitido.")
        for field in self.REQUIRED_SNAPSHOT_FIELDS:
            if field not in snapshot:
                issues.append(f"Campo ausente: {field}")
        try:
            conf = float(snapshot.get("final_confidence"))
            if conf < 0 or conf > 1:
                issues.append("final_confidence fora de [0,1]")
        except Exception:
            issues.append("final_confidence inválida")
        if snapshot.get("regime") not in {"trend","breakout","reversal","low_volume","neutral"}:
            issues.append("regime inválido")
        if snapshot.get("final_signal") not in {"BUY","SELL","HOLD"}:
            issues.append("final_signal inválido")
        return issues

class AdaptiveLearningCoordinator:
    def __init__(self, config: Optional[LearningConfig] = None):
        self.config = config or LearningConfig()
        self.memory = TradeMemory(self.config)
        self.reward_engine = RewardEngine(self.config)
        self.meta_learner = MetaLearner(self.config)
        self.conf_calibrator = ConfidenceCalibrator(self.config)
        self.weight_updater = AdaptiveWeightUpdater(self.config)
        self.auditor = ConsistencyAuditor()

    def train_from_memory(self) -> TrainingReport:
        memory_df = self.memory.load()
        if memory_df.empty:
            return TrainingReport(False, 0, None, None, None, None, ["Memória vazia."])
        rewards = self.reward_engine.compute_rewards(memory_df)
        enriched = memory_df.copy()
        enriched["reward"] = rewards.values
        self.memory.attach_reward_column(rewards)
        return self.meta_learner.train(enriched)

    def evaluate_snapshot(self, snapshot: Dict[str, Any], base_weights: Optional[Dict[str, float]] = None) -> LearningDecision:
        issues = self.auditor.audit_snapshot(snapshot)
        if issues:
            raise ValueError("Inconsistências no snapshot: " + " | ".join(issues))
        ensure_symbol(snapshot["symbol"])
        success_probability = self.meta_learner.predict_success_proba(snapshot)
        adjusted_confidence = self.conf_calibrator.calibrate(float(snapshot["final_confidence"]), success_probability, str(snapshot["regime"]))
        suggested_weights = self.weight_updater.suggest(str(snapshot["regime"]), success_probability, base_weights)
        reasons = [f"regime={snapshot['regime']}", f"base_confidence={float(snapshot['final_confidence']):.4f}", f"adjusted_confidence={adjusted_confidence:.4f}"]
        if success_probability is not None:
            reasons.append(f"success_probability={success_probability:.4f}")
        else:
            reasons.append("modelo ainda não pronto; usando calibragem conservadora")
        final_signal = str(snapshot["final_signal"])
        label = "WATCHLIST"
        if success_probability is None:
            label = "SOFT_APPROVED" if adjusted_confidence >= self.config.approve_threshold and final_signal != "HOLD" else ("HOLD" if final_signal == "HOLD" else "WATCHLIST")
        else:
            if success_probability >= self.config.approve_threshold and adjusted_confidence >= self.config.approve_threshold:
                label = "APPROVED"
            elif success_probability <= self.config.reject_threshold:
                final_signal = "HOLD"; adjusted_confidence = min(adjusted_confidence, 0.45); label = "REJECTED"
            elif success_probability >= self.config.watchlist_threshold:
                label = "WATCHLIST"
            else:
                final_signal = "HOLD"; label = "HOLD"
        if snapshot["regime"] == "low_volume" and final_signal != "HOLD":
            final_signal = "HOLD"; adjusted_confidence = min(adjusted_confidence, 0.44); label = "REJECTED_LOW_VOLUME"; reasons.append("bloqueio por regime de baixo volume")
        return LearningDecision(final_signal, float(adjusted_confidence), None if success_probability is None else float(success_probability), label, suggested_weights, reasons, self.meta_learner.is_ready())

    def register_closed_trade(self, record: TradeRecord) -> None:
        self.memory.append(record)

def _example() -> None:
    cfg = LearningConfig(storage_dir="/mnt/data/demo_vaiiixbrxaprende")
    app = AdaptiveLearningCoordinator(cfg)
    rng = np.random.default_rng(42)
    regimes = ["trend", "breakout", "reversal", "low_volume", "neutral"]
    for i in range(120):
        regime = regimes[i % len(regimes)]
        rel_volume = float(max(0.5, rng.normal(1.15 if regime != "low_volume" else 0.78, 0.15)))
        rsi = float(clamp(rng.normal(58 if regime == "trend" else 49, 10), 10, 90))
        edge = 0.0
        if regime == "trend" and rel_volume > 1.0: edge += 0.35
        if regime == "breakout" and rel_volume > 1.2: edge += 0.28
        if regime == "low_volume": edge -= 0.30
        if rsi > 75: edge -= 0.15
        result_binary = 1 if rng.random() < clamp(0.48 + edge, 0.10, 0.90) else 0
        ret = float(rng.normal(0.25 if result_binary else -0.18, 0.22))
        dd = float(abs(rng.normal(0.08 if result_binary else 0.18, 0.07)))
        record = TradeRecord("ITUB4", f"2026-03-01 10:{i%60:02d}:00", f"2026-03-01 10:{(i+3)%60:02d}:00", "LONG", regime, "BUY", float(clamp(rng.normal(0.66, 0.10), 0.15, 0.95)), "BUY", float(clamp(rng.normal(0.63, 0.11), 0.10, 0.95)), "BUY", float(clamp(rng.normal(0.67, 0.10), 0.10, 0.97)), 31.0 + rng.normal(0, 0.8), 31.1 + rng.normal(0, 0.9), 30.7, 31.6, ret, ret * 10, dd, int(rng.integers(2, 12)), rel_volume, rsi, float(max(0.003, rng.normal(0.012, 0.004))), float(rng.normal(0.002, 0.006)), float(rng.normal(0.001, 0.005)), float(rng.normal(0.004 if regime == "trend" else 0.0005, 0.003)), float(rng.normal(0.007 if regime == "trend" else 0.001, 0.004)), True, bool(rng.random() > 0.3), bool((not result_binary) and rng.random() > 0.25), bool(result_binary and rng.random() > 0.35), regime == "low_volume", regime != "low_volume", result_binary, {"example": True})
        app.register_closed_trade(record)
    report = app.train_from_memory()
    snapshot = {"symbol": "ITUB4","regime": "trend","side": "LONG","vaiiixbr_signal": "BUY","vaiiixbr_confidence": 0.74,"hybrid_signal": "BUY","hybrid_confidence": 0.69,"final_signal": "BUY","final_confidence": 0.71,"entry_price": 31.45,"stop_price": 31.18,"take_price": 31.98,"rel_volume": 1.34,"rsi_14": 62.4,"atr_pct": 0.010,"dist_vwap_pct": 0.002,"body_pct": 0.003,"trend_spread": 0.0045,"long_trend_spread": 0.0075,"was_possible_entry": True,"was_guaranteed_entry": True,"low_volume_entry": False,"aligned_with_regime": True,"bars_held": 0}
    decision = app.evaluate_snapshot(snapshot)
    logger.info("TrainingReport: %s", report)
    logger.info("LearningDecision: %s", decision)

if __name__ == "__main__":
    _example()
