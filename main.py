import datetime
import logging
import os
from tempfile import NamedTemporaryFile

from typing import List, Tuple
import streamlit as st

_orig_number_input = st.number_input
_orig_text_input = st.text_input
import pdf2image
from PIL import Image, ImageDraw, ImageFont
import streamlit_analytics
from streamlit import runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx
from google.cloud import firestore
from dotenv import load_dotenv

load_dotenv(verbose=True)
version_string = "ver.0.94"


@st.cache_data(max_entries=1)
def load_pdf(pdf_bytes: bytes) -> List[Image.Image]:
    images = pdf2image.convert_from_bytes(pdf_bytes)
    return images


def create_image(width: int, height: int, str: str = "") -> Image:
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    fnt = ImageFont.truetype("./Kokoro.otf", 120)  # ImageFontインスタンスを作る
    _, _, w, h = draw.textbbox((0, 0), str, font=fnt)
    draw.text(((width - w) / 2, (height - h) / 4), str, font=fnt, fill="black")
    return img


def preview_images(images: List[Image.Image], first_page=0, pages=2):
    preview_cols = 2
    cols = st.columns(preview_cols)
    for i, img in enumerate(images[first_page : first_page + pages]):
        with cols[i % preview_cols]:
            st.image(img, caption=f"ページ{i+first_page+1}", use_column_width="always")
    return images


def split_images(
    _images: List[Image.Image],
    divide_direction: str = "左右",
    right_to_left: bool = False,
    max_process_num: int = 0,
    add_front_cover: bool = True,
    front_cover_string: str = "",
) -> Tuple[List[Image.Image], int]:
    initial_width = initial_height = 0
    processed_num = 0
    half_page = False
    images = []
    if divide_direction == "自動":
        img = _images[1] if len(_images) > 1 else _images[0]
        width, height = img.size
        divide_direction = "上下に分割" if width < height else "左右に分割"

    # 1枚目だけサイズが異なる
    if len(_images) > 1 and (_images[0].width != _images[1].width or _images[0].height != _images[1].height):
        half_page = True

    last_page = None

    for i, img in enumerate(_images):
        width, height = img.size

        if max_process_num > 0 and i == max_process_num:
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
                # print(f"{i} get_l_r")
                last_page, right_img = get_l_r()
                if add_front_cover:
                    processed_num += 2
                    images.append(create_image(last_page.width, last_page.height, front_cover_string))
                    images.append(last_page)
                    last_page = create_image(last_page.width, last_page.height, "")

                processed_num += 1
                images.append(right_img)
            continue

        if initial_width == 0:
            initial_width = width
            initial_height = height
        else:
            if width != initial_width or height != initial_height:
                break

        # print(f"{i} get_l_r")
        left_img, right_img = get_l_r()
        processed_num += 2
        images.append(left_img)
        images.append(right_img)
    # print(f"last_page {i} get_l_r")
    if last_page:
        processed_num += 1
        images.append(last_page)
    for img in _images[i:]:
        images.append(img)

    return images, processed_num


def get_conv_file_name(input_path: str) -> str:
    file_name = os.path.splitext(os.path.basename(input_path))[0]
    converted_name = f"{file_name}_conv.pdf"
    return converted_name


def images_to_pdf(pdf_path: str, images: List[Image.Image]) -> None:
    images[0].save(pdf_path, save_all=True, append_images=images[1:])


@st.cache_resource
def get_firestore_db() -> firestore.Client:
    # Authenticate to Firestore with the JSON account key.
    db = firestore.Client.from_service_account_json("/tmp/firestore-key.json")
    return db


def formatNow() -> str:
    JST = datetime.timezone(datetime.timedelta(hours=+9), "JST")
    now = datetime.datetime.now(JST)
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

        db.collection("logs").add(
            {"created": f"{formatNow()}", "message": message, "ip": {get_remote_ip()}}, formatNow()
        )
        # ここで print や他のハンドラーを呼び出すこともできます
        super().emit(record)


def create_logger(level: str = "DEBUG", file: str = None) -> logging.Logger:
    logger = logging.getLogger(__name__)
    logger.propagate = False
    logger.setLevel(level)
    if sum([isinstance(handler, FirestoreHandler) for handler in logger.handlers]) == 0:
        ch = FirestoreHandler()
        logger.addHandler(ch)

    return logger


