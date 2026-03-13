#!/usr/bin/env bash
# Sair se houver erro
set -o errexit

# Atualiza o pip e instala as dependências do Python
pip install --upgrade pip
pip install -r requirements.txt

# Instala o binário do Chromium (SEM o comando --with-deps que pede root)
playwright install chromium
