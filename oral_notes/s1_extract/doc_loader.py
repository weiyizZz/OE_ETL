import re
import io
import time
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Read-only access to Google Drive files
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Maps Google Workspace MIME types to (export_mime, file_extension)
# Google Workspace files cannot be downloaded directly — they must be exported to a standard format first
EXPORT_MAP = {
    # Google Sheets → export as CSV
    'application/vnd.google-apps.spreadsheet': ('text/csv', '.csv'),

    # Google Docs → export as Word .docx (preserves structure for python-docx parsing)
    'application/vnd.google-apps.document': (
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'
    ),
}


class GoogleDriveLoader:
    """Loads files from Google Drive into memory using a Service Account."""
    def __init__(self, service_account_file: str):
        """
        Args:
            service_account_file: Path to the service account JSON key file.
        """
        self.service_account_file = service_account_file
        self.service = self._build_service()

    def _build_service(self):
        """Authenticates with the service account and builds the Drive API client."""
        creds = service_account.Credentials.from_service_account_file(
            self.service_account_file, scopes=SCOPES
        )
        return build('drive', 'v3', credentials=creds)

    def _extract_file_id(self, drive_url: str) -> str:
        """Extracts the file ID from various Google Drive URL formats.
        Supports:
            - /document/d/FILE_ID/
            - /spreadsheets/d/FILE_ID/
            - ?id=FILE_ID
            - /d/FILE_ID/
        """
        patterns = [
            r'/document/d/([a-zA-Z0-9_-]+)',
            r'/spreadsheets/d/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'/d/([a-zA-Z0-9_-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, drive_url)
            if match:
                return match.group(1)
        raise ValueError(f"Could not extract file ID from URL: {drive_url}")

    def _get_file_metadata(self, file_id: str) -> dict:
        """Fetches file metadata from Drive (name, MIME type, link, parent folders)."""
        return self.service.files().get(
            fileId=file_id,
            fields='name, mimeType, webViewLink, parents'
        ).execute()

    def _download(self, file_id: str, mime: str) -> io.BytesIO:
        """Downloads or exports the file into a BytesIO buffer.

        Retries up to 3 times on HTTP 500 errors (Google-side transient failures).
        """
        fh = io.BytesIO()
        if mime in EXPORT_MAP:
            export_mime, _ = EXPORT_MAP[mime]
            request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = self.service.files().get_media(fileId=file_id)

        # Retry up to 3 times on transient Google 500 errors
        for attempt in range(3):
            try:
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                return fh
            except HttpError as e:
                if e.resp.status == 500 and attempt < 2:
                    print(f"Google 500 error, retrying in 3 seconds... (attempt {attempt + 1}/3)")
                    time.sleep(3)
                else:
                    raise

    def _resolve_drive_path(self, file_id: str) -> str:
        # Walks up the parent chain to reconstruct the full folder path in Drive.
        parts = []
        current_id = file_id
        while True:
            meta = self.service.files().get(
                fileId=current_id,
                fields='name, parents'
            ).execute()
            parts.append(meta['name'])
            parents = meta.get('parents')
            if not parents:
                break
            current_id = parents[0]
        parts.reverse()
        return "/".join(parts)

    def load(self, drive_url: str) -> dict:
        """Loads a file from a Google Drive URL into memory.
        Args:
            drive_url: Full Google Drive URL of the file.
        Returns:
            dict with keys:
                - fh:         BytesIO buffer of the file content
                - name:       File name with extension
                - mime:       Original MIME type from Drive
                - drive_path: Full folder path in Drive
        """
        file_id = self._extract_file_id(drive_url)
        meta = self._get_file_metadata(file_id)
        name = meta['name']
        mime = meta['mimeType']
        print(f"Loading: {name} ({mime})")

        if mime in EXPORT_MAP:
            _, ext = EXPORT_MAP[mime]
            local_name = name + ext
        else:
            local_name = name

        fh = self._download(file_id, mime)
        drive_path = self._resolve_drive_path(file_id)

        print(f"Drive path: {drive_path}")

        return {
            "fh":         fh,
            "name":       local_name,
            "mime":       mime,
            "drive_path": drive_path,
        }