from __future__ import annotations

import argparse
import csv
import tempfile
import unittest
from pathlib import Path

from ui.backend.cancellation import OperationCancelled
from scripts.pipeline.extract_metadata import merge_metadata_with_ml_outputs
from scripts.pipeline.make_manifest import append_manifest_file_ids_to_cache
from scripts.pipeline.make_output import generate_output_csvs
from scripts.pipeline.run_pipeline import resolve_source_root
from scripts.pipeline.simple_outputs import build_simple_rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class PipelineBackendRefactorTests(unittest.TestCase):
    def test_pipeline_service_passes_cancel_check_into_each_step(self) -> None:
        from ui.backend.services import pipeline_service as service

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            staging_dir = tmp_path / "staging"
            staging_dir.mkdir(parents=True, exist_ok=True)

            calls = []

            def cancel_check() -> bool:
                return False

            def assert_cancel_check(step_name: str, kwargs: dict) -> None:
                calls.append(step_name)
                self.assertIn("cancel_check", kwargs)
                self.assertIs(kwargs["cancel_check"], cancel_check)

            original_build_manifest = service.build_manifest
            original_extract_metadata = service.extract_metadata_from_manifest
            original_run_speciesnet = service.run_speciesnet_model
            original_run_speciesnet_csv = service.run_speciesnet
            original_postprocess = service.postprocess_speciesnet_results
            original_generate_output = service.generate_output_csvs

            def fake_build_manifest(*args, **kwargs):
                assert_cancel_check("build_manifest", kwargs)
                manifest_path = tmp_path / "manifest.csv"
                write_csv(
                    manifest_path,
                    ["file_id", "local_path"],
                    [{"file_id": "img-1", "local_path": str(tmp_path / "one.jpg")}],
                )
                return {"manifest_path": str(manifest_path), "rows_written": 1}

            def fake_extract_metadata(*args, **kwargs):
                assert_cancel_check("extract_metadata_from_manifest", kwargs)
                return {"metadata_path": str(tmp_path / "metadata.csv"), "rows_written": 1}

            def fake_run_speciesnet(*args, **kwargs):
                assert_cancel_check("run_speciesnet_model", kwargs)
                speciesnet_json = tmp_path / "speciesnet.json"
                speciesnet_json.write_text("{\"predictions\": []}", encoding="utf-8")
                return {"speciesnet_json": str(speciesnet_json), "classified_images": 1}

            def fake_run_speciesnet_csv(*args, **kwargs):
                out_csv = Path(kwargs.get("out_csv") or tmp_path / "ml_outputs.csv")
                write_csv(
                    out_csv,
                    ["filepath", "final_label", "needs_review"],
                    [],
                )
                return {"ml_outputs_path": str(out_csv), "threshold": 0.8}

            def fake_postprocess(*args, **kwargs):
                assert_cancel_check("postprocess_speciesnet_results", kwargs)
                return {
                    "results_csv": str(tmp_path / "speciesnet_results.csv"),
                    "review_csv": str(tmp_path / "speciesnet_review.csv"),
                    "total_predictions": 1,
                    "total_bursts": 1,
                    "review_items": 0,
                    "generic_label_review_items": 0,
                    "burst_window_seconds": 300,
                }

            def fake_generate_output(*args, **kwargs):
                assert_cancel_check("generate_output_csvs", kwargs)
                return {
                    "drive_index_present": False,
                    "out_dir": str(tmp_path / "by_location"),
                }

            service.build_manifest = fake_build_manifest
            service.extract_metadata_from_manifest = fake_extract_metadata
            service.run_speciesnet_model = fake_run_speciesnet
            service.run_speciesnet = fake_run_speciesnet_csv
            service.postprocess_speciesnet_results = fake_postprocess
            service.generate_output_csvs = fake_generate_output

            try:
                result = service.run_pipeline_service(
                    service.PipelineRunConfig(staging_dir=staging_dir),
                    cancel_check=cancel_check,
                )
            finally:
                service.build_manifest = original_build_manifest
                service.extract_metadata_from_manifest = original_extract_metadata
                service.run_speciesnet_model = original_run_speciesnet
                service.run_speciesnet = original_run_speciesnet_csv
                service.postprocess_speciesnet_results = original_postprocess
                service.generate_output_csvs = original_generate_output

            self.assertEqual(
                calls,
                [
                    "build_manifest",
                    "extract_metadata_from_manifest",
                    "run_speciesnet_model",
                    "postprocess_speciesnet_results",
                    "extract_metadata_from_manifest",
                    "generate_output_csvs",
                ],
            )
            self.assertEqual(result["steps"]["output"]["drive_index_present"], False)

    def test_generate_output_csvs_honors_cancel_check_before_working_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest_path = tmp_path / "manifest.csv"
            metadata_path = tmp_path / "metadata.csv"
            out_dir = tmp_path / "by_location"

            write_csv(
                manifest_path,
                ["file_id", "file_name", "local_file_name", "local_path"],
                [
                    {
                        "file_id": "img-1",
                        "file_name": "one.jpg",
                        "local_file_name": "one.jpg",
                        "local_path": str(tmp_path / "one.jpg"),
                    }
                ],
            )
            write_csv(
                metadata_path,
                [
                    "file_id",
                    "file_name",
                    "local_file_name",
                    "local_path",
                    "date",
                    "time",
                    "has_animal",
                    "has_human",
                    "species",
                    "species_level",
                    "species_raw",
                    "model_certainty",
                    "prediction_source",
                    "resolved_source",
                    "count",
                ],
                [
                    {
                        "file_id": "img-1",
                        "file_name": "one.jpg",
                        "local_file_name": "one.jpg",
                        "local_path": str(tmp_path / "one.jpg"),
                        "date": "20260419",
                        "time": "08:00:00",
                        "has_animal": "1",
                        "has_human": "0",
                        "species": "coyote",
                        "species_level": "1",
                        "species_raw": "Canis latrans",
                        "model_certainty": "0.98",
                        "prediction_source": "speciesnet",
                        "resolved_source": "speciesnet",
                        "count": "1",
                    }
                ],
            )

            with self.assertRaises(OperationCancelled):
                generate_output_csvs(
                    manifest=manifest_path,
                    metadata=metadata_path,
                    drive_index=None,
                    out_dir=out_dir,
                    cancel_check=lambda: True,
                )

            self.assertFalse((out_dir / "final_results.csv").exists())

    def test_pipeline_cancel_state_is_cancelled_not_failed(self) -> None:
        from ui.backend import main as backend_main

        session_key = "pipeline-cancel-test"
        backend_main.PIPELINE_STATES.clear()
        backend_main.PIPELINE_CANCEL_TOKENS.clear()
        state = backend_main._get_pipeline_state(session_key)
        state.update({
            "status": "running",
            "run_id": "run-1",
            "started_at": "2026-05-27T00:00:00",
            "progress": {
                "step": "Run SpeciesNet",
                "percent": 55,
                "message": "Running",
                "details": {},
            },
        })
        token = backend_main._create_pipeline_cancel_token(session_key)

        cancelled = backend_main.mark_pipeline_cancelled(
            session_key,
            message="Pipeline stop requested",
        )

        self.assertTrue(token.is_cancelled())
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(cancelled["error"])
        self.assertTrue(cancelled["cancellation_requested"])
        self.assertEqual(cancelled["progress"]["step"], "Cancelled")
        backend_main.PIPELINE_STATES.clear()
        backend_main.PIPELINE_CANCEL_TOKENS.clear()

    def test_merge_metadata_with_ml_outputs_updates_existing_metadata_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            metadata_path = tmp_path / "metadata.csv"
            ml_outputs_path = tmp_path / "ml_outputs.csv"

            write_csv(
                metadata_path,
                ["file_id", "local_path", "date", "time", "width", "height"],
                [
                    {
                        "file_id": "abc123",
                        "local_path": "/tmp/example.jpg",
                        "date": "2026-04-19",
                        "time": "08:00:00",
                        "width": "1200",
                        "height": "800",
                    }
                ],
            )
            write_csv(
                ml_outputs_path,
                ["file_id", "has_animal", "species", "model_certainty"],
                [
                    {
                        "file_id": "abc123",
                        "has_animal": "1",
                        "species": "coyote",
                        "model_certainty": "0.97",
                    }
                ],
            )

            result = merge_metadata_with_ml_outputs(metadata_path, ml_outputs_path)

            with open(metadata_path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(result["rows_written"], 1)
            self.assertEqual(rows[0]["date"], "2026-04-19")
            self.assertEqual(rows[0]["width"], "1200")
            self.assertEqual(rows[0]["has_animal"], "1")
            self.assertEqual(rows[0]["species"], "coyote")

    def test_append_manifest_file_ids_to_cache_is_incremental_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest_path = tmp_path / "manifest.csv"
            cache_path = tmp_path / "processed_file_ids.txt"

            write_csv(
                manifest_path,
                ["file_id", "file_name"],
                [
                    {"file_id": "fid-1", "file_name": "one.jpg"},
                    {"file_id": "fid-2", "file_name": "two.jpg"},
                ],
            )
            cache_path.write_text("fid-1\n", encoding="utf-8")

            first_result = append_manifest_file_ids_to_cache(manifest_path, cache_path)
            second_result = append_manifest_file_ids_to_cache(manifest_path, cache_path)

            cache_values = cache_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(first_result["ids_appended"], 1)
            self.assertEqual(second_result["ids_appended"], 0)
            self.assertEqual(cache_values, ["fid-1", "fid-2"])

    def test_generate_output_csvs_works_without_drive_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest_path = tmp_path / "manifest.csv"
            metadata_path = tmp_path / "metadata.csv"
            out_dir = tmp_path / "by_location"

            write_csv(
                manifest_path,
                ["file_id", "file_name", "local_file_name", "local_path"],
                [
                    {
                        "file_id": "local-1",
                        "file_name": "IMG_0001.JPG",
                        "local_file_name": "IMG_0001.JPG",
                        "local_path": "/Users/test/Desktop/CameraA/IMG_0001.JPG",
                    }
                ],
            )
            write_csv(
                metadata_path,
                [
                    "file_id",
                    "file_name",
                    "local_file_name",
                    "local_path",
                    "date",
                    "time",
                    "exif_datetime",
                    "has_animal",
                    "has_human",
                    "species",
                    "species_level",
                    "species_raw",
                    "model_certainty",
                    "prediction_source",
                    "resolved_source",
                    "count",
                ],
                [
                    {
                        "file_id": "local-1",
                        "file_name": "IMG_0001.JPG",
                        "local_file_name": "IMG_0001.JPG",
                        "local_path": "/Users/test/Desktop/CameraA/IMG_0001.JPG",
                        "date": "20260419",
                        "time": "08:00:00",
                        "exif_datetime": "2026:04:19 08:00:00",
                        "has_animal": "1",
                        "has_human": "0",
                        "species": "coyote",
                        "species_level": "1",
                        "species_raw": "Canis latrans",
                        "model_certainty": "0.98",
                        "prediction_source": "speciesnet",
                        "resolved_source": "speciesnet",
                        "count": "1",
                    }
                ],
            )

            result = generate_output_csvs(
                manifest=manifest_path,
                metadata=metadata_path,
                drive_index=None,
                out_dir=out_dir,
            )

            self.assertFalse(result["drive_index_present"])
            self.assertEqual(result["rows_written"], 1)
            self.assertTrue((out_dir / "all_results.csv").exists())
            for filename in [
                "final_results.csv",
                "animal_results.csv",
                "review_needed.csv",
                "summary_by_camera.csv",
            ]:
                self.assertTrue((out_dir / filename).exists())

    def test_simple_animal_results_exclude_human_and_vehicle_rows(self) -> None:
        rows = build_simple_rows(
            [
                {
                    "_filename": "coyote.jpg",
                    "CameraName": "CameraA",
                    "Date": "20260419",
                    "Time": "08:00:00",
                    "has_animal": "1",
                    "Species": "Canis latrans",
                    "model_certainty": "0.97",
                    "# of Individuals": "1",
                },
                {
                    "_filename": "person.jpg",
                    "CameraName": "CameraA",
                    "Date": "20260419",
                    "Time": "08:01:00",
                    "has_animal": "1",
                    "Species": "human",
                    "model_certainty": "0.99",
                    "# of Individuals": "1",
                },
                {
                    "_filename": "truck.jpg",
                    "CameraName": "CameraA",
                    "Date": "20260419",
                    "Time": "08:02:00",
                    "has_animal": "1",
                    "Species": "vehicle",
                    "model_certainty": "0.99",
                    "# of Individuals": "1",
                },
            ]
        )

        animal_rows = [
            row
            for row in rows
            if row["animal_detected"] == "yes"
            and row["species"]
            and row["species"] not in {"human", "vehicle", "blank"}
        ]

        self.assertEqual([row["species"] for row in rows], ["coyote", "human", "vehicle"])
        self.assertEqual([row["image_name"] for row in animal_rows], ["coyote.jpg"])

    def test_simple_rows_use_resolved_species_fields_without_collapsing_to_blank(self) -> None:
        rows = build_simple_rows(
            [
                {
                    "local_file_name": "coyote.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:00:00",
                    "has_animal": "1",
                    "species": "coyote",
                    "model_certainty": "0.97",
                },
                {
                    "local_file_name": "raccoon.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:01:00",
                    "has_animal": "1",
                    "species": "northern raccoon",
                    "model_certainty": "0.88",
                },
                {
                    "local_file_name": "blank.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:02:00",
                    "has_animal": "0",
                    "species": "blank",
                    "model_certainty": "0.36",
                    "count": "1",
                },
            ]
        )

        by_name = {row["image_name"]: row for row in rows}
        self.assertEqual(by_name["coyote.jpg"]["animal_detected"], "yes")
        self.assertEqual(by_name["coyote.jpg"]["species"], "coyote")
        self.assertEqual(by_name["coyote.jpg"]["confidence"], "0.97")
        self.assertEqual(by_name["raccoon.jpg"]["animal_detected"], "yes")
        self.assertEqual(by_name["raccoon.jpg"]["species"], "raccoon")
        self.assertEqual(by_name["blank.jpg"]["animal_detected"], "no")
        self.assertEqual(by_name["blank.jpg"]["species"], "blank")

    def test_simple_rows_truncate_confidence_without_rounding_or_zeroing_blank_rows(self) -> None:
        rows = build_simple_rows(
            [
                {
                    "local_file_name": "human.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:00:00",
                    "has_animal": "0",
                    "species": "human",
                    "model_certainty": "0.93",
                },
                {
                    "local_file_name": "animal.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:01:00",
                    "has_animal": "1",
                    "species": "coyote",
                    "model_certainty": "0.999",
                },
                {
                    "local_file_name": "blank.jpg",
                    "camera": "CameraA",
                    "date": "20260419",
                    "time": "08:02:00",
                    "has_animal": "0",
                    "species": "blank",
                    "prediction_score_raw": "0.36",
                },
            ]
        )

        by_name = {row["image_name"]: row for row in rows}
        self.assertEqual(by_name["human.jpg"]["confidence"], "0.93")
        self.assertEqual(by_name["animal.jpg"]["confidence"], "0.99")
        self.assertEqual(by_name["blank.jpg"]["confidence"], "0.36")

    def test_resolve_source_root_distinguishes_manual_and_staging_modes(self) -> None:
        with tempfile.TemporaryDirectory() as manual_dir, tempfile.TemporaryDirectory() as staging_dir:
            manual_args = argparse.Namespace(mode="manual", folder=manual_dir)
            staging_args = argparse.Namespace(mode="staging", folder=staging_dir)

            manual_mode, manual_root = resolve_source_root(manual_args)
            staging_mode, staging_root = resolve_source_root(staging_args)

            self.assertEqual(manual_mode, "direct_local_folder")
            self.assertEqual(manual_root, Path(manual_dir).resolve())
            self.assertEqual(staging_mode, "existing_staging")
            self.assertEqual(staging_root, Path(staging_dir).resolve())


if __name__ == "__main__":
    unittest.main()
