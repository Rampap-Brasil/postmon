FROM python:2.7-slim

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libz-dev \
    libxml2-dev \
    libxslt1-dev \
    libyaml-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Atualizar pip e ferramentas
RUN pip install --upgrade pip==20.3.4
RUN pip install setuptools==44.1.1 wheel==0.37.1

ENV APP_DIR=/srv/postmon
WORKDIR $APP_DIR

# Copiar e instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

EXPOSE 9876

ENTRYPOINT ["python", "PostmonServer.py"]