from __future__ import annotations

import asyncio
import io
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core.exceptions import ConfigurationError
from app.domain.models import SourceDocument

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME = "application/vnd.google-apps.folder"
EXPORT_MIME: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


@dataclass(frozen=True, slots=True)
class SourceChange:
    file_id: str
    removed: bool
    document: SourceDocument | None
    next_page_token: str | None = None
    new_start_page_token: str | None = None


class DocumentSource(Protocol):
    def list_documents(self, *, limit: int | None = None) -> AsyncIterator[SourceDocument]: ...
    async def download(self, document: SourceDocument) -> bytes: ...
    async def get_metadata(self, source_id: str) -> SourceDocument: ...
    async def get_changes(self, page_token: str) -> tuple[list[SourceChange], str]: ...


class GoogleDriveDocumentSource:
    def __init__(self, service: Any, *, root_folder_id: str) -> None:
        if not root_folder_id:
            raise ConfigurationError("GOOGLE_DRIVE_ROOT_FOLDER_ID is required")
        self.service = service
        self.root_folder_id = root_folder_id

    @classmethod
    def from_service_account(
        cls, credential_file: str, *, root_folder_id: str
    ) -> GoogleDriveDocumentSource:
        credential_path = Path(credential_file).expanduser().resolve()
        if not credential_path.is_file():
            raise ConfigurationError(
                "Google service-account credentials not found: "
                f"{credential_path}. For a local run, put the downloaded JSON at "
                "credentials/google-service-account.json and set "
                "GOOGLE_SERVICE_ACCOUNT_FILE=credentials/google-service-account.json. "
                "Docker Compose maps that directory to /run/secrets."
            )
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            str(credential_path), scopes=[DRIVE_SCOPE]
        )
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return cls(service, root_folder_id=root_folder_id)

    @classmethod
    def from_oauth2(
        cls,
        client_file: str,
        token_file: str,
        *,
        root_folder_id: str,
    ) -> GoogleDriveDocumentSource:
        client_path = Path(client_file).expanduser().resolve()
        token_path = Path(token_file).expanduser().resolve()
        credentials: OAuthCredentials | None = None

        if token_path.is_file():
            credentials = OAuthCredentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                str(token_path),
                scopes=[DRIVE_SCOPE],
            )

        if credentials is None or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())  # type: ignore[no-untyped-call]
            else:
                if not client_path.is_file():
                    raise ConfigurationError(
                        "Google OAuth desktop client credentials not found: "
                        f"{client_path}. Download the Desktop app OAuth JSON from "
                        "Google Auth Platform > Clients and save it as "
                        "credentials/google-oauth-client.json."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_path),
                    scopes=[DRIVE_SCOPE],
                )
                credentials = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(credentials.to_json(), encoding="utf-8")

        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        return cls(service, root_folder_id=root_folder_id)

    async def list_documents(self, *, limit: int | None = None) -> AsyncIterator[SourceDocument]:
        queue: deque[tuple[str, PurePosixPath]] = deque([(self.root_folder_id, PurePosixPath())])
        yielded = 0
        while queue:
            folder_id, logical_path = queue.popleft()
            items = await asyncio.to_thread(self._list_children, folder_id)
            for item in items:
                item_path = logical_path / item["name"]
                if item["mimeType"] == FOLDER_MIME:
                    queue.append((item["id"], item_path))
                    continue
                yield self._to_document(item, str(item_path.parent))
                yielded += 1
                if limit is not None and yielded >= limit:
                    return

    async def download(self, document: SourceDocument) -> bytes:
        return await asyncio.to_thread(self._download, document)

    async def get_metadata(self, source_id: str) -> SourceDocument:
        item = await asyncio.to_thread(
            lambda: (
                self.service.files()
                .get(fileId=source_id, fields=self._fields(), supportsAllDrives=True)
                .execute()
            )
        )
        return self._to_document(item, "")

    async def get_start_page_token(self) -> str:
        response = await asyncio.to_thread(
            lambda: self.service.changes().getStartPageToken(supportsAllDrives=True).execute()
        )
        return str(response["startPageToken"])

    async def get_changes(self, page_token: str) -> tuple[list[SourceChange], str]:
        changes: list[SourceChange] = []
        current_token: str | None = page_token
        final_token = page_token
        while current_token:
            response = await asyncio.to_thread(self._list_changes, current_token)
            for raw in response.get("changes", []):
                removed = bool(raw.get("removed", False))
                item = raw.get("file")
                document = None if removed or item is None else self._to_document(item, "")
                changes.append(SourceChange(raw["fileId"], removed, document))
            current_token = response.get("nextPageToken")
            final_token = response.get("newStartPageToken", final_token)
        return changes, final_token

    def _list_children(self, folder_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields=f"nextPageToken, files({self._fields()})",
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            result.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return result

    def _download(self, document: SourceDocument) -> bytes:
        source_mime_type = document.source_mime_type or document.mime_type
        if source_mime_type in EXPORT_MIME:
            export_mime, _ = EXPORT_MIME[source_mime_type]
            request = self.service.files().export_media(
                fileId=document.source_id, mimeType=export_mime
            )
        else:
            request = self.service.files().get_media(
                fileId=document.source_id, supportsAllDrives=True
            )
        output = io.BytesIO()
        downloader = MediaIoBaseDownload(output, request, chunksize=4 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return output.getvalue()

    def _list_changes(self, page_token: str) -> dict[str, Any]:
        response = (
            self.service.changes()
            .list(
                pageToken=page_token,
                fields=f"nextPageToken,newStartPageToken,changes(fileId,removed,file({self._fields()}))",
                includeRemoved=True,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return cast(dict[str, Any], response)

    @staticmethod
    def _fields() -> str:
        return (
            "id,name,mimeType,size,modifiedTime,createdTime,md5Checksum,webViewLink,parents,trashed"
        )

    @staticmethod
    def _to_document(item: dict[str, Any], folder_path: str) -> SourceDocument:
        mime_type = str(item["mimeType"])
        name = str(item["name"])
        if mime_type in EXPORT_MIME and not name.lower().endswith(EXPORT_MIME[mime_type][1]):
            name += EXPORT_MIME[mime_type][1]
        effective_mime = EXPORT_MIME.get(mime_type, (mime_type, ""))[0]
        modified = item.get("modifiedTime")
        return SourceDocument(
            source_id=str(item["id"]),
            name=name,
            mime_type=effective_mime,
            source_mime_type=mime_type,
            folder_path=folder_path.strip("/"),
            size=int(item["size"]) if item.get("size") else None,
            modified_time=datetime.fromisoformat(modified.replace("Z", "+00:00"))
            if modified
            else None,
            checksum=item.get("md5Checksum"),
            web_url=item.get("webViewLink"),
            parent_ids=[str(value) for value in item.get("parents", [])],
        )
