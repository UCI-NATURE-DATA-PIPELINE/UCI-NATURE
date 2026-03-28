# Drive Upload Pipeline

Uploads processed CSV results back to Julie's Wildlife Database on Google Drive.

## WARNING

DO NOT TEST THESE SCRIPTS WITHOUT PERMISSION. Running them will upload files directly to Julie's Drive and cannot be easily undone.

## How It Works

1. `make_output.py` (part of main pipeline) — generates one CSV per camera in `data/outputs/by_location/`
2. `find_camera_folders.py` — helper to look up Drive folder IDs for each camera location
3. `upload_to_drive.py` — uploads per-camera CSVs to Julie's Drive with append + deduplication logic

## For Developers

Step 1: Run the main pipeline first
The main pipeline (`run_pipeline.py`) produces `data/outputs/by_location/<CameraName>.csv` files automatically. Run that before uploading.

Step 2: Find folder IDs (first-time setup only)
```bash
python scripts/drive_upload/find_camera_folders.py
```

Copy the folder IDs and paste them into `upload_to_drive.py` in the `CAMERA_FOLDERS` dictionary. This only needs to be done once per new camera location.

Step 3: Test locally first (IMPORTANT)
Before running on Julie's Drive, test on your personal Google Drive:
- Create a test folder structure in your Drive
- Share it with the service account
- Modify CAMERA_FOLDERS in upload_to_drive.py to use your test folder IDs
- Run upload_to_drive.py to verify it works

Step 4: Upload to Julie's Drive (with permission)
Once testing is confirmed working:
- Update CAMERA_FOLDERS with real Julie's folder IDs
- Run upload_to_drive.py

## For Julie

Once this is integrated into the full pipeline, the workflow will be:
1. Run the main pipeline script
2. Results automatically upload to your Drive in the correct camera folders
3. Existing CSVs are updated with new data instead of overwritten
4. No manual work needed

## Technical Details

Uses Google Drive API with service account authentication (inf191a-uci-nature-sa.json).
Creates one CSV per camera location with append and deduplication logic.