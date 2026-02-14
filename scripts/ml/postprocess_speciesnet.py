import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

IN_JSON = Path("data/outputs/speciesnet_results.json")
MANIFEST_CSV = Path("data/outputs/manifest.csv")
METADATA_CSV = Path("data/outputs/metadata.csv")

OUT_CSV = Path("data/outputs/speciesnet_postprocessed.csv")
REVIEW_CSV = Path("data/outputs/speciesnet_review.csv")

# Tunable accuracy knobs
THRESH_NORMAL = 0.90
THRESH_GENERIC = 0.97
MARGIN_MIN = 0.20

# Burst voting
BURST_WINDOW_SECONDS = 45  # group shots taken within 45s in the same folder

GENERIC_EXACT = {
    "no cv result", "animal", "mammal", "rodent", "carnivorous mammal", "canis species"
}

def common_name_from_pred(pred: str) -> str:
    # Format: uuid;class;order;family;genus;species;common_name
    parts = pred.split(";") if pred else []
    if len(parts) >= 7 and parts[6].strip():
        return parts[6].strip().lower()
    for i in range(min(6, len(parts) - 1), 0, -1):
        if parts[i].strip():
            return parts[i].strip().lower()
    return "unknown"

def is_generic(label: str) -> bool:
    l = (label or "").lower()
    return (
        l in GENERIC_EXACT
        or l.endswith(" family")
        or l.endswith(" species")
        or l == "unknown"
    )

def top2(scores):
    if not scores:
        return (0.0, 0.0)
    s = sorted([float(x) for x in scores], reverse=True)
    p1 = s[0]
    p2 = s[1] if len(s) > 1 else 0.0
    return p1, p2

def parse_datetime_loose(s: str):
    """Try common datetime formats. Returns datetime or None."""
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    # last resort: try trimming fractional seconds
    if "." in s:
        base = s.split(".", 1)[0]
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                return datetime.strptime(base, fmt)
            except Exception:
                pass
    return None

def get_first_existing_key(d, candidates):
    for c in candidates:
        if c in d and d[c] not in (None, ""):
            return c
    return None

