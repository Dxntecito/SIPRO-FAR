import json
import os
import time
import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "dataset_medicamentos_mensual.csv"))

CAT_FEATURES = ["medicamento_id", "departamento"]
NUM_FEATURES = [
    "costo_unitario",
    "base_mensual",
    "sensibilidad_dengue",
    "sensibilidad_clima",
    "mes",
    "mes_sin",
    "mes_cos",
    "pedido_departamento",
    "consumo_mes_actual",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_12",
    "media_movil_3",
    "media_movil_12",
    "desviacion_movil_12",
    "nivel_dengue",
    "evento_nino",
    "lluvia_mm",
    "desembalse_almanzor",
    "pronostico_dengue_mes_objetivo",
    "pronostico_nino_mes_objetivo",
]
TARGET = "demanda_mes_anio_siguiente"


def mape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true > 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100.0)


def validate_dataset(df: pd.DataFrame) -> dict:
    report = {
        "filas": int(len(df)),
        "columnas": int(df.shape[1]),
        "nulos_totales": int(df.isnull().sum().sum()),
        "duplicados_exactos": int(df.duplicated().sum()),
        "escenarios": int(df["escenario_id"].nunique()),
        "medicamentos": int(df["medicamento_id"].nunique()),
        "departamentos": int(df["departamento"].nunique()),
        "anios": [int(df["anio"].min()), int(df["anio"].max())],
        "target_min": float(df[TARGET].min()),
        "target_max": float(df[TARGET].max()),
        "target_mean": round(float(df[TARGET].mean()), 2),
        "negativos_en_consumo_o_target": int(
            ((df["consumo_mes_actual"] < 0) | (df[TARGET] < 0)).sum()
        ),
    }
    return report


def build_preprocessor(dense_output=True):
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=not dense_output),
                CAT_FEATURES,
            ),
            ("num", StandardScaler(), NUM_FEATURES),
        ]
    )


