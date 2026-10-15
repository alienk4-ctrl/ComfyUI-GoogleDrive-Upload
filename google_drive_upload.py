import io
import json
import os
import re
from datetime import datetime
from typing import Tuple

import numpy as np
from PIL import Image

from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_kaggle_secret():
    """Obtém GDRIVE_TOKEN_JSON sem imprimir nem persistir o segredo."""
    value = os.environ.get("GDRIVE_TOKEN_JSON", "").strip()
    if value:
        return value

    try:
        from kaggle_secrets import UserSecretsClient

        value = UserSecretsClient().get_secret("GDRIVE_TOKEN_JSON")
        if value and value.strip():
            return value.strip()
    except Exception:
        pass

    raise ValueError(
        "Secret GDRIVE_TOKEN_JSON não encontrado. "
        "Configure-o em Kaggle > Add-ons > Secrets."
    )


def _parse_json_secret(raw):
    """Aceita JSON puro ou JSON codificado em Base64."""
    import base64

    if isinstance(raw, dict):
        return raw

    raw = str(raw).strip()
    if not raw:
        raise ValueError("GDRIVE_TOKEN_JSON está vazio.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8")
            data = json.loads(decoded)
        except Exception as exc:
            raise ValueError(
                "GDRIVE_TOKEN_JSON não contém JSON válido "
                "nem JSON válido codificado em Base64."
            ) from exc

    if not isinstance(data, dict):
        raise ValueError("O conteúdo do secret deve ser um objeto JSON.")

    return data


def _build_credentials(data):
    """Cria credenciais OAuth ou Service Account sem arquivos locais."""
    account_type = data.get("type", "")

    if account_type == "service_account" or (
        data.get("client_email") and data.get("private_key")
    ):
        credentials = service_account.Credentials.from_service_account_info(
            data,
            scopes=SCOPES,
        )
        return credentials

    # OAuth: suporta JSON de token.json e authorized_user.
    if not data.get("refresh_token"):
        # Um access token sozinho só funciona enquanto estiver válido.
        access_token = data.get("token") or data.get("access_token")
        if access_token:
            return OAuthCredentials(
                token=access_token,
                scopes=SCOPES,
                token_uri=data.get(
                    "token_uri", "https://oauth2.googleapis.com/token"
                ),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
            )

        raise ValueError(
            "O JSON não é uma Service Account e não contém refresh_token "
            "nem token de acesso."
        )

    if not data.get("client_id") or not data.get("client_secret"):
        raise ValueError(
            "Para OAuth com refresh_token, o JSON precisa conter "
            "client_id e client_secret."
        )

    credentials = OAuthCredentials(
        token=data.get("token") or data.get("access_token"),
        refresh_token=data["refresh_token"],
        token_uri=data.get(
            "token_uri", "https://oauth2.googleapis.com/token"
        ),
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data.get("scopes") or SCOPES,
    )

    if not credentials.valid:
        credentials.refresh(Request())

    return credentials


def _clean_folder_id(value):
    """Aceita tanto o ID quanto a URL de uma pasta do Drive."""
    value = (value or "").strip()

    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    if match:
        return match.group(1)

    value = value.split("?", 1)[0].rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]

    if not value:
        raise ValueError("Informe o ID ou a URL da pasta do Google Drive.")

    return value


def _safe_filename(value):
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value or "")
    value = value.strip(" .")
    return (value or "comfyui_output")[:150]


def _tensor_to_pil(tensor):
    """Converte um item IMAGE do ComfyUI em PIL, sem salvar em disco."""
    if hasattr(tensor, "detach"):
        tensor = tensor.detach()

    if hasattr(tensor, "cpu"):
        tensor = tensor.cpu()

    array = np.asarray(tensor, dtype=np.float32)
    array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    array = (np.clip(array, 0.0, 1.0) * 255.0).round().astype(np.uint8)

    if array.ndim == 2:
        return Image.fromarray(array, mode="L")

    if array.ndim != 3:
        raise ValueError("Formato de imagem inesperado no tensor.")

    channels = array.shape[-1]

    if channels == 1:
        return Image.fromarray(array[:, :, 0], mode="L")
    if channels == 3:
        return Image.fromarray(array, mode="RGB")
    if channels == 4:
        return Image.fromarray(array, mode="RGBA")

    raise ValueError(f"Número de canais não suportado: {channels}")


