# split_pdf

PDFを分割して、前後に空白ページをつける

## 用途
見開きでスキャンされたPDFを、冊子のように印刷したい時に使う。
PDFの最初のページから、ページのサイズが同じところまで処理をする。

## 使い方
```bash
poetry config --local virtualenvs.in-project true
poetry install
poetry run .venv/bin/streamlit run main.py 
```