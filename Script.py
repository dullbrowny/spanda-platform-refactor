import os
import json
import requests
import io
import base64
import zipfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# Define the scope
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def authenticate_gdrive():
    creds = None
    # Load credentials from file
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no valid credentials, ask the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(
                port=8080
            )  # Ensure the port matches the redirect URI
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    return service


def process_folder(service, folder_id):
    # Modified query to exclude trashed files
    query = f"'{folder_id}' in parents and trashed=false"
    results = (
        service.files()
        .list(q=query, pageSize=1000, fields="files(id, name, mimeType)")
        .execute()
    )
    items = results.get("files", [])

    if not items:
        print("No files found.")
    else:
        print("Files:")
        for item in items:
            print(f'{item["name"]} ({item["id"]})')
            if item["mimeType"] == "application/vnd.google-apps.folder":
                process_folder(service, item["id"])
            else:
                download_and_upload_file(
                    service, item["id"], item["name"], item["mimeType"]
                )


def download_and_upload_file(service, file_id, filename, mime_type):
    try:
        if mime_type.startswith("application/vnd.google-apps."):
            # Check the type of Google Docs file and set the appropriate MIME type
            if mime_type == "application/vnd.google-apps.document":
                export_mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                export_mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif mime_type == "application/vnd.google-apps.presentation":
                export_mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            else:
                print(
                    f"File {filename} with MIME type {mime_type} is not supported for export."
                )
                return

            request = service.files().export_media(
                fileId=file_id, mimeType=export_mime_type
            )
        else:
            # Other files can be downloaded directly
            request = service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")

        fh.seek(0)

        if filename.lower().endswith(".zip"):
            # Handle zip file
            with zipfile.ZipFile(fh, "r") as zip_ref:
                for file_info in zip_ref.infolist():
                    with zip_ref.open(file_info) as extracted_file:
                        process_extracted_file(
                            extracted_file, file_info.filename
                        )
        else:
            # Handle other files
            base64_content = base64.b64encode(fh.read()).decode("utf-8")
            fileData = {
                "filename": filename,
                "extension": filename.split(".").pop().lower(),
                "content": base64_content,
            }

            upload_file(fileData)
    except HttpError as error:
        print(f"An error occurred: {error}")
        print(f"Failed to process file: {filename}")


def process_extracted_file(extracted_file, filename):
    base64_content = base64.b64encode(extracted_file.read()).decode("utf-8")
    fileData = {
        "filename": filename,
        "extension": filename.split(".").pop().lower(),
        "content": base64_content,
    }
    upload_file(fileData)


def upload_file(fileData):
    payload = {
        "data": [fileData],
        "textValues": [],
        "config": {
            "RAG": {
                "Reader": {"selected": "UnstructuredAPI"},
                "Chunker": {"selected": "TokenChunker"},
                "Embedder": {"selected": "MiniLMEmbedder"},
                "Retriever": {"selected": "WindowRetriever"},
                "Generator": {"selected": "Ollama"},
            },
            "SETTING": {"selectedTheme": "defaultTheme"},
        },
    }

    response = requests.post("http://localhost:8000/api/import", json=payload)
    if response.status_code == 200:
        print("File uploaded successfully.")
    else:
        print(
            f"Failed to upload file: {response.status_code} - {response.text}"
        )


if __name__ == "__main__":
    service = authenticate_gdrive()
    folder_id = "1MUGEzJuRBqOVPJmeotnerowNitOPkgfp"
    process_folder(service, folder_id)
