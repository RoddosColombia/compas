"""S1: cfo/calc y cfo/goldens NO importan modelos de dominio ajenos ni tocan el driver
de Mongo; la única subruta que persiste es cfo/datos/repositorios.py y solo cfo_*."""

import pathlib
import re

CFO = pathlib.Path(__file__).resolve().parents[2] / "app" / "cfo"

# Subrutas que NO pueden tocar Mongo directamente ni importar modelos de dominio ajenos.
LOGICA = [CFO / "calc", CFO / "goldens"]
PROHIBIDO_IMPORT = re.compile(
    r"from app\.domain\.(?!__init__)"
)  # modelos de dominio ajenos
PROHIBIDO_DRIVER = re.compile(r"get_pymongo_collection|motor|AsyncIOMotor")


def _py_files(base):
    return [p for p in base.rglob("*.py") if p.name != "__init__.py"]


def test_calc_y_goldens_no_tocan_driver_ni_dominio_ajeno():
    ofensas = []
    for base in LOGICA:
        for f in _py_files(base):
            txt = f.read_text(encoding="utf-8")
            # excepción: cfo/goldens/modelo.py define su PROPIO Document (cfo_goldens)
            if f.name == "modelo.py":
                continue
            if PROHIBIDO_DRIVER.search(txt):
                ofensas.append(f"{f}: toca el driver de Mongo")
            for m in PROHIBIDO_IMPORT.finditer(txt):
                # se permite importar tipos de lectura de dominio SOLO si el spec lo
                # documenta; para inc1 no debería hacer falta ninguno en calc/goldens.
                ofensas.append(f"{f}: importa modelo de dominio ajeno ({m.group()})")
    assert ofensas == [], "Violaciones S1:\n" + "\n".join(ofensas)


def test_solo_repositorios_persiste_cfo():
    # cfo/datos/repositorios.py solo referencia CFOGolden (colección cfo_goldens)
    repo = (CFO / "datos" / "repositorios.py").read_text(encoding="utf-8")
    assert "CFOGolden" in repo
    assert "app.domain" not in repo  # no persiste colecciones ajenas
