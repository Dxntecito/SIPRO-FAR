"""
Agrega la arquitectura SIMPLE de SIPRO-FAR encima del repositorio de tu compañero.

Uso (ejecútalo DENTRO de la carpeta raíz del repo, donde están ml/, data/, README...):
    python crear_estructura_integrada.py

- NO toca ml/, data/ (salvo agregar stock_lotes.csv), README, LICENSE,
  requirements.txt ni .gitignore.
- NO sobrescribe ningún archivo que ya exista.
"""
import sys
from pathlib import Path

RAIZ = sys.argv[1] if len(sys.argv) > 1 else "."

ARCHIVOS = """
app.py
db.py

data/stock_lotes.csv

templates/base.html
templates/control_estadistico.html
templates/departamentos_vs_ia.html
templates/simulador.html
templates/sesgo.html
templates/requerimiento.html
templates/inventario.html
templates/presupuesto.html
templates/modelo.html

static/css/estilos.css
static/js/comun.js
static/vendor/chart.umd.min.js

tests/test_basico.py

docs/01_requerimientos_y_arquitectura.md
docs/02_presupuesto_y_roi.md
docs/03_puesta_en_marcha_y_capacitacion.md
docs/04_manual_de_usuario.md
docs/05_modelo_cobit_y_riesgos.md
""".split()

base = Path(RAIZ)
if not (base / "ml").is_dir():
    print("Aviso: no encuentro la carpeta ml/ aquí. ¿Estás en la raíz del repo de tu compañero?")

creados, existentes = 0, 0
for ruta in ARCHIVOS:
    destino = base / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        existentes += 1
    else:
        destino.touch()
        creados += 1

print(f"Listo: {creados} archivos nuevos creados, {existentes} ya existían (no se tocaron).")
