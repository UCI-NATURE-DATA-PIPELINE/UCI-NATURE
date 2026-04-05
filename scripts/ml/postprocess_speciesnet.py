# scripts/ml/postprocess_speciesnet.py

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath


IN_JSON = Path("data/outputs/speciesnet_results.json")
MANIFEST_CSV = Path("data/outputs/manifest.csv")
METADATA_CSV = Path("data/outputs/metadata.csv")

OUT_CSV = Path("data/outputs/speciesnet_results.csv")
REVIEW_CSV = Path("data/outputs/speciesnet_review.csv")

MOUNTED_JSON = Path("/mnt/data/speciesnet_results.json")

THRESH_NORMAL = 0.90
THRESH_GENERIC = 0.97
MARGIN_MIN = 0.20
BURST_WINDOW_SECONDS = 300

GENERIC_EXACT = {
    "no cv result",
    "animal",
    "mammal",
    "rodent",
    "carnivorous mammal",
    "canis species",
}


def normalize_path(p: str) -> str:
    p = (p or "").strip().replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    if p.startswith("./"):
        p = p[2:]
    return p


def tail_key(fp: str, n_parts: int) -> str:
    pp = PurePosixPath(normalize_path(fp))
    parts = pp.parts
    if len(parts) <= n_parts:
        return str(pp)
    return str(PurePosixPath(*parts[-n_parts:]))


def folder_key_from_filepath(fp: str) -> str:
    fp = normalize_path(fp)
    parts = fp.split("/")
    if len(parts) >= 2:
        return parts[-2]
    return "unknown_folder"


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def common_name_from_pred(pred: str) -> str:
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

    vals = []
    for x in scores:
        try:
            vals.append(float(x))
        except Exception:
            pass

    if not vals:
        return (0.0, 0.0)

    vals.sort(reverse=True)
    p1 = vals[0]
    p2 = vals[1] if len(vals) > 1 else 0.0
    return p1, p2


def parse_datetime_loose(s: str):
    if not s:
        return None

    s = str(s).strip()
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

    if "." in s:
        base = s.split(".", 1)[0]
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y:%m:%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
        ]:
            try:
                return datetime.strptime(base, fmt)
            except Exception:
                pass

    return None


