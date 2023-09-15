import datetime
import logging
import os
from tempfile import NamedTemporaryFile
import streamlit as st
_orig_number_input = st.number_input
from pypdf import PdfWriter, PdfReader
import pdf2image
import streamlit_analytics
from streamlit import runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx
from google.cloud import firestore
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


@st.cache_data(max_entries=1)
def load_pdf(pdf_bytes):
    images = pdf2image.convert_from_bytes(pdf_bytes)
    return images


def preview_images(images, first_page=0, pages=2):
    preview_cols = 2
    cols = st.columns(preview_cols)
    for i, img in enumerate(images[first_page : first_page + pages]):
        with cols[i % preview_cols]:
            st.image(img, caption=f"ページ{i+first_page+1}", use_column_width="always")
    return images


def split_images(
    _images, divide_direction="左右", right_to_left=False, max_process_num=0
):
    initial_width = initial_height = 0
    processed_num = 0
    half_page = False
    images = []
    if divide_direction == "自動":
        img = _images[1] if len(_images) > 1 else _images[0]
        width, height = img.size
        divide_direction = "上下に分割" if width < height else "左右に分割"

    # 1枚目だけサイズが異なる
    if len(_images) > 1 and (
        _images[0].width != _images[1].width or _images[0].height != _images[1].height
    ):
        half_page = True

    last_page = None

    for i, img in enumerate(_images):
        width, height = img.size

        if max_process_num > 0 and i + 1 == max_process_num:
            break

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

        if i == 0:
            if half_page:
                images.append(img)
            else:
                last_page, right_img = get_l_r()
                images.append(right_img)
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
        images.append(left_img)
        images.append(right_img)
    if last_page:
        images.append(last_page)
    for img in _images[processed_num:]:
        images.append(img)

    return images, processed_num


def get_conv_file_name(input_path):
    file_name = os.path.splitext(os.path.basename(input_path))[0]
    converted_name = f"{file_name}_conv.pdf"
    return converted_name


def images_to_pdf(pdf_path, images):
    output_pdf = PdfWriter()
    for img in images:
        add_img_to_pdf(img, output_pdf)
    with open(pdf_path, "wb") as f:
        output_pdf.write(f)

@st.cache_resource
def get_firestore_db():
    # Authenticate to Firestore with the JSON account key.
    db = firestore.Client.from_service_account_json("/tmp/firestore-key.json")
    return db

def formatNow():
    now = datetime.datetime.now()
    return str(now)


def get_remote_ip() -> str:
    """Get remote ip."""

    try:
        ctx = get_script_run_ctx(True)
        if ctx is None:
            return None

        session_info = runtime.get_instance().get_client(ctx.session_id)
        if session_info is None:
            return None
    except Exception as e:
        return None

    return session_info.request.remote_ip

# Firestoreにログを記録するカスタムロギングハンドラー
class FirestoreHandler(logging.StreamHandler):
    def emit(self, record):
        message = self.format(record)
        db = get_firestore_db()

        if st.session_state.get(record.lineno):
           return
        
        st.session_state[record.lineno] = 1

        db.collection("logs").add({"created": f"{formatNow()}", "message": message, "ip": {get_remote_ip()}}, formatNow())
        # ここで print や他のハンドラーを呼び出すこともできます
        super().emit(record)

def create_logger(level = 'DEBUG', file = None):
    logger = logging.getLogger(__name__)
    logger.propagate = False
    logger.setLevel(level)
    if sum([isinstance(handler, FirestoreHandler) for handler in logger.handlers]) == 0:
        ch = FirestoreHandler()
        logger.addHandler(ch)
        
    return logger

@st.cache_resource
def get_logger():
    logger = create_logger(level = 'DEBUG')
    return logger

def st_main():

    firebase_key_base64 = os.environ.get("FIREBASE_ACCESS_KEY", "")
    import base64
    firebase_key_str = base64.b64decode(firebase_key_base64.encode())

    f = NamedTemporaryFile(delete=False)
    with open("/tmp/firestore-key.json", "wb") as f:
        f.write(firebase_key_str)

    logger = get_logger()
    logger.info("display")
    
    with streamlit_analytics.track(unsafe_password=os.environ.get("ANALYTICS_KEY", ""), firestore_key_file="/tmp/firestore-key.json", firestore_collection_name="counts"):

        # firesrore保存時に例外になるのでオリジナルの関数に差し替え
        st.number_input = _orig_number_input

        st.markdown("# 見開きPDF分割君")
        st.markdown("")
        st.markdown("見開きでスキャンされたPDFを分割・順番入れ替えし、両面印刷で冊子として印刷できるPDFに変換します。")

        file = st.file_uploader(
            "PDFをアップロードしてください.", type=["pdf"], accept_multiple_files=False
        )
        max_size_mb = 100

        if file:
            bytes = file.read()
            logger.info(f"filename:{file.name} size:{len(bytes)}")

            if len(bytes) > max_size_mb * 1024 * 1024:
                raise Exception(
                    f"サイズが大きすぎます。{len(bytes)/1024/1024:.2f}MB / {max_size_mb}MB"
                )
            images = load_pdf(bytes)

            with st.expander("詳細設定"):
                st.markdown(f"変換前プレビュー")
                preview_images(images, 0, 2)
                divide_direction = st.radio(
                    "分割の方向", ("自動", "左右に分割", "上下に分割"), horizontal=True
                )

                right_to_left = st.checkbox("右側の方が若いページ", value=False)

                max_process_num = st.number_input(
                    "分割するページの数(0は自動)", max_value=len(images), value=0, min_value=0
                )

                output_images, processed_num = split_images(
                    images,
                    divide_direction=str(divide_direction),
                    right_to_left=right_to_left,
                    max_process_num=int(max_process_num),
                )

                st.markdown("変換後プレビュー")
                st.markdown("最初の2ページ")
                preview_images(output_images, 0, 2)
                if processed_num > 1:
                    st.markdown("最後の2ページ")
                    preview_images(output_images, processed_num * 2 - 2, 2)

            with st.form("my_form"):
                submitted = st.form_submit_button("PDF生成")

            # PDFを分割
            if submitted:
                with st.spinner(f"{file.name} を変換中"):
                    converted_name = get_conv_file_name(file.name)
                    images_to_pdf(converted_name, images=output_images)

                st.markdown(f"ダウンロード後、両面印刷か2in1で印刷してください。")
                with open(converted_name, "br") as f:
                    st.download_button("ダウンロード", f, converted_name)
                    logger.info({"converted": converted_name})


if __name__ == "__main__":
    st_main()
