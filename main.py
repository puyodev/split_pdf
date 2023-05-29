import os
from tempfile import NamedTemporaryFile
import streamlit as st
from pypdf import PdfWriter, PdfReader
import pdf2image
import streamlit_analytics
from dotenv import load_dotenv

load_dotenv(verbose=True)

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
def load_pdf(input_path, pdf_bytes=None):
    if pdf_bytes != None:
        images = pdf2image.convert_from_bytes(pdf_bytes)
    else:
        images = pdf2image.convert_from_path(input_path)
    cols = st.columns(min(len(images), 2))
    for i, c in enumerate(cols):
        with c:
            st.image(images[i], caption=f"ページ{i+1}")
    return images

def preview_pdf(input_path, pdf_bytes=None, pages=2):
    if pdf_bytes != None:
        images = pdf2image.convert_from_bytes(pdf_bytes, dpi = 50, last_page=pages)
    else:
        images = pdf2image.convert_from_path(input_path, dpi = 50, last_page=pages)
    preview_cols=3
    cols = st.columns(preview_cols)
    for i, img in enumerate(images):
        with cols[i%preview_cols]:
            st.image(images[i], caption=f"ページ{i+1}")
    return images



def split_pdf(
    input_path,
    _images,
    divide_direction="左右",
    use_1stpage_as_cover=False,
    right_to_left=False,
):
    output_pdf = PdfWriter()
    initial_width = initial_height = 0
    processed_num = 0
    half_page = False
    if divide_direction == "自動":
        horinetal_count = vertical_count = 0
        for i, img in enumerate(_images):
            width, height = img.size
            if width < height:
                horinetal_count += 1
            else:
                vertical_count += 1
        divide_direction = "左右に分割" if horinetal_count < vertical_count else "上下に分割"

    # 1枚目だけサイズが異なる
    if len(_images) > 1 and (
        _images[0].width != _images[1].width or _images[0].height != _images[1].height
    ):
        half_page = True

    if not use_1stpage_as_cover:
        if half_page:
            # 1枚目だけサイズが異なるので強制的に表紙として使う
            use_1stpage_as_cover = True

    for i, img in enumerate(_images):
        width, height = img.size

        def get_l_r():
            if divide_direction == "左右に分割":
                half_width = width // 2
                left_img = img.crop((0, 0, half_width, height))
                right_img = img.crop((half_width, 0, width, height))
            elif divide_direction == "上下に分割":
                half_height = height // 2
                left_img = img.crop((0, 0, width, half_height))
                right_img = img.crop((0, half_height, width, height))
            else:
                raise
            if right_to_left:
                return right_img, left_img
            return left_img, right_img

        if i == 0 and use_1stpage_as_cover:
            if half_page:
                add_img_to_pdf(img, output_pdf)
            else:
                left_img, right_img = get_l_r()
                add_img_to_pdf(right_img, output_pdf)
            processed_num += 1
            continue

        if initial_width == 0:
            initial_width = width
            initial_height = height
        else:
            if width != initial_width or height != initial_height:
                break
        processed_num += 1
        left_img, right_img = get_l_r()
        add_img_to_pdf(left_img, output_pdf)
        if i == 0:
            output_pdf.insert_blank_page(index=0)
        add_img_to_pdf(right_img, output_pdf)
    output_pdf.add_blank_page()
    for img in _images[processed_num:]:
        add_img_to_pdf(img, output_pdf)

    file_name = os.path.splitext(os.path.basename(input_path))[0]
    converted_name = f"{file_name}_conv.pdf"
    with open(converted_name, "wb") as f:
        output_pdf.write(f)
    return converted_name


def st_main():
    with streamlit_analytics.track(unsafe_password=os.environ.get("ANALYTICS_KEY","")):
        st.markdown("# split_pdf")
        st.markdown("")
        st.markdown("見開きでスキャンされたPDFを分割し、表紙をつけて冊子形式で印刷できるようにします。")

        file = st.file_uploader("PDFをアップロードしてください.", type=["pdf"])
        if file:
            st.markdown(f"変換前")
            images = load_pdf(file.name, file.read())

            with st.form("my_form"):
                divide_direction = st.radio(
                    "ページの分割方法", ("自動", "左右に分割", "上下に分割"), horizontal=True
                )
                use_1stpage_as_cover = st.checkbox("1ページ目を表紙として扱う", value=False)

                right_to_left = st.checkbox(
                    "右側の方が若いページ", value=False
                )
                submitted = st.form_submit_button("PDF生成")

            # PDFを分割
            if submitted:
                with st.spinner(f"{file.name} を変換中"):
                    converted_name = split_pdf(
                        file.name,
                        images,
                        divide_direction=str(divide_direction),
                        use_1stpage_as_cover=use_1stpage_as_cover,
                        right_to_left=right_to_left,
                    )

                st.markdown("変換後")
                preview_pdf(converted_name, None, 3)
                st.markdown(f"ダウンロード後、両面印刷か2in1で印刷してください。")
                with open(converted_name, "br") as f:
                    st.download_button("ダウンロード", f, converted_name)


if __name__ == "__main__":
    st_main()
