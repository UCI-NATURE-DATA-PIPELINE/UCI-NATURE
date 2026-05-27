from __future__ import annotations

import threading
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui.backend.services import drive_staging_service as service


class _FakeExecute:
    def __init__(self, payload: dict):
        self.payload = payload

    def execute(self) -> dict:
        return self.payload


class _FakeChanges:
    def __init__(self, *, page_token: str = "token-1", changes_payload: dict | None = None):
        self.page_token = page_token
        self.changes_payload = changes_payload or {
            "changes": [],
            "newStartPageToken": "token-2",
        }

    def getStartPageToken(self, **_kwargs):
        return _FakeExecute({"startPageToken": self.page_token})

    def list(self, **_kwargs):
        return _FakeExecute(self.changes_payload)


class _FakeDriveService:
    def __init__(self, *, page_token: str = "token-1", changes_payload: dict | None = None):
        self._changes = _FakeChanges(page_token=page_token, changes_payload=changes_payload)

    def changes(self):
        return self._changes


def _file_info(file_id: str, name: str, folder_id: str = "folder-root") -> dict[str, object]:
    return {
        "file_id": file_id,
        "file_name": name,
        "drive_folder_id": folder_id,
        "mimeType": "image/jpeg",
        "modifiedTime": "2026-05-27T00:00:00.000Z",
        "size": "10",
        "drive_path": name,
        "relative_local_path": Path(f"{file_id}__{name}"),
    }


class DriveStagingServiceTests(unittest.TestCase):
    def test_download_workers_start_before_recursive_listing_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            download_started = threading.Event()

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None):
                if seen_folders is not None:
                    seen_folders.add("folder-root")
                yield _file_info("file-1", "one.jpg")
                self.assertTrue(
                    download_started.wait(timeout=2),
                    "first download did not start while listing was still running",
                )
                yield _file_info("file-2", "two.jpg")

            def fake_download(_drive_service, _file_id, out_path: Path):
                download_started.set()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"image")

            with (
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService()),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=fake_iter),
                mock.patch.object(service, "_download_file", side_effect=fake_download),
            ):
                result = service.stage_selected_drive_folder(
                    access_token="access-token",
                    refresh_token=None,
                    folder_id="folder-root",
                    folder_name="Camera Folder",
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                    max_files=None,
                )

            self.assertEqual(result["available_count"], 2)
            self.assertEqual(result["downloaded_count"], 2)
            self.assertEqual(result["newly_downloaded_count"], 2)

    def test_cached_drive_index_skips_recursive_listing_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            files = [_file_info("file-1", "one.jpg"), _file_info("file-2", "two.jpg")]

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None):
                if seen_folders is not None:
                    seen_folders.add("folder-root")
                yield from files

            def fake_download(_drive_service, _file_id, out_path: Path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"image")

            common_patches = [
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_download_file", side_effect=fake_download),
            ]

            with (
                common_patches[0],
                common_patches[1],
                common_patches[2],
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService(page_token="token-1")),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=fake_iter) as first_listing,
            ):
                first_result = service.stage_selected_drive_folder(
                    access_token="access-token",
                    refresh_token=None,
                    folder_id="folder-root",
                    folder_name="Camera Folder",
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                    max_files=None,
                )

            self.assertEqual(first_result["downloaded_count"], 2)
            self.assertTrue(first_listing.called)

            with (
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService(page_token="token-2")),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_download_file", side_effect=AssertionError("download should be skipped")),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=AssertionError("listing should be cached")),
            ):
                second_result = service.stage_selected_drive_folder(
                    access_token="access-token",
                    refresh_token=None,
                    folder_id="folder-root",
                    folder_name="Camera Folder",
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                    max_files=None,
                )

            self.assertEqual(second_result["downloaded_count"], 2)
            self.assertEqual(second_result["newly_downloaded_count"], 0)
            self.assertEqual(second_result["already_staged_count"], 2)


if __name__ == "__main__":
    unittest.main()
