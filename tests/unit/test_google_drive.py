from pathlib import Path
from typing import Any

import pytest

from app.core.exceptions import ConfigurationError
from app.domain.models import SourceDocument
from app.integrations.google_drive import GoogleDriveDocumentSource


def test_missing_service_account_file_has_actionable_error(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing-service-account.json"

    with pytest.raises(
        ConfigurationError,
        match=r"GOOGLE_SERVICE_ACCOUNT_FILE=credentials/google-service-account\.json",
    ):
        GoogleDriveDocumentSource.from_service_account(
            str(missing_file),
            root_folder_id="test-folder",
        )


def test_missing_oauth_client_file_has_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(
        ConfigurationError,
        match=r"Google Auth Platform > Clients",
    ):
        GoogleDriveDocumentSource.from_oauth2(
            str(tmp_path / "missing-client.json"),
            str(tmp_path / "missing-token.json"),
            root_folder_id="test-folder",
        )


def test_oauth_browser_flow_persists_refreshable_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_file = tmp_path / "client.json"
    token_file = tmp_path / "token.json"
    client_file.write_text("{}", encoding="utf-8")

    class FakeCredentials:
        valid = False
        expired = False
        refresh_token = None

        def to_json(self) -> str:
            return '{"refresh_token":"stored-locally"}'

    class FakeFlow:
        @classmethod
        def from_client_secrets_file(cls, *_args: Any, **_kwargs: Any) -> Any:
            return cls()

        def run_local_server(self, *, port: int) -> FakeCredentials:
            assert port == 0
            return FakeCredentials()

    monkeypatch.setattr("app.integrations.google_drive.InstalledAppFlow", FakeFlow)
    monkeypatch.setattr("app.integrations.google_drive.build", lambda *_args, **_kwargs: object())

    GoogleDriveDocumentSource.from_oauth2(
        str(client_file),
        str(token_file),
        root_folder_id="test-folder",
    )

    assert token_file.read_text(encoding="utf-8") == '{"refresh_token":"stored-locally"}'


async def test_native_google_sheet_uses_export_media(monkeypatch: pytest.MonkeyPatch) -> None:
    export_calls: list[dict[str, object]] = []

    class FakeFiles:
        def export_media(self, **kwargs: object) -> object:
            export_calls.append(kwargs)
            return object()

        def get_media(self, **_kwargs: object) -> object:
            raise AssertionError("Native Google files must use export_media")

    class FakeService:
        def files(self) -> FakeFiles:
            return FakeFiles()

    class FakeDownloader:
        def __init__(self, output: Any, _request: object, *, chunksize: int) -> None:
            assert chunksize == 4 * 1024 * 1024
            output.write(b"exported-sheet")

        def next_chunk(self) -> tuple[None, bool]:
            return None, True

    monkeypatch.setattr("app.integrations.google_drive.MediaIoBaseDownload", FakeDownloader)
    source = GoogleDriveDocumentSource(FakeService(), root_folder_id="root")
    document = SourceDocument(
        source_id="sheet-id",
        name="report.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        source_mime_type="application/vnd.google-apps.spreadsheet",
        folder_path="",
    )

    content = await source.download(document)

    assert content == b"exported-sheet"
    assert export_calls == [
        {
            "fileId": "sheet-id",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    ]
