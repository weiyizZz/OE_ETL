import re
import io
from docx import Document
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = "../config/service_account_key.json"

def extract_file_id(drive_url: str) -> str:
    """Extract file ID from various Google Drive URL formats."""
    patterns = [
        r'/document/d/([a-zA-Z0-9_-]+)',   # /document/d/FILE_ID/view
        r'/spreadsheets/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',          # ?id=FILE_ID
        r'/d/([a-zA-Z0-9_-]+)',          # /d/FILE_ID/
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract file ID from URL: {drive_url}")

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def load_file_from_url(drive_url: str):
    """Load a file from a Google Drive URL into memory."""
    service = get_drive_service()
    file_id = extract_file_id(drive_url)

    # Get file metadata to know the type
    meta = service.files().get(fileId=file_id, fields='name, mimeType').execute()
    name = meta['name']
    mime = meta['mimeType']
    print(f"Loading: {name} ({mime})")

    # Google Workspace files (Sheets, Docs) need export instead of direct download
    EXPORT_MAP = {
        'application/vnd.google-apps.spreadsheet': ('text/csv', '.csv'),
        'application/vnd.google-apps.document': (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'
        ),
    }

    fh = io.BytesIO()
    if mime in EXPORT_MAP:
        export_mime, _ = EXPORT_MAP[mime]
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    fh.seek(0)
    return fh, name

# --- Usage ---
url = "https://docs.google.com/document/d/1jgVRKPK4bEfU0ARhlYNbiMmDTszwjBQloOhjBUWmJwI/edit?tab=t.0"
fh, name = load_file_from_url(url)

doc = Document(fh)
for paragraph in doc.paragraphs:
    print(paragraph.text)