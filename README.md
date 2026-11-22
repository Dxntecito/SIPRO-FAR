# SIPRO-FAR — Sistema Predictivo de Demanda Farmacológica y Transparencia de Stock

Proyecto priorizado (Fase 1) del **PETI 2026–2030** para el **Hospital II-1 Luis Enrique Heysen Incháustegui (EsSalud – Red Prestacional Lambayeque)**, alineado a **COBIT 2019 (MEA03 y DSS04 – Nivel 4)** y **OEI 5**.

## Estructura del Repositorio

```text
SIPRO-FAR/
├── data/
│   └── dataset_medicamentos_mensual.csv   # 49,500 filas (55 escenarios, 15 meds, 5 deptos, 2016–2025)
├── ml/
│   ├── train_model.py                     # Validación CSV + comparación Ridge vs RF vs HistGB
│   ├── engine.py                          # Motor predictivo Random Forest + 3-Sigma + Simulador de Crisis
│   ├── model_metrics.json                 # Métricas reales (R²=0.9786, MAE=114.83, MAPE=7.42%)
│   ├── evaluacion_modelos.png             # Gráfica de comparación de modelos (Anexo 4)
│   └── control_3sigma_ejemplo.png         # Gráfica de control estadístico 3-Sigma (Anexo 4)
├── db/
│   ├── schema_mysql.sql                   # Esquema MySQL 8.0 de 8 tablas en 3FN (Workbench / Railway)
│   ├── seed_mysql.sql                     # Carga inicial lista para ejecutar en MySQL Workbench / Railway
│   ├── generar_seed_mysql.py              # Regenera seed_mysql.sql desde el CSV
│   └── diagrama_eer.png                   # Diagrama EER generado en MySQL Workbench (Anexo 4)
└── requirements.txt
```

## Cómo levantar el entorno localmente

### 1. Base de Datos (MySQL 8 / MySQL Workbench)
1. Abrir **MySQL Workbench** y ejecutar `db/schema_mysql.sql` (crea `siprofar_db` con las 8 tablas en 3FN).
2. Ejecutar `db/seed_mysql.sql` (carga 4 roles, 3 usuarios, 15 medicamentos, 5 departamentos, 75 lotes, 16 alertas, 10 búsquedas sin stock y 9,000 registros históricos).

### 2. Motor de IA en Python
```bash
pip install -r requirements.txt
python ml/train_model.py     # Genera ml/modelo_siprofar.joblib (~10 seg)
python ml/engine.py          # Prueba en consola del simulador de crisis y 3-Sigma
```

## Usuarios de prueba cargados en `siprofar_db`
| Usuario | Contraseña | Rol |
| :--- | :--- | :--- |
| `farmacia_heysen` | `Farmacia2026*` | `FARMACEUTICO` |
| `calidad_heysen` | `Calidad2026*` | `PLANEAMIENTO` |
| `direccion_heysen` | `Direccion2026*` | `DIRECCION` |