def plot_evaluation(results: list, y_test, best_preds, best_name: str, out_path: str):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=220)
    fig.patch.set_facecolor("white")

    names = [r["modelo"] for r in results]
    r2s = [r["r2"] for r in results]
    mapes = [r["mape_pct"] for r in results]

    ax1 = axes[0]
    x = np.arange(len(names))
    w = 0.35
    b1 = ax1.bar(x - w / 2, [v * 100 for v in r2s], width=w, color="#0D5C8C", label="R² (%)")
    b2 = ax1.bar(x + w / 2, mapes, width=w, color="#C0392B", label="MAPE (%) - menor es mejor")
    ax1.set_xticks(x)
    ax1.set_xticklabels(names, fontsize=8.8, fontweight="bold")
    ax1.set_ylim(0, 112)
    ax1.set_ylabel("Porcentaje (%)")
    ax1.set_title("Comparación de Modelos ML (Validación por Escenario)", fontweight="bold", color="#1B2A5B")
    ax1.legend(frameon=False, fontsize=8.5)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    for bar in b1:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, h + 1.5, f"{h:.2f}%", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#0D5C8C")
    for bar in b2:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, h + 1.5, f"{h:.2f}%", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#C0392B")

    ax2 = axes[1]
    sample_idx = np.random.RandomState(42).choice(len(y_test), size=min(2500, len(y_test)), replace=False)
    yt = np.asarray(y_test)[sample_idx]
    yp = np.asarray(best_preds)[sample_idx]
    ax2.scatter(yt, yp, s=10, alpha=0.35, color="#177E89", edgecolors="none")
    lim_max = max(yt.max(), yp.max()) * 1.03
    ax2.plot([0, lim_max], [0, lim_max], color="#C0392B", linestyle="--", linewidth=1.6, label="Predicción ideal (y = x)")
    ax2.set_xlabel("Demanda Real (unidades)")
    ax2.set_ylabel("Demanda Predicha (unidades)")
    ax2.set_title(f"Real vs. Predicho — {best_name}", fontweight="bold", color="#1B2A5B")
    ax2.legend(frameon=False, fontsize=8.5)
    ax2.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_3sigma_example(df: pd.DataFrame, out_path: str):
    # Pick a representative high-dengue scenario for MED-001 in Emergencia
    sub = df[
        (df["medicamento_id"] == "MED-001")
        & (df["departamento"] == "Emergencia y Shock Trauma")
    ].copy()
    # Select scenario with highest peak z-score so chart demonstrates crisis detection clearly
    sub["z"] = (sub["consumo_mes_actual"] - sub["media_movil_12"]) / sub["desviacion_movil_12"].replace(0, np.nan)
    top_esc = int(sub.loc[sub["z"].idxmax(), "escenario_id"])
    s = sub[sub["escenario_id"] == top_esc].sort_values("mes")

    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    x = s["mes"].values
    consumo = s["consumo_mes_actual"].values
    media = s["media_movil_12"].values
    desv = s["desviacion_movil_12"].values
    lcs = media + 3 * desv
    lci = np.maximum(0, media - 3 * desv)
    alerta_2s = media + 2 * desv

    fig, ax = plt.subplots(figsize=(10.5, 4.6), dpi=220)
    fig.patch.set_facecolor("white")

    ax.fill_between(x, lci, lcs, color="#DBEAFE", alpha=0.45, label="Banda de Control Normal (μ ± 3σ)")
    ax.plot(x, lcs, color="#C0392B", linestyle="--", linewidth=1.6, label="Límite Superior 3σ (LCS)")
    ax.plot(x, alerta_2s, color="#D97706", linestyle=":", linewidth=1.4, label="Alerta Temprana (+2σ)")
    ax.plot(x, media, color="#1B2A5B", linestyle="-.", linewidth=1.4, label="Media Móvil 12m (μ)")
    ax.plot(x, consumo, color="#0D5C8C", marker="o", linewidth=2.2, markersize=6, label="Consumo Mensual Real")

    # Highlight points above +2sigma / +3sigma
    crit_mask = consumo >= alerta_2s
    if crit_mask.any():
        ax.scatter(x[crit_mask], consumo[crit_mask], color="#C0392B", s=85, zorder=6, label="Pico Anómalo / Alerta Activa")

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(meses, fontweight="bold")
    ax.set_ylabel("Unidades (Tabletas)")
    ax.set_title(
        f"Control Estadístico 3-Sigma — Paracetamol 500 mg | Emergencia y Shock Trauma (Escenario #{top_esc})",
        fontweight="bold",
        color="#1B2A5B",
        pad=10,
    )
    ax.legend(loc="upper right", fontsize=8.2, frameon=True, facecolor="white")
    ax.grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    plt.savefig(out_path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close()


def main():
    print("Cargando dataset:", CSV_PATH)
    df = pd.read_csv(CSV_PATH)
    val_report = validate_dataset(df)
    print("Validación CSV:", json.dumps(val_report, indent=2, ensure_ascii=False))

    X = df[CAT_FEATURES + NUM_FEATURES]
    y = df[TARGET]
    groups = df["escenario_id"]

    # Split strictly by escenario_id (no leakage between scenarios)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    print(f"Train: {len(X_train)} filas ({groups.iloc[train_idx].nunique()} escenarios) | Test: {len(X_test)} filas ({groups.iloc[test_idx].nunique()} escenarios)")

    candidates = [
        ("Regresión Lineal (Ridge)", Ridge(alpha=1.0)),
        (
            "Random Forest",
            RandomForestRegressor(
                n_estimators=120,
                max_depth=16,
                min_samples_leaf=4,
                random_state=42,
                n_jobs=-1,
            ),
        ),
        (
            "HistGradientBoosting",
            HistGradientBoostingRegressor(
                max_iter=300,
                learning_rate=0.06,
                max_depth=8,
                min_samples_leaf=20,
                random_state=42,
            ),
        ),
    ]

    results = []
    best_pipe = None
    best_r2 = -999.0
    best_preds = None
    best_name = ""

    for name, est in candidates:
        t0 = time.time()
        pipe = Pipeline([("prep", build_preprocessor(dense_output=True)), ("model", est)])
        pipe.fit(X_train, y_train)
        preds = np.maximum(0, pipe.predict(X_test))
        elapsed = round(time.time() - t0, 2)

        r2 = float(r2_score(y_test, preds))
        mae = float(mean_absolute_error(y_test, preds))
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        mp = mape(y_test, preds)

        res = {
            "modelo": name,
            "r2": round(r2, 4),
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "mape_pct": round(mp, 2),
            "tiempo_seg": elapsed,
        }
        results.append(res)
        print(f" -> {name}: R²={r2:.4f} | MAE={mae:.2f} | RMSE={rmse:.2f} | MAPE={mp:.2f}% ({elapsed}s)")

        if r2 > best_r2:
            best_r2 = r2
            best_pipe = pipe
            best_preds = preds
            best_name = name

    # Save best model
    model_path = os.path.join(BASE_DIR, "modelo_siprofar.joblib")
    joblib.dump(best_pipe, model_path)
    print(f"\nMejor modelo guardado en: {model_path} ({best_name})")

    # Save metrics JSON
    metrics_payload = {
        "validacion_dataset": val_report,
        "split": {
            "metodo": "GroupShuffleSplit por escenario_id (80/20, sin fuga de datos)",
            "train_filas": int(len(X_train)),
            "test_filas": int(len(X_test)),
            "train_escenarios": int(groups.iloc[train_idx].nunique()),
            "test_escenarios": int(groups.iloc[test_idx].nunique()),
        },
        "comparacion_modelos": results,
        "modelo_ganador": best_name,
        "cumple_kpi_peti": {
            "meta_r2": 0.90,
            "meta_mape_pct": 12.0,
            "cumple": bool(best_r2 >= 0.90 and min(r["mape_pct"] for r in results if r["modelo"] == best_name) <= 12.0),
        },
        "features": {"categoricas": CAT_FEATURES, "numericas": NUM_FEATURES, "target": TARGET},
    }
    metrics_path = os.path.join(BASE_DIR, "model_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2, ensure_ascii=False)

    # Generate visual charts for Anexo 4
    plot_evaluation(results, y_test, best_preds, best_name, os.path.join(BASE_DIR, "evaluacion_modelos.png"))
    plot_3sigma_example(df, os.path.join(BASE_DIR, "control_3sigma_ejemplo.png"))
    print("Gráficas generadas: evaluacion_modelos.png y control_3sigma_ejemplo.png")


if __name__ == "__main__":
    main()