def load_manifest_localpath_by_fileid():
    """
    Returns dict: file_id -> local_path (relative/absolute string)
    Accepts headers like:
      - file_id, local_path
      - id, local_path
      - file_id, filepath
    """
    if not MANIFEST_CSV.exists():
        raise FileNotFoundError(f"Missing {MANIFEST_CSV}")

    with open(MANIFEST_CSV, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = [x.strip() for x in (r.fieldnames or [])]

        # Guess columns
        def norm(s): return (s or "").strip()

        fileid_col = None
        for c in fieldnames:
            if c.lower() in ("file_id", "fileid", "id"):
                fileid_col = c
                break

        path_col = None
        for c in fieldnames:
            if c.lower() in ("local_path", "filepath", "path"):
                path_col = c
                break

        if not fileid_col or not path_col:
            raise ValueError(f"manifest.csv must have file_id/id + local_path/filepath. Found: {fieldnames}")

        out = {}
        for row in r:
            fid = norm(row.get(fileid_col))
            lp = norm(row.get(path_col))
            if fid and lp:
                out[fid] = lp
        return out

def load_exif_dt_by_fileid():
    """
    Returns dict: file_id -> datetime
    Accepts:
      - file_id + exif_datetime
      - file_id + Date + Time
    """
    if not METADATA_CSV.exists():
        raise FileNotFoundError(f"Missing {METADATA_CSV}")

    with open(METADATA_CSV, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = [x.strip() for x in (r.fieldnames or [])]

        fileid_col = None
        for c in fieldnames:
            if c.lower() in ("file_id", "fileid", "id"):
                fileid_col = c
                break
        if not fileid_col:
            raise ValueError(f"metadata.csv must have file_id/id. Found: {fieldnames}")

        exif_col = None
        for c in fieldnames:
            if c.lower() in ("exif_datetime", "datetime", "exifdatetime", "date_time"):
                exif_col = c
                break

        date_col = None
        time_col = None
        for c in fieldnames:
            if c.lower() == "date":
                date_col = c
            if c.lower() == "time":
                time_col = c

        out = {}
        for row in r:
            fid = (row.get(fileid_col) or "").strip()
            if not fid:
                continue

            dt = None
            if exif_col:
                dt = parse_datetime_loose(row.get(exif_col, ""))
            if dt is None and date_col and time_col:
                d = (row.get(date_col) or "").strip()
                t = (row.get(time_col) or "").strip()
                if d and t:
                    # handle date like YYYYMMDD or YYYY-MM-DD
                    if len(d) == 8 and d.isdigit():
                        d_fmt = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
                        dt = parse_datetime_loose(f"{d_fmt} {t}")
                    else:
                        dt = parse_datetime_loose(f"{d} {t}")

            if dt:
                out[fid] = dt
        return out

def normalize_path(p: str) -> str:
    return (p or "").replace("\\", "/").strip()

def folder_key_from_filepath(fp: str) -> str:
    fp = normalize_path(fp)
    # ex: data/staging/2020_08_04_BonitaCanyon1/xxxxx.JPG -> folder = 2020_08_04_BonitaCanyon1
    parts = fp.split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "unknown_folder"

def decision_needs_review(label, score, margin):
    is_blank = (label == "blank")
    is_human = (label == "human")
    generic = is_generic(label)
    thresh = THRESH_GENERIC if generic else THRESH_NORMAL

    needs_review = False

    if is_blank or is_human:
        if score < 0.85 or margin < 0.10:
            needs_review = True
    else:
        if score < thresh:
            needs_review = True
        if margin < MARGIN_MIN:
            needs_review = True
        if generic:
            needs_review = True

    final_label = label
    if needs_review and not (is_blank or is_human):
        final_label = "unknown"

    reason = []
    if is_blank or is_human:
        if score < 0.85: reason.append("low_score_for_blank_or_human")
        if margin < 0.10: reason.append("low_margin_for_blank_or_human")
    else:
        if score < thresh: reason.append(f"low_score<{thresh}")
        if margin < MARGIN_MIN: reason.append(f"low_margin<{MARGIN_MIN}")
        if generic: reason.append("generic_label")

    return needs_review, final_label, ";".join(reason) if reason else "uncertain"

def burst_vote(items):
    """
    items = list of dicts with:
      - idx (index into preds list)
      - label_raw
      - score
      - is_blank / is_human
      - generic
    Returns voted_label (string)
    """
    # Strong rule: if any confident human in burst -> human
    # (you can tweak these thresholds)
    for it in items:
        if it["label_raw"] == "human" and it["score"] >= 0.85:
            return "human"
    # Strong rule: if majority confident blank -> blank
    blank_weight = sum(it["score"] for it in items if it["label_raw"] == "blank")
    if blank_weight >= 0.85 * max(1, len(items)) * 0.7:
        return "blank"

    # Weighted vote, but downweight generic labels heavily
    weights = defaultdict(float)
    for it in items:
        lab = it["label_raw"]
        w = float(it["score"])
        if is_generic(lab) and lab not in ("blank", "human"):
            w *= 0.15
        weights[lab] += w

    if not weights:
        return "unknown"

    best_label, best_w = max(weights.items(), key=lambda x: x[1])

    # If best is generic and there exists a non-generic alternative close behind, pick non-generic
    sorted_items = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    if is_generic(best_label) and best_label not in ("blank", "human"):
        for lab, w in sorted_items[1:]:
            if not is_generic(lab) and (w >= 0.75 * best_w):
                return lab

    return best_label

def make_bursts(pred_rows, fp_to_dt):
    """
    pred_rows: list of dicts with filepath and other info
    fp_to_dt: dict filepath -> datetime
    Returns list of bursts, each is list of indices into pred_rows
    """
    # Group by folder first
    by_folder = defaultdict(list)
    for i, pr in enumerate(pred_rows):
        fp = pr["filepath"]
        dt = fp_to_dt.get(fp)
        if dt is None:
            # no timestamp -> isolate as single burst
            by_folder[(folder_key_from_filepath(fp), "NO_DT")].append((dt, i))
        else:
            by_folder[folder_key_from_filepath(fp)].append((dt, i))

    bursts = []
    win = timedelta(seconds=BURST_WINDOW_SECONDS)

    for key, arr in by_folder.items():
        if isinstance(key, tuple) and key[1] == "NO_DT":
            for _, idx in arr:
                bursts.append([idx])
            continue

        arr.sort(key=lambda x: x[0])
        cur = []
        start_dt = None
        last_dt = None

        for dt, idx in arr:
            if not cur:
                cur = [idx]
                start_dt = dt
                last_dt = dt
                continue
            # same burst if within window of last or within window of start (either works; we use last)
            if (dt - last_dt) <= win:
                cur.append(idx)
                last_dt = dt
            else:
                bursts.append(cur)
                cur = [idx]
                start_dt = dt
                last_dt = dt

        if cur:
            bursts.append(cur)

    return bursts

def main():
    data = json.load(open(IN_JSON, "r"))
    preds = data.get("predictions", [])

    # Build filepath -> datetime using manifest+metadata
    fileid_to_path = load_manifest_localpath_by_fileid()
    fileid_to_dt = load_exif_dt_by_fileid()

    # Normalize manifest paths to match speciesnet filepaths (speciesnet uses "data/staging/...")
    # We'll try to match by suffix if needed.
    norm_path_to_dt = {}
    for fid, dt in fileid_to_dt.items():
        lp = fileid_to_path.get(fid)
        if not lp:
            continue
        norm_path_to_dt[normalize_path(lp)] = dt

    # Make a helper to find dt for a given speciesnet filepath
    def lookup_dt(fp):
        fp_n = normalize_path(fp)
        if fp_n in norm_path_to_dt:
            return norm_path_to_dt[fp_n]
        # fallback: match by suffix (handles relative vs absolute differences)
        for k, dt in norm_path_to_dt.items():
            if fp_n.endswith(k) or k.endswith(fp_n):
                return dt
        return None

    # Prepare per-pred rows
    pred_rows = []
    for p in preds:
        fp = normalize_path(p.get("filepath", ""))
        pred_str = p.get("prediction", "")
        score = float(p.get("prediction_score", 0.0))

        label = common_name_from_pred(pred_str)
        scores = (p.get("classifications") or {}).get("scores", [])
        p1, p2 = top2(scores)
        margin = p1 - p2

        pred_rows.append({
            "filepath": fp,
            "label_raw": label,
            "score": score,
            "margin": margin,
            "is_blank": int(label == "blank"),
            "is_human": int(label == "human"),
            "generic": int(is_generic(label)),
            "dt": lookup_dt(fp),
        })

    # Build filepath->dt map for burst building
    fp_to_dt = {r["filepath"]: r["dt"] for r in pred_rows if r["dt"] is not None}

    bursts = make_bursts(pred_rows, fp_to_dt)

    # Burst vote label per image
    voted_label_by_idx = {}
    for burst in bursts:
        items = []
        for idx in burst:
            r = pred_rows[idx]
            items.append({
                "idx": idx,
                "label_raw": r["label_raw"],
                "score": r["score"],
            })
        voted = burst_vote(items)
        for idx in burst:
            voted_label_by_idx[idx] = voted

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f_out, \
         open(REVIEW_CSV, "w", newline="", encoding="utf-8") as f_rev:

        out_w = csv.DictWriter(f_out, fieldnames=[
            "filepath", "label_raw", "score", "p1_minus_p2",
            "burst_label", "is_blank", "is_human", "final_label", "needs_review"
        ])
        rev_w = csv.DictWriter(f_rev, fieldnames=[
            "filepath", "label_raw", "score", "p1_minus_p2", "burst_label", "reason"
        ])
        out_w.writeheader()
        rev_w.writeheader()

        for i, r in enumerate(pred_rows):
            label = r["label_raw"]
            score = r["score"]
            margin = r["margin"]
            burst_label = voted_label_by_idx.get(i, label)

            # If burst vote gives something non-generic, use it as the working label
            working = burst_label if burst_label else label

            needs_review, final_label, reason = decision_needs_review(working, score, margin)

            out_w.writerow({
                "filepath": r["filepath"],
                "label_raw": label,
                "score": round(score, 6),
                "p1_minus_p2": round(margin, 6),
                "burst_label": working,
                "is_blank": r["is_blank"],
                "is_human": r["is_human"],
                "final_label": final_label,
                "needs_review": int(needs_review),
            })

            if needs_review:
                rev_w.writerow({
                    "filepath": r["filepath"],
                    "label_raw": label,
                    "score": round(score, 6),
                    "p1_minus_p2": round(margin, 6),
                    "burst_label": working,
                    "reason": reason,
                })

    print(f"Wrote: {OUT_CSV}")
    print(f"Wrote: {REVIEW_CSV}")
    print(f"Burst window: {BURST_WINDOW_SECONDS}s")
    print(f"Total predictions: {len(pred_rows)}")
    print(f"Total bursts: {len(bursts)}")

if __name__ == "__main__":
    main()