def load_manifest_localpath_by_fileid(manifest_csv: Path = MANIFEST_CSV):
    manifest_csv = Path(manifest_csv)
    if not manifest_csv.exists():
        raise FileNotFoundError(f"Missing {manifest_csv}")

    with open(manifest_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = [x.strip() for x in (r.fieldnames or [])]

        def pick_col(options):
            for c in fieldnames:
                if c.lower() in options:
                    return c
            return None

        fileid_col = pick_col({"file_id", "fileid", "id"})
        path_col = pick_col({"local_path", "filepath", "path"})

        if not fileid_col or not path_col:
            raise ValueError(
                f"{manifest_csv} must have file_id/id + local_path/filepath/path. Found: {fieldnames}"
            )

        out = {}
        for row in r:
            fid = (row.get(fileid_col) or "").strip()
            lp = (row.get(path_col) or "").strip()
            if fid and lp:
                out[fid] = normalize_path(lp)

        return out


def load_exif_dt_by_fileid(metadata_csv: Path = METADATA_CSV):
    metadata_csv = Path(metadata_csv)
    if not metadata_csv.exists():
        raise FileNotFoundError(f"Missing {metadata_csv}")

    with open(metadata_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = [x.strip() for x in (r.fieldnames or [])]

        def pick_col(options):
            for c in fieldnames:
                if c.lower() in options:
                    return c
            return None

        fileid_col = pick_col({"file_id", "fileid", "id"})
        if not fileid_col:
            raise ValueError(f"{metadata_csv} must have file_id/id. Found: {fieldnames}")

        exif_col = pick_col({"exif_datetime", "datetime", "exifdatetime", "date_time"})
        date_col = pick_col({"date"})
        time_col = pick_col({"time"})

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
                    if len(d) == 8 and d.isdigit():
                        d_fmt = f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
                        dt = parse_datetime_loose(f"{d_fmt} {t}")
                    else:
                        dt = parse_datetime_loose(f"{d} {t}")

            if dt:
                out[fid] = dt

        return out


def decision_needs_review(label, score, margin):
    is_blank = label == "blank"
    is_human = label == "human"
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

    reason = []
    if is_blank or is_human:
        if score < 0.85:
            reason.append("low_score_for_blank_or_human")
        if margin < 0.10:
            reason.append("low_margin_for_blank_or_human")
    else:
        if score < thresh:
            reason.append(f"low_score<{thresh}")
        if margin < MARGIN_MIN:
            reason.append(f"low_margin<{MARGIN_MIN}")
        if generic:
            reason.append("generic_label")

    return needs_review, final_label, ";".join(reason) if reason else "uncertain"


def burst_vote(items):
    for it in items:
        if it["label_raw"] == "human" and it["score"] >= 0.85:
            return "human"

    blank_weight = sum(it["score"] for it in items if it["label_raw"] == "blank")
    if blank_weight >= 0.85 * max(1, len(items)) * 0.7:
        return "blank"

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

    sorted_items = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    if is_generic(best_label) and best_label not in ("blank", "human"):
        for lab, w in sorted_items[1:]:
            if not is_generic(lab) and (w >= 0.75 * best_w):
                return lab

    return best_label


def make_bursts(pred_rows, burst_window_seconds: int = BURST_WINDOW_SECONDS):
    burst_window_seconds = max(10, min(300, int(burst_window_seconds)))
    by_folder = defaultdict(list)

    for i, pr in enumerate(pred_rows):
        fp = pr["filepath"]
        dt = pr.get("dt")
        if dt is None:
            by_folder[(folder_key_from_filepath(fp), "NO_DT")].append((dt, i))
        else:
            by_folder[folder_key_from_filepath(fp)].append((dt, i))

    bursts = []
    win = timedelta(seconds=burst_window_seconds)

    for key, arr in by_folder.items():
        if isinstance(key, tuple) and key[1] == "NO_DT":
            for _, idx in arr:
                bursts.append([idx])
            continue

        arr.sort(key=lambda x: x[0])
        cur = []
        last_dt = None

        for dt, idx in arr:
            if not cur:
                cur = [idx]
                last_dt = dt
                continue

            if (dt - last_dt) <= win:
                cur.append(idx)
                last_dt = dt
            else:
                bursts.append(cur)
                cur = [idx]
                last_dt = dt

        if cur:
            bursts.append(cur)

    return bursts


def postprocess_speciesnet_results(
    in_path: Path = IN_JSON,
    manifest_csv: Path = MANIFEST_CSV,
    metadata_csv: Path = METADATA_CSV,
    out_csv: Path = OUT_CSV,
    review_csv: Path = REVIEW_CSV,
    burst_window_seconds: int = BURST_WINDOW_SECONDS,
) -> dict:
    burst_window_seconds = max(10, min(300, int(burst_window_seconds)))

    in_path = Path(in_path)
    manifest_csv = Path(manifest_csv)
    metadata_csv = Path(metadata_csv)
    out_csv = Path(out_csv)
    review_csv = Path(review_csv)

    if not in_path.exists() and MOUNTED_JSON.exists():
        in_path = MOUNTED_JSON
    if not in_path.exists():
        raise FileNotFoundError(
            f"Missing input JSON: {in_path} (also checked {MOUNTED_JSON})"
        )

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    preds = data if isinstance(data, list) else data.get("predictions", [])

    fileid_to_path = load_manifest_localpath_by_fileid(manifest_csv)
    fileid_to_dt = load_exif_dt_by_fileid(metadata_csv)

    exact_path_to_dt = {}
    basename_to_candidates = defaultdict(list)
    tail_to_dt = {}

    for fid, dt in fileid_to_dt.items():
        lp = fileid_to_path.get(fid)
        if not lp:
            continue

        lp_n = normalize_path(lp)
        exact_path_to_dt[lp_n] = dt

        bn = PurePosixPath(lp_n).name
        if bn:
            basename_to_candidates[bn].append((lp_n, dt))

        for n in (3, 4, 5):
            tail_to_dt[tail_key(lp_n, n)] = dt

    def lookup_dt(fp: str):
        fp_n = normalize_path(fp)
        if not fp_n:
            return None

        if fp_n in exact_path_to_dt:
            return exact_path_to_dt[fp_n]

        for n in (3, 4, 5):
            t = tail_key(fp_n, n)
            if t in tail_to_dt:
                return tail_to_dt[t]

        bn = PurePosixPath(fp_n).name
        cands = basename_to_candidates.get(bn, [])
        if len(cands) == 1:
            return cands[0][1]

        folder = folder_key_from_filepath(fp_n)
        for fullp, dt in cands:
            if folder_key_from_filepath(fullp) == folder:
                return dt

        return None

    pred_rows = []
    for p in preds:
        fp = normalize_path(p.get("filepath", ""))
        pred_str = p.get("prediction", "")
        score = safe_float(p.get("prediction_score", 0.0), 0.0)

        label = common_name_from_pred(pred_str)
        scores = ((p.get("classifications") or {}).get("scores", []) or [])
        p1, p2 = top2(scores)
        margin = p1 - p2

        pred_rows.append(
            {
                "filepath": fp,
                "label_raw": label,
                "score": score,
                "margin": margin,
                "is_blank": int(label == "blank"),
                "is_human": int(label == "human"),
                "generic": int(is_generic(label)),
                "dt": lookup_dt(fp),
            }
        )

    bursts = make_bursts(pred_rows, burst_window_seconds=burst_window_seconds)

    voted_label_by_idx = {}
    for burst in bursts:
        items = [
            {
                "label_raw": pred_rows[idx]["label_raw"],
                "score": pred_rows[idx]["score"],
            }
            for idx in burst
        ]
        voted = burst_vote(items)
        for idx in burst:
            voted_label_by_idx[idx] = voted

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    review_csv.parent.mkdir(parents=True, exist_ok=True)

    review_count = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as f_out, open(
        review_csv, "w", newline="", encoding="utf-8"
    ) as f_rev:
        out_w = csv.DictWriter(
            f_out,
            fieldnames=[
                "filepath",
                "label_raw",
                "score",
                "p1_minus_p2",
                "burst_label",
                "is_blank",
                "is_human",
                "final_label",
                "needs_review",
            ],
        )
        rev_w = csv.DictWriter(
            f_rev,
            fieldnames=[
                "filepath",
                "label_raw",
                "score",
                "p1_minus_p2",
                "burst_label",
                "reason",
            ],
        )

        out_w.writeheader()
        rev_w.writeheader()

        for i, r in enumerate(pred_rows):
            label = r["label_raw"]
            score = r["score"]
            margin = r["margin"]

            burst_label = voted_label_by_idx.get(i, label)
            working = burst_label or label

            needs_review, final_label, reason = decision_needs_review(
                working, score, margin
            )

            out_w.writerow(
                {
                    "filepath": r["filepath"],
                    "label_raw": label,
                    "score": round(score, 6),
                    "p1_minus_p2": round(margin, 6),
                    "burst_label": working,
                    "is_blank": r["is_blank"],
                    "is_human": r["is_human"],
                    "final_label": final_label,
                    "needs_review": int(needs_review),
                }
            )

            if needs_review:
                review_count += 1
                rev_w.writerow(
                    {
                        "filepath": r["filepath"],
                        "label_raw": label,
                        "score": round(score, 6),
                        "p1_minus_p2": round(margin, 6),
                        "burst_label": working,
                        "reason": reason,
                    }
                )

    print(f"Wrote: {out_csv}")
    print(f"Wrote: {review_csv}")
    print(f"Burst window: {burst_window_seconds}s")
    print(f"Total predictions: {len(pred_rows)}")
    print(f"Total bursts: {len(bursts)}")

    return {
        "results_csv": str(out_csv),
        "review_csv": str(review_csv),
        "total_predictions": len(pred_rows),
        "total_bursts": len(bursts),
        "review_items": review_count,
        "burst_window_seconds": burst_window_seconds,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_path", default=str(IN_JSON))
    parser.add_argument("--manifest_csv", default=str(MANIFEST_CSV))
    parser.add_argument("--metadata_csv", default=str(METADATA_CSV))
    parser.add_argument("--out_csv", default=str(OUT_CSV))
    parser.add_argument("--review_csv", default=str(REVIEW_CSV))
    parser.add_argument("--burst_window", type=int, default=300)
    args = parser.parse_args()

    postprocess_speciesnet_results(
        in_path=Path(args.in_path),
        manifest_csv=Path(args.manifest_csv),
        metadata_csv=Path(args.metadata_csv),
        out_csv=Path(args.out_csv),
        review_csv=Path(args.review_csv),
        burst_window_seconds=args.burst_window,
    )


if __name__ == "__main__":
    main()
    