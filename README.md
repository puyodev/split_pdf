# split_pdf

## 用途
見開きでスキャンしたPDFを各ページ左右または上下で分割し、表紙をつけることで冊子形式で印刷可能なPDFに変換します。

## 使い方
```bash
poetry config --local virtualenvs.in-project true
poetry install
poetry run .venv/bin/streamlit run main.py 
```