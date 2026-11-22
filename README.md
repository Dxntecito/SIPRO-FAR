# SIPRO-FAR — Sistema Predictivo de Demanda Farmacológica y Transparencia de Stock

Proyecto del **PETI 2026–2030** para el **Hospital II-1 Luis Enrique Heysen Incháustegui (EsSalud – Red Prestacional Lambayeque)**.

## Componentes
- **Motor Predictivo ML (`ml/train_model.py`):** Entrenamiento y comparación de modelos (Ridge, Random Forest, HistGradientBoosting) sobre `data/dataset_medicamentos_mensual.csv` (49,500 registros, 55 escenarios, 15 medicamentos críticos, 5 departamentos), validado por `escenario_id` sin fuga de datos.
  - Modelo ganador: **Random Forest** (`R² = 0.9786`, `MAPE = 7.42%`, `MAE = 114.83`, `RMSE = 232.93`).
- **Control Estadístico 3-Sigma y Simulador de Crisis (`ml/engine.py`):** Detección de picos anómalos ($\mu \pm 3\sigma$) y simulación de brotes de dengue, Fenómeno de El Niño, lluvias y desembalse del HNAAA.
- **Base de Datos y Sitio Web (en construcción):** Portal público de transparencia de stock para asegurados, panel administrativo CRUD para Farmacia y dashboard predictivo.

## Cómo ejecutar localmente
```bash
pip install -r requirements.txt
python ml/train_model.py
python ml/engine.py
```
