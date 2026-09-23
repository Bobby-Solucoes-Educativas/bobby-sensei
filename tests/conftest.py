# Os módulos de src/ (core/, ui/, ...) são importados como pacotes de topo
# (`from core.chat_state import Message`), assumindo src/ na raiz do
# sys.path — o mesmo efeito que `streamlit run src/app.py` dá de graça (o
# interpretador prepend a pasta do script). Os testes não passam por lá, então
# fazem isso à mão aqui, sem depender da instalação editável do pacote.
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
