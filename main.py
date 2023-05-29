import os
from tempfile import NamedTemporaryFile
import streamlit as st
from pypdf import PdfWriter, PdfReader
import pdf2image
from PIL import Image

def add_img_to_pdf(img, output_pdf):
    f = NamedTemporaryFile(delete=False)
    try:
        with open(f.name, "wb") as f:
            img.save(f, "PDF", resolution=100.0)
        with open(f.name, "rb") as f:
            input_pdf = PdfReader(f)
            page = input_pdf.pages[0]
            output_pdf.add_page(page)
    finally:
        os.unlink(f.name)

@st.cache_data
def load_pdf(input_path, pdf_bytes = None):
    if (pdf_bytes != None):
        images = pdf2image.convert_from_bytes(pdf_bytes)
    else:
        images = pdf2image.convert_from_path(input_path)
        
    tabs = st.tabs(list(map(lambda a:f"ページ{a}",range(1, len(images)+1))))
    for i, t in enumerate(tabs):
        with t:
            st.image(images[i], width=150, use_column_width="auto", caption=f"{i+1}")
    return images

def get_concat_h(im1, im2):
    dst = Image.new('RGB', (im1.width + im2.width, im1.height))
    dst.paste(im1, (0, 0))
    dst.paste(im2, (im1.width, 0))
    return dst

def get_concat_v(im1, im2):
    dst = Image.new('RGB', (im1.width, im1.height + im2.height))
    dst.paste(im1, (0, 0))
    dst.paste(im2, (0, im1.height))
    return dst

def split_pdf(input_path, images, divide_direction = "左右"):
    output_pdf = PdfWriter()
    initial_width = initial_height = 0
    processed_num = 0
    left_img = right_img = None
    blank_img = None
    for i, img in enumerate(images):
        width, height = img.size
        if (i==0):
            initial_width = width
            initial_height = height
        else:
            if (width != initial_width or height != initial_height):
                break
        processed_num += 1
        if divide_direction == "横書き（左右に分割）":
            half_width = width // 2
            left_img = img.crop((0, 0, half_width, height))
            blank_img = Image.new('RGB', (half_width, height), color="white")
            tmp_left_img = blank_img if i==0 else right_img
            concat_img = get_concat_h(tmp_left_img, left_img)
            right_img = img.crop((half_width, 0, width, height))
        elif divide_direction == "縦書き（上下に分割）":
            half_height = height // 2
            left_img = img.crop((0, 0, width, half_height))
            blank_img = Image.new('RGB', (width, half_height), color="white")
            tmp_left_img = blank_img if i==0 else right_img
            concat_img = get_concat_v(tmp_left_img, left_img)
            right_img = img.crop((0, half_height, width, height))
        else:
            raise
        add_img_to_pdf(concat_img, output_pdf)
        
    if right_img:
        if divide_direction == "横書き（左右に分割）":
            concat_img = get_concat_h(right_img, blank_img)
        elif divide_direction == "縦書き（上下に分割）":
            concat_img = get_concat_v(right_img, blank_img)
        else:
            raise
        add_img_to_pdf(concat_img, output_pdf)

    for img in images[processed_num:]:
        add_img_to_pdf(img, output_pdf)

    file_name = os.path.splitext(os.path.basename(input_path))[0]
    converted_name = f"{file_name}_conv.pdf"
    with open(converted_name, "wb") as f:
        output_pdf.write(f)
    return converted_name
    
def st_main():
    st.markdown('# split_pdf')
    st.markdown('')
    st.markdown('見開きでスキャンしたPDFを各ページ左右または上下で分割し、表紙をつけることで冊子形式で印刷可能なPDFに変換します。')
    
    file = st.file_uploader('PDFをアップロードしてください.', type=['pdf'])
    if file:
        images = load_pdf(file.name, file.read())

        with st.form("my_form"):
            divide_direction = st.radio(
                "ページの分割方法",
                ('横書き（左右に分割）', '縦書き（上下に分割）'))
            submitted = st.form_submit_button("PDF生成")        

        # PDFを分割
        if submitted:
            with st.spinner(f"{file.name} を変換中"):
                converted_name = split_pdf(file.name, images, divide_direction=divide_direction)

            st.markdown(f'変換を完了しました。')
            
            with open(converted_name, 'br') as f:
                st.download_button("ダウンロード", f , converted_name)

if __name__ == '__main__':
    st_main()
