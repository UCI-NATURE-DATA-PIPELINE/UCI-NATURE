from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "requirements" / "create_test_csvs.py"),
        run_name="__main__",
    )
