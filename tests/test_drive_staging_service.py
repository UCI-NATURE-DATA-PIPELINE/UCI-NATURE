from __future__ import annotations

import json
import threading
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui.backend.auth import routes_drive
from ui.backend.cancellation import CancellationToken, OperationCancelled
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
    def __init__(
        self,
        *,
        page_token: str = "token-1",
        changes_payload: dict | None = None,
        metadata_by_id: dict[str, dict] | None = None,
        children_by_folder: dict[str, list[dict]] | None = None,
    ):
        self._changes = _FakeChanges(page_token=page_token, changes_payload=changes_payload)
        self._files = _FakeFiles(
            metadata_by_id=metadata_by_id or {},
            children_by_folder=children_by_folder or {},
        )

    def changes(self):
        return self._changes

    def files(self):
        return self._files


class _FakeFiles:
    def __init__(
        self,
        *,
        metadata_by_id: dict[str, dict],
        children_by_folder: dict[str, list[dict]],
    ):
        self.metadata_by_id = metadata_by_id
        self.children_by_folder = children_by_folder
        self.get_calls: list[str] = []
        self.list_calls: list[str] = []

    def get(self, *, fileId: str, **_kwargs):
        self.get_calls.append(fileId)
        return _FakeExecute(self.metadata_by_id[fileId])

    def list(self, *, q: str, **_kwargs):
        folder_id = q.split("'", 2)[1]
        self.list_calls.append(folder_id)
        return _FakeExecute({"files": self.children_by_folder.get(folder_id, [])})


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


def _resolved_folder(folder_id: str = "folder-root") -> dict[str, object]:
    return {
        "selected_id": folder_id,
        "selected_name": "Camera Folder",
        "selected_mime_type": service.FOLDER_MIME_TYPE,
        "shortcut_target_id": None,
        "resolved_id": folder_id,
        "resolved_name": "Camera Folder",
        "resolved_mime_type": service.FOLDER_MIME_TYPE,
    }


