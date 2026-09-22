# Imagem única: interface + API no mesmo processo.
#
# É o formato que Render e Railway esperam — um contêiner, um serviço. Juntar
# os dois elimina o CORS (mesma origem), dispensa configurar o endereço da API
# em lugar nenhum e corta pela metade a conta de hospedagem, que é cobrada por
# serviço.
#
# A API atende sob /api; todo o resto é a interface. O prefixo existe porque
# /obras da API colidiria com /obras da tela.

# --------------------------------------------------------------------- telas
FROM node:22-alpine AS interface
WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
# Caminho relativo: a interface fala com a API na própria origem, então não há
# endereço para acertar entre ambientes.
ENV VITE_API=/api
RUN npm run build

# ----------------------------------------------------------------- aplicação
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_PREFIX=/api \
    ESTATICOS_DIR=/app/estaticos

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY --from=interface /app/dist ./estaticos

RUN useradd --create-home treele && chown -R treele /app
USER treele

EXPOSE 8000
# A porta vem do ambiente: as plataformas de hospedagem escolhem qual usar.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