@st.cache_resource
def get_logger() -> logging.Logger:
    logger = create_logger(level="DEBUG")
    return logger


def st_main() -> None:
    firebase_key_base64 = os.environ.get("FIREBASE_ACCESS_KEY", "")
    import base64

    firebase_key_str = base64.b64decode(firebase_key_base64.encode())

    f = NamedTemporaryFile(delete=False)
    with open("/tmp/firestore-key.json", "wb") as f:
        f.write(firebase_key_str)

    logger = get_logger()
    logger.info("display")

    with streamlit_analytics.track(
        unsafe_password=os.environ.get("ANALYTICS_KEY", ""),
        firestore_key_file="/tmp/firestore-key.json",
        firestore_collection_name="counts",
    ):
        # firesrore保存時に例外になるのでオリジナルの関数に差し替え
        st.number_input = _orig_number_input
        st.text_input = _orig_text_input

        st.markdown("# 見開きPDF分割君")
        st.markdown(version_string)
        st.markdown("見開きでスキャンされたPDFを分割・順番入れ替えし、両面印刷で冊子として印刷できるPDFに変換します。")

        file = st.file_uploader("PDFをアップロードしてください.", type=["pdf"], accept_multiple_files=False)
        max_size_mb = 100

        if file:
            bytes = file.read()
            logger.info(f"filename:{file.name} size:{len(bytes)}")

            if len(bytes) > max_size_mb * 1024 * 1024:
                raise Exception(f"サイズが大きすぎます。{len(bytes)/1024/1024:.2f}MB / {max_size_mb}MB")
            images = load_pdf(bytes)

            with st.expander("詳細設定"):
                st.markdown(f"変換前のPDFイメージ")
                if len(images) <= 8:
                    preview_images(images, 0, len(images))
                else:
                    st.markdown(f"最初の4ページ")
                    preview_images(images, 0, 4)
                    st.markdown(f"最後の4ページ")
                    preview_images(images, len(images) - 4, 4)

                divide_direction = st.radio("どのように分割しますか？", ("自動", "左右に分割", "上下に分割"), horizontal=True)
                add_front_cover = st.checkbox(
                    "表紙を作成してつけますか？", value=True, help="PDFに表紙が含まれている場合は、二重に表紙が作成されてしまうのでチェックを外してください。"
                )
                basename_without_ext = os.path.splitext(os.path.basename(file.name))[0]
                front_cover_string = st.text_input("作成する表紙の文言", basename_without_ext)

                st.markdown("国語の問題のように右側の方が若いページの場合はチェックを入れてください。")
                right_to_left = st.checkbox("ページの左右の順番を逆にする", value=False)

                max_process_num = st.number_input(
                    "変換前のPDFで1ページ目から何ページまでを分割対象としますか？(0は自動判定)", max_value=len(images), value=0, min_value=0
                )

            output_images, processed_num = split_images(
                images,
                divide_direction=str(divide_direction),
                right_to_left=right_to_left,
                max_process_num=int(max_process_num),
                add_front_cover=add_front_cover,
                front_cover_string=front_cover_string,
            )

            st.markdown("変換後のPDFイメージ")

            if processed_num <= 8:
                preview_images(output_images, 0, processed_num)
            else:
                st.markdown("最初の4ページ")
                preview_images(output_images, 0, 4)
                st.markdown("最後の4ページ")
                preview_images(output_images, processed_num - 4, 4)
            if len(output_images) - processed_num > 0:
                st.markdown("未変換ページ")
                preview_images(output_images, processed_num, len(output_images) - processed_num)

            with st.form("my_form"):
                st.markdown("この内容でよければ、PDF生成を押してください。")
                st.markdown("調整が必要な場合は、詳細設定を押してください。")
                submitted = st.form_submit_button("PDF生成")

            converted_name = get_conv_file_name(file.name)
            # PDFを分割
            if submitted:
                with st.spinner(f"{file.name} を変換中"):
                    images_to_pdf(converted_name, images=output_images)

                st.markdown(f"ダウンロード後、両面印刷か2in1で印刷してください。")
                with open(converted_name, "br") as f:
                    st.download_button("ダウンロード", f, converted_name)
                    logger.info({"converted": converted_name})


if __name__ == "__main__":
    st_main()