class DriveStagingServiceTests(unittest.TestCase):
    def tearDown(self) -> None:
        routes_drive.DRIVE_SYNC_STATES.clear()
        routes_drive.DRIVE_SYNC_CANCEL_TOKENS.clear()

    def test_download_workers_start_before_recursive_listing_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            download_started = threading.Event()

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None, stats=None):
                if seen_folders is not None:
                    self.assertNotIn("folder-root", seen_folders)
                    seen_folders.add("folder-root")
                if stats is not None:
                    stats["folders_scanned"] = 1
                    stats["files_scanned"] = 2
                    stats["images_discovered"] = 2
                    stats["first_image_names"] = ["one.jpg", "two.jpg"]
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
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
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

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None, stats=None):
                if seen_folders is not None:
                    self.assertNotIn("folder-root", seen_folders)
                    seen_folders.add("folder-root")
                if stats is not None:
                    stats["folders_scanned"] = 1
                    stats["files_scanned"] = len(files)
                    stats["images_discovered"] = len(files)
                    stats["first_image_names"] = [str(item["file_name"]) for item in files]
                yield from files

            def fake_download(_drive_service, _file_id, out_path: Path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"image")

            common_patches = [
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
                mock.patch.object(service, "_download_file", side_effect=fake_download),
            ]

            with (
                common_patches[0],
                common_patches[1],
                common_patches[2],
                common_patches[3],
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
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
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

    def test_sync_limit_prunes_existing_staged_files_beyond_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            files = [
                _file_info("file-1", "one.jpg"),
                _file_info("file-2", "two.jpg"),
                _file_info("file-3", "three.jpg"),
            ]

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None, stats=None):
                if seen_folders is not None:
                    seen_folders.add("folder-root")
                if stats is not None:
                    stats["folders_scanned"] = 1
                    stats["files_scanned"] = len(files)
                    stats["images_discovered"] = len(files)
                    stats["first_image_names"] = [str(item["file_name"]) for item in files]
                yield from files

            def fake_download(_drive_service, _file_id, out_path: Path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"image")

            with (
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService(page_token="token-1")),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=fake_iter),
                mock.patch.object(service, "_download_file", side_effect=fake_download),
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

            self.assertEqual(first_result["downloaded_count"], 3)
            self.assertTrue((tmp_path / "data" / "staging" / "file-3__three.jpg").exists())

            with (
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService(page_token="token-2")),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
                mock.patch.object(service, "_download_file", side_effect=AssertionError("download should be skipped")),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=AssertionError("listing should be cached")),
            ):
                limited_result = service.stage_selected_drive_folder(
                    access_token="access-token",
                    refresh_token=None,
                    folder_id="folder-root",
                    folder_name="Camera Folder",
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                    max_files=2,
                )

            self.assertEqual(limited_result["available_count"], 3)
            self.assertEqual(limited_result["downloaded_count"], 2)
            self.assertEqual(limited_result["already_staged_count"], 2)
            self.assertFalse((tmp_path / "data" / "staging" / "file-3__three.jpg").exists())
            index_rows = service._read_drive_index(tmp_path / "data" / "outputs" / "drive_index.csv")
            self.assertEqual([row["file_name"] for row in index_rows], ["one.jpg", "two.jpg"])

    def test_shortcut_folder_resolves_to_target_folder(self) -> None:
        drive_service = _FakeDriveService(
            metadata_by_id={
                "shortcut-id": {
                    "id": "shortcut-id",
                    "name": "Bonita Canyon1",
                    "mimeType": service.SHORTCUT_MIME_TYPE,
                    "shortcutDetails": {
                        "targetId": "target-folder-id",
                        "targetMimeType": service.FOLDER_MIME_TYPE,
                    },
                },
                "target-folder-id": {
                    "id": "target-folder-id",
                    "name": "Bonita Canyon Target",
                    "mimeType": service.FOLDER_MIME_TYPE,
                },
            },
        )

        resolved = service._resolve_selected_drive_folder(
            drive_service,
            "shortcut-id",
            folder_name="Bonita Canyon1",
        )

        self.assertEqual(resolved["selected_mime_type"], service.SHORTCUT_MIME_TYPE)
        self.assertEqual(resolved["shortcut_target_id"], "target-folder-id")
        self.assertEqual(resolved["resolved_id"], "target-folder-id")
        self.assertEqual(resolved["resolved_mime_type"], service.FOLDER_MIME_TYPE)

    def test_uppercase_jpg_detection(self) -> None:
        self.assertTrue(service._is_supported_image("IMG_0001.JPG", "application/octet-stream"))
        self.assertTrue(service._is_supported_image("camera-without-extension", "image/jpeg"))

    def test_nested_folder_image_discovery(self) -> None:
        drive_service = _FakeDriveService(
            children_by_folder={
                "folder-root": [
                    {
                        "id": "nested-folder",
                        "name": "Nested",
                        "mimeType": service.FOLDER_MIME_TYPE,
                    },
                ],
                "nested-folder": [
                    {
                        "id": "image-1",
                        "name": "TrailCam.JPG",
                        "mimeType": "application/octet-stream",
                        "modifiedTime": "2026-05-27T00:00:00.000Z",
                        "size": "10",
                    },
                ],
            },
        )
        seen_folders: set[str] = set()
        stats = service._new_drive_listing_stats()

        files = list(
            service._iter_selected_folder_images(
                drive_service,
                "folder-root",
                seen_folders=seen_folders,
                stats=stats,
            )
        )

        self.assertEqual([item["file_name"] for item in files], ["TrailCam.JPG"])
        self.assertEqual(files[0]["drive_path"], "Nested/TrailCam.JPG")
        self.assertEqual(seen_folders, {"folder-root", "nested-folder"})
        self.assertEqual(stats["folders_scanned"], 2)
        self.assertEqual(stats["images_discovered"], 1)
        self.assertEqual(stats["first_image_names"], ["TrailCam.JPG"])

    def test_zero_image_cache_falls_back_to_live_listing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            outputs_dir = tmp_path / "data" / "outputs"
            outputs_dir.mkdir(parents=True)
            cache_index_path = outputs_dir / service.DRIVE_INDEX_CACHE_CSV_NAME
            cache_manifest_path = outputs_dir / service.DRIVE_INDEX_CACHE_MANIFEST_NAME
            cache_index_path.write_text(",".join(service.DRIVE_INDEX_FIELDS) + "\n", encoding="utf-8")
            cache_manifest_path.write_text(
                json.dumps(
                    {
                        "version": service.DRIVE_INDEX_CACHE_VERSION,
                        "folder_id": "folder-root",
                        "folder_ids": ["folder-root"],
                        "start_page_token": "token-1",
                        "file_count": 0,
                    }
                ),
                encoding="utf-8",
            )
            live_files = [_file_info("file-live", "live.JPG")]

            def fake_iter(_drive_service, _folder_id, *, seen_folders=None, stats=None):
                if seen_folders is not None:
                    self.assertNotIn("folder-root", seen_folders)
                    seen_folders.add("folder-root")
                if stats is not None:
                    stats["folders_scanned"] = 1
                    stats["files_scanned"] = 1
                    stats["images_discovered"] = 1
                    stats["first_image_names"] = ["live.JPG"]
                yield from live_files

            def fake_download(_drive_service, _file_id, out_path: Path):
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"image")

            with (
                mock.patch.object(service, "REPO_ROOT", tmp_path),
                mock.patch.object(service, "_build_drive_service", return_value=_FakeDriveService(page_token="token-1")),
                mock.patch.object(service, "_make_drive_service_factory", return_value=lambda: _FakeDriveService()),
                mock.patch.object(service, "_resolve_selected_drive_folder", return_value=_resolved_folder()),
                mock.patch.object(service, "_iter_selected_folder_images", side_effect=fake_iter) as live_listing,
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

            self.assertTrue(live_listing.called)
            self.assertEqual(result["downloaded_count"], 1)
            self.assertEqual(result["newly_downloaded_count"], 1)

    def test_cancelled_drive_sync_raises_without_listing(self) -> None:
        token = CancellationToken()
        token.cancel()

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            mock.patch.object(service, "REPO_ROOT", Path(tmp_dir)),
            mock.patch.object(service, "_build_drive_service", side_effect=AssertionError("service should not be built")),
        ):
            with self.assertRaises(OperationCancelled):
                service.stage_selected_drive_folder(
                    access_token="access-token",
                    refresh_token=None,
                    folder_id="folder-root",
                    folder_name="Camera Folder",
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                    cancellation_token=token,
                )

    def test_cancel_drive_sync_operation_marks_cancelled_state(self) -> None:
        session_key = "test-session"
        session = {
            "selected_drive_folder": {
                "id": "folder-root",
                "name": "Camera Folder",
            }
        }

        with (
            mock.patch.object(routes_drive, "write_session", return_value=None),
            mock.patch.object(routes_drive, "read_session", return_value=session),
        ):
            routes_drive.start_drive_sync_operation(
                session,
                session_key,
                folder=session["selected_drive_folder"],
                message="Syncing",
                staging_dir="data/staging",
            )
            token = routes_drive.get_drive_sync_cancel_token(session_key)
            self.assertIsNotNone(token)
            self.assertFalse(token.is_cancelled())

            state = routes_drive.cancel_drive_sync_operation(
                session,
                session_key,
                folder=session["selected_drive_folder"],
                message="Drive sync stopped by user",
            )
            serialized = routes_drive.serialize_drive_sync_state(
                session=session,
                session_key=session_key,
            )

        self.assertTrue(token.is_cancelled())
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(serialized["status"], "cancelled")
        self.assertTrue(serialized["cancellation_requested"])
        self.assertFalse(serialized["source_ready"])

    def test_clear_drive_sync_endpoint_clears_artifacts_and_resets_state(self) -> None:
        session_key = "test-session-token"
        session = {
            "token": session_key,
            "selected_drive_folder": {
                "id": "folder-root",
                "name": "Camera Folder",
            },
            "drive_sync": {
                "status": "completed",
                "source_ready": True,
                "folder": {
                    "id": "folder-root",
                    "name": "Camera Folder",
                },
                "discovered_count": 123,
                "downloaded_count": 123,
            },
        }

        with (
            mock.patch.object(routes_drive, "read_session", return_value=session),
            mock.patch.object(routes_drive, "write_session", return_value=None),
            mock.patch.object(routes_drive, "resolve_pipeline_staging_dir", return_value=Path("data/staging")),
            mock.patch.object(
                routes_drive,
                "clear_drive_staging_artifacts",
                return_value={"removed_count": 3, "staging_dir": "data/staging"},
            ) as clear_artifacts,
        ):
            response = routes_drive.clear_selected_folder_sync(
                authorization=f"Bearer {session_key}",
            )

        clear_artifacts.assert_called_once()
        self.assertEqual(response["message"], "Drive staged files cleared")
        self.assertEqual(response["sync"]["status"], "idle")
        self.assertEqual(response["sync"]["downloaded_count"], 0)
        self.assertEqual(response["sync"]["discovered_count"], 0)
        self.assertFalse(response["sync"]["source_ready"])

    def test_clear_drive_staging_artifacts_removes_staging_and_drive_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            staging_dir = tmp_path / "data" / "staging"
            outputs_dir = tmp_path / "data" / "outputs"
            staging_dir.mkdir(parents=True)
            outputs_dir.mkdir(parents=True)
            (staging_dir / "file-1.jpg").write_bytes(b"image")
            (staging_dir / service.STAGING_MANIFEST_NAME).write_text("{}", encoding="utf-8")
            drive_index = outputs_dir / "drive_index.csv"
            cache_index = outputs_dir / service.DRIVE_INDEX_CACHE_CSV_NAME
            cache_manifest = outputs_dir / service.DRIVE_INDEX_CACHE_MANIFEST_NAME
            drive_index.write_text("file_name\none.jpg\n", encoding="utf-8")
            cache_index.write_text("file_name\none.jpg\n", encoding="utf-8")
            cache_manifest.write_text("{}", encoding="utf-8")

            with mock.patch.object(service, "REPO_ROOT", tmp_path):
                result = service.clear_drive_staging_artifacts(
                    staging_dir="data/staging",
                    drive_index_path=Path("data/outputs/drive_index.csv"),
                )

            self.assertEqual(result["staging_dir"], str(staging_dir.resolve()))
            self.assertTrue(staging_dir.exists())
            self.assertFalse(any(staging_dir.iterdir()))
            self.assertFalse(drive_index.exists())
            self.assertFalse(cache_index.exists())
            self.assertFalse(cache_manifest.exists())


if __name__ == "__main__":
    unittest.main()
