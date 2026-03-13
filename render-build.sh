#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Instala apenas o navegador, sem tentar ser administrador (root)
playwright install chromium
