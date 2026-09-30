import base64
import io
import secrets

import qrcode


def generate_tracking_code(prefix: str = "LAB") -> str:
    """
    Generates a short, human-readable unique tracking string —
    the DATA a QR code encodes, not the image itself.
    Reusable across modules: lab orders, patient wristbands,
    invoice tracking, admission tags, etc. — just vary the prefix.
    """
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def generate_qr_image_bytes(data: str) -> bytes:
    """
    Encodes `data` into a QR code and returns raw PNG bytes.
    Use this when saving the QR image to disk/S3 via app/core/files.
    """
    qr = qrcode.QRCode(
        version=None,          # auto-sizes to fit the data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_qr_data_uri(data: str) -> str:
    png_bytes = generate_qr_image_bytes(data)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"