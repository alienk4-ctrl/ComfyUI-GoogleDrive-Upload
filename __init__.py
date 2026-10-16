
from .google_drive_upload import GoogleDriveUpload
from .google_drive_video_upload import GoogleDriveVideoUpload

NODE_CLASS_MAPPINGS = {
    "GoogleDriveUpload": GoogleDriveUpload,
    "GoogleDriveVideoUpload": GoogleDriveVideoUpload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoogleDriveUpload": "Upload Image to Google Drive",
    "GoogleDriveVideoUpload": "Upload Video to Google Drive",
}

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
]
