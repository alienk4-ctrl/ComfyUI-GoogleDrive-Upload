import base64
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Tuple

from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_secret():
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

    raise ValueError("Secret GDRIVE_TOKEN_JSON não encontrado.")


def _parse_secret(raw):
    if isinstance(raw, dict):
        return raw

    raw = str(raw).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(
                base64.b64decode(raw, validate=True).decode("utf-8")
            )
        except Exception as exc:
            raise ValueError("Secret não contém JSON válido.") from exc

    if not isinstance(data, dict):
        raise ValueError("O secret deve conter um objeto JSON.")

    return data


def _build_credentials(data):
    if data.get("type") == "service_account" or (
        data.get("client_email") and data.get("private_key")
    ):
        return service_account.Credentials.from_service_account_info(
            data, scopes=SCOPES
        )

    token = data.get("token") or data.get("access_token")
    refresh_token = data.get("refresh_token")

    if refresh_token:
        if not data.get("client_id") or not data.get("client_secret"):
            raise ValueError(
                "OAuth requer client_id e client_secret."
            )

        credentials = OAuthCredentials(
            token=token,
            refresh_token=refresh_token,
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

    if token:
        return OAuthCredentials(
            token=token,
            token_uri=data.get(
                "token_uri", "https://oauth2.googleapis.com/token"
            ),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=SCOPES,
        )

    raise ValueError("Credenciais OAuth ou Service Account inválidas.")


def _clean_folder_id(value):
    value = (value or "").strip()

    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    if match:
        return match.group(1)

    value = value.split("?", 1)[0].rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]

    if not value:
        raise ValueError("Informe o ID ou a URL da pasta do Drive.")

    return value


def _safe_filename(value):
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value or "")
    return (value.strip(" .") or "comfyui_video")[:150]


class GoogleDriveVideoUpload:
    """
    Faz upload de um vídeo existente no ComfyUI/VHS para o Google Drive.
    O arquivo é transmitido em blocos, sem criar uma cópia temporária.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "Caminho completo do vídeo",
                    },
                ),
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
                    {"default": "comfyui_video", "multiline": False},
                ),
                "add_timestamp": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "chunk_size_mb": (
                    "INT",
                    {"default": 8, "min": 1, "max": 64, "step": 1},
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("status", "file_url")
    FUNCTION = "upload_to_drive"
    CATEGORY = "video/output"
    OUTPUT_NODE = True

    def upload_to_drive(
        self,
        video_path,
        folder_id,
        filename_prefix="comfyui_video",
        add_timestamp=True,
        chunk_size_mb=8,
    ) -> Tuple[str, str]:

        try:
            # O caminho deve apontar para o arquivo produzido pelo VHS.
            path = Path(video_path.strip()).expanduser()

            if not path.is_file():
                raise FileNotFoundError(
                    "Vídeo não encontrado. Informe o caminho completo "
                    "do arquivo gerado pelo VHS_VideoCombine."
                )

            extension = path.suffix.lower()
            mime_types = {
                ".mp4": "video/mp4",
                ".webm": "video/webm",
                ".mov": "video/quicktime",
                ".mkv": "video/x-matroska",
                ".avi": "video/x-msvideo",
                ".gif": "image/gif",
            }

            mime_type = mime_types.get(extension)
            if not mime_type:
                raise ValueError(
                    f"Formato de vídeo não suportado: {extension}"
                )

            folder_id = _clean_folder_id(folder_id)
            secret_data = _parse_secret(_get_secret())
            credentials = _build_credentials(secret_data)

            service = build(
                "drive",
                "v3",
                credentials=credentials,
                cache_discovery=False,
            )

            prefix = _safe_filename(filename_prefix)
            timestamp = (
                "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                if add_timestamp else ""
            )

            filename = f"{prefix}{timestamp}{extension}"

            metadata = {
                "name": filename,
                "parents": [folder_id],
                "mimeType": mime_type,
            }

            # Upload em blocos diretamente do arquivo original.
            # Não lê o vídeo inteiro para a RAM nem cria outra cópia.
            media = MediaFileUpload(
                str(path),
                mimetype=mime_type,
                chunksize=chunk_size_mb * 1024 * 1024,
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

            return (
                f"Sucesso: vídeo enviado ao Google Drive: "
                f"{result.get('name', filename)}",
                file_url,
            )

        except Exception as exc:
            # Evita expor valores de credenciais em mensagens de erro.
            message = str(exc)

            for key in (
                "refresh_token",
                "client_secret",
                "private_key",
                "access_token",
            ):
                message = re.sub(
                    rf"(?i){key}\s*[:=]\s*[^,\s}}]+",
                    f"{key}=[REDACTED]",
                    message,
                )

            return (
                f"Erro no upload para o Google Drive: {message}",
                "",
            )


NODE_CLASS_MAPPINGS = {
    "GoogleDriveVideoUpload": GoogleDriveVideoUpload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoogleDriveVideoUpload": "Upload Video to Google Drive",
}