def _encode_image(pil_image, image_format, quality):
    """Codifica a imagem em RAM e retorna buffer e MIME type."""
    fmt = image_format.upper()
    buffer = io.BytesIO()

    if fmt == "JPEG":
        if pil_image.mode in ("RGBA", "LA"):
            rgba = pil_image.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            pil_image = background
        elif pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        pil_image.save(buffer, format="JPEG", quality=int(quality))
        mime_type, extension = "image/jpeg", "jpg"

    elif fmt == "PNG":
        pil_image.save(buffer, format="PNG")
        mime_type, extension = "image/png", "png"

    elif fmt == "WEBP":
        pil_image.save(buffer, format="WEBP", quality=int(quality))
        mime_type, extension = "image/webp", "webp"

    else:
        raise ValueError(f"Formato não suportado: {image_format}")

    buffer.seek(0)
    return buffer, mime_type, extension


class GoogleDriveUpload:
    """Envia imagens do ComfyUI diretamente para o Google Drive."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "folder_id": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "ID ou URL da pasta do Drive",
                    },
                ),
                "filename_prefix": (
                    "STRING",
                    {"default": "comfyui_output", "multiline": False},
                ),
                "image_format": (["PNG", "JPEG", "WEBP"],),
                "jpeg_quality": (
                    "INT",
                    {"default": 95, "min": 1, "max": 100, "step": 1},
                ),
                "add_timestamp": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("status", "file_url")
    FUNCTION = "upload_to_drive"
    CATEGORY = "image/output"
    OUTPUT_NODE = True

    def upload_to_drive(
        self,
        image,
        folder_id,
        filename_prefix="comfyui_output",
        image_format="PNG",
        jpeg_quality=95,
        add_timestamp=True,
    ) -> Tuple[str, str]:
        buffers = []

        try:
            folder_id = _clean_folder_id(folder_id)

            raw_secret = _get_kaggle_secret()
            secret_data = _parse_json_secret(raw_secret)
            credentials = _build_credentials(secret_data)

            service = build(
                "drive",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )

            prefix = _safe_filename(filename_prefix)
            timestamp = (
                datetime.now().strftime("%Y%m%d_%H%M%S")
                if add_timestamp
                else ""
            )

            # IMAGE no ComfyUI normalmente possui formato B x H x W x C.
            if len(image.shape) == 3:
                batch = [image]
            else:
                batch = [image[index] for index in range(image.shape[0])]

            if not batch:
                raise ValueError("O lote de imagens está vazio.")

            uploaded_urls = []
            uploaded_names = []

            for index, tensor in enumerate(batch):
                pil_image = _tensor_to_pil(tensor)
                buffer, mime_type, extension = _encode_image(
                    pil_image, image_format, jpeg_quality
                )
                buffers.append(buffer)

                suffix = f"_{timestamp}" if timestamp else ""
                if len(batch) > 1:
                    suffix += f"_{index + 1:03d}"

                filename = f"{prefix}{suffix}.{extension}"

                metadata = {
                    "name": filename,
                    "parents": [folder_id],
                    "mimeType": mime_type,
                }

                # O upload consome BytesIO: nenhuma imagem é gravada em disco.
                media = MediaIoBaseUpload(
                    buffer,
                    mimetype=mime_type,
                    resumable=True,
                )

                result = (
                    service.files()
                    .create(
                        body=metadata,
                        media_body=media,
                        fields="id,name,webViewLink",
                    )
                    .execute()
                )

                file_id = result.get("id", "")
                file_url = result.get("webViewLink") or (
                    f"https://drive.google.com/file/d/{file_id}/view"
                )

                uploaded_names.append(result.get("name", filename))
                uploaded_urls.append(file_url)

            status = (
                f"Sucesso: {len(uploaded_names)} imagem(ns) enviada(s) "
                "ao Google Drive."
            )
            return status, "\n".join(uploaded_urls)

        except Exception as exc:
            # Não registrar credenciais ou o conteúdo do secret.
            message = str(exc)
            for sensitive_key in (
                "refresh_token",
                "client_secret",
                "private_key",
                "access_token",
            ):
                message = re.sub(
                    rf"(?i){sensitive_key}\s*[:=]\s*[^,\s}}]+",
                    f"{sensitive_key}=[REDACTED]",
                    message,
                )
            return f"Erro no upload para o Google Drive: {message}", ""

        finally:
            for buffer in buffers:
                try:
                    buffer.close()
                except Exception:
                    pass


NODE_CLASS_MAPPINGS = {
    "GoogleDriveUpload": GoogleDriveUpload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoogleDriveUpload": "Upload to Google Drive (Kaggle)",
}
