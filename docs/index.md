# UCI Nature Wildlife Pipeline

A backend Python pipeline for processing wildlife camera images.

## Overview

This project processes wildlife camera images, reduces manual review, and generates structured CSV outputs. The backend pipeline indexes files, downloads images when needed, builds manifests, runs wildlife classification, and writes results into the output folders.

## Goal

The goal is to turn large image collections into structured CSV results that are easier to review and share. The main outputs are written under `data/outputs/`, including per-camera CSV files in `data/outputs/by_location/`.

## Run paths

You can run the pipeline in two main ways:

1. from images copied locally from an SD card or another folder on your computer
2. from images retrieved from Google Drive

For this docs site, ignore the frontend, UI, Docker, and deployment parts of the repository.

## Workflow

1. Install Python 3.11 and the project dependencies.
2. Run the local-folder workflow or the Google Drive workflow.
3. Check the CSV outputs in `data/outputs/` and `data/outputs/by_location/`.

## Pages

- [Setup](setup.md)
- [Run](run.md)
- [Troubleshooting](troubleshooting.md)
