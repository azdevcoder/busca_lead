#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Este comando tenta instalar as libs de sistema necessárias no Render
playwright install --with-deps chromium
