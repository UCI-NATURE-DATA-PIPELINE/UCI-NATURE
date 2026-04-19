from __future__ import annotations

import argparse
import csv
import tempfile
import unittest
from pathlib import Path

from scripts.pipeline.extract_metadata import merge_metadata_with_ml_outputs
from scripts.pipeline.make_manifest import append_manifest_file_ids_to_cache
from scripts.pipeline.make_output import generate_output_csvs
from scripts.pipeline.run_pipeline import resolve_source_root


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class PipelineBackendRefactorTests(unittest.TestCase):
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
