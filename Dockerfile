FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src/ ./src/
COPY .streamlit/ ./.streamlit/
# Instala os pacotes de src/ (core) no ambiente, tornando-os importáveis
# de qualquer módulo sem manipulação de sys.path.
RUN pip install --no-cache-dir -e .

EXPOSE 8501
CMD ["streamlit", "run", "src/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
