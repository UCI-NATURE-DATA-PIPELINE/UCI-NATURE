from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.backend import main as backend_main


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class DashboardSpeciesHistogramTests(unittest.TestCase):
    def test_histogram_only_includes_whitelisted_parks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            by_location_dir = tmp_path / "by_location"

            fieldnames = ["CameraName", "Image#", "Species", "has_animal"]
            write_csv(
                by_location_dir / "Research_Park_results.csv",
                fieldnames,
                [
                    {"CameraName": "Research Park", "Image#": "a.jpg", "Species": "coyote", "has_animal": "1"},
                    {"CameraName": "Research Park", "Image#": "b.jpg", "Species": "", "has_animal": "1"},
                    {"CameraName": "Research Park", "Image#": "c.jpg", "Species": "human", "has_animal": "1"},
                ],
            )
            write_csv(
                by_location_dir / "Marshtrail_results.csv",
                fieldnames,
                [
                    {"CameraName": "Marshtrail", "Image#": "d.jpg", "Species": "bobcat", "has_animal": "1"},
                ],
            )
            write_csv(
                by_location_dir / "Bonita_Canyon1_results.csv",
                fieldnames,
                [
                    {"CameraName": "Bonita Canyon 1", "Image#": "e.jpg", "Species": "deer", "has_animal": "1"},
                    {"CameraName": "Bonita Canyon 1", "Image#": "f.jpg", "Species": "vehicle", "has_animal": "1"},
                ],
            )
            write_csv(
                by_location_dir / "Bonita_Canyon2_results.csv",
                fieldnames,
                [
                    {"CameraName": "Bonita Canyon 2", "Image#": "g.jpg", "Species": "raccoon", "has_animal": "0"},
                ],
            )
            write_csv(
                by_location_dir / "misc_results.csv",
                fieldnames,
                [
                    {"CameraName": "Misc", "Image#": "z.jpg", "Species": "coyote", "has_animal": "1"},
                ],
            )

            with patch.object(backend_main, "BY_LOCATION_DIR", by_location_dir):
                result = backend_main.build_dashboard_species_histogram_data()

            parks = {park["key"]: park for park in result["parks"]}
            self.assertEqual(result["default_park_key"], "research_park")
            self.assertTrue(result["has_data"])
            self.assertEqual(parks["research_park"]["species_labels"], ["animal_unclassified", "coyote"])
            self.assertEqual(parks["research_park"]["species_values"], [1, 1])
            self.assertEqual(parks["marshal_trail"]["species_labels"], ["bobcat"])
            self.assertEqual(parks["bonita_canyon_1"]["species_labels"], ["deer"])
            self.assertEqual(parks["bonita_canyon_2"]["species_labels"], [])
            self.assertEqual(result["total_detections"], 4)
            self.assertNotIn("misc", parks)
