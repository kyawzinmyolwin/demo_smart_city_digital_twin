#!/usr/bin/env python3
"""
Calibrate Unity Transform (position XZ + yaw) for Christchurch_Central_City_3D.fbx
against Christchurch_Central_City_main_streets.net.xml lane shapes.

FBX road meshes use local X/Y (Z=0); Unity ground plane is X/Z with Y up.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from _sim_root import PROJECT_ROOT as root

try:
    import ufbx
except ImportError as e:
    raise SystemExit("pip install ufbx") from e


def load_fbx_road_points(fbx_path: Path) -> np.ndarray:
    scene = ufbx.load_file(str(fbx_path))
    pts: list[tuple[float, float]] = []
    for node in scene.nodes:
        if not node.mesh:
            continue
        name = node.mesh.name or node.name
        if "osm_roads_" not in name:
            continue
        for v in node.mesh.vertices:
            pts.append((float(v.x), float(v.y)))
    if not pts:
        raise RuntimeError("No map_*osm_roads_* vertices in FBX")
    return np.asarray(pts, dtype=np.float64)


def load_sumo_lane_points(net_path: Path) -> np.ndarray:
    root = ET.parse(net_path).getroot()
    pts: list[tuple[float, float]] = []
    for lane in root.iter("lane"):
        shape = lane.get("shape")
        if not shape:
            continue
        for token in shape.split():
            x, y = token.split(",")
            pts.append((float(x), float(y)))
    if not pts:
        raise RuntimeError("No lane shapes in net.xml")
    return np.asarray(pts, dtype=np.float64)


def apply_2d(points: np.ndarray, rot_deg: float, flip_x: bool, flip_y: bool, swap_xy: bool) -> np.ndarray:
    out = points.copy()
    if swap_xy:
        out = out[:, [1, 0]]
    if flip_x:
        out[:, 0] *= -1.0
    if flip_y:
        out[:, 1] *= -1.0
    if rot_deg:
        rad = math.radians(rot_deg)
        c, s = math.cos(rad), math.sin(rad)
        x, y = out[:, 0], out[:, 1]
        out[:, 0] = c * x - s * y
        out[:, 1] = s * x + c * y
    return out


def score_alignment(fbx: np.ndarray, sumo: np.ndarray, max_samples: int, seed: int) -> tuple[float, np.ndarray]:
    """Mean nearest-neighbour distance (metres) after optimal translation."""
    rng = random.Random(seed)
    n_f = min(len(fbx), max_samples)
    n_s = min(len(sumo), max_samples)
    f_idx = rng.sample(range(len(fbx)), n_f) if len(fbx) > n_f else list(range(len(fbx)))
    s_idx = rng.sample(range(len(sumo)), n_s) if len(sumo) > n_s else list(range(len(sumo)))
    f = fbx[f_idx]
    s = sumo[s_idx]

    t = s.mean(axis=0) - f.mean(axis=0)
    f_shifted = f + t

    try:
        from scipy.spatial import cKDTree
    except ImportError:
        # O(n^2) fallback
        dists = []
        for p in f_shifted:
            d = np.linalg.norm(s - p, axis=1).min()
            dists.append(d)
        return float(np.mean(dists)), t

    tree = cKDTree(s)
    dists, _ = tree.query(f_shifted, k=1, workers=-1)
    return float(np.mean(dists)), t


def search_best(fbx: np.ndarray, sumo: np.ndarray, max_samples: int, seed: int) -> dict:
    best = None
    rotations = (0, 90, 180, 270)
    for swap in (False, True):
        for flip_x in (False, True):
            for flip_y in (False, True):
                for rot in rotations:
                    mapped = apply_2d(fbx, rot, flip_x, flip_y, swap)
                    err, t = score_alignment(mapped, sumo, max_samples, seed)
                    cand = {
                        "mean_error_m": err,
                        "translation_xz": [float(t[0]), float(t[1])],
                        "pre_rotation_deg": rot,
                        "swap_xy": swap,
                        "flip_x": flip_x,
                        "flip_y": flip_y,
                    }
                    if best is None or err < best["mean_error_m"]:
                        best = cand
    assert best is not None
    return best


def unity_transform_from_calibration(
    fbx: np.ndarray,
    sumo: np.ndarray,
    cal: dict,
) -> dict:
    mapped = apply_2d(
        fbx,
        cal["pre_rotation_deg"],
        cal["flip_x"],
        cal["flip_y"],
        cal["swap_xy"],
    )
    # Recompute translation on full point sets for a stable centroid match.
    t = sumo.mean(axis=0) - mapped.mean(axis=0)

    # Unity imports FBX road polylines as local (fbx_x, 0, fbx_y).
    # Best fit: world.xz = (fbx_x, -fbx_y) + translation — flip FBX Y into SUMO Z.
    # Use scale Z = -1 (same as rotation X=180, easier to read in the Inspector).
    pos = {"x": float(t[0]), "y": 0.0, "z": float(t[1])}
    return {
        "position": pos,
        "rotation_euler": {"x": 0.0, "y": 0.0, "z": 0.0},
        "rotation_quaternion": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "local_scale": {"x": 1.0, "y": 1.0, "z": -1.0},
        "notes": (
            "Apply to Christchurch_Central_City_3D root. "
            "Rotation (0,0,0), Scale Z=-1, then Position — matches SUMO (x,-y)."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate FBX map vs SUMO net.xml")
    parser.add_argument(
        "--fbx",
        type=Path,
        default=root / "3D_simulation/Assets/Christchurch_Central_City_3D.fbx",
    )
    parser.add_argument(
        "--net",
        type=Path,
        default=root / "2D_simulation/data/output/network/Christchurch_Central_City_main_streets.net.xml",
    )
    parser.add_argument("--samples", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "2D_simulation/calibration_fbx_sumo.json",
    )
    args = parser.parse_args()

    fbx_pts = load_fbx_road_points(args.fbx)
    sumo_pts = load_sumo_lane_points(args.net)

    print(f"FBX road vertices: {len(fbx_pts)}")
    print(f"  X [{fbx_pts[:,0].min():.1f}, {fbx_pts[:,0].max():.1f}]  Y [{fbx_pts[:,1].min():.1f}, {fbx_pts[:,1].max():.1f}]")
    print(f"SUMO lane points: {len(sumo_pts)}")
    print(f"  X [{sumo_pts[:,0].min():.1f}, {sumo_pts[:,0].max():.1f}]  Y [{sumo_pts[:,1].min():.1f}, {sumo_pts[:,1].max():.1f}]")

    cal = search_best(fbx_pts, sumo_pts, args.samples, args.seed)
    unity = unity_transform_from_calibration(fbx_pts, sumo_pts, cal)

    out = {
        "fbx": str(args.fbx),
        "net_xml": str(args.net),
        "calibration": cal,
        "unity_transform": unity,
    }
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\nBest pre-transform on FBX local X/Y (before Unity placement):")
    print(f"  swap_xy={cal['swap_xy']} flip_x={cal['flip_x']} flip_y={cal['flip_y']} rot={cal['pre_rotation_deg']}°")
    print(f"  mean NN error: {cal['mean_error_m']:.2f} m")
    print("\nUnity Transform on map root:")
    print(f"  Position: ({unity['position']['x']:.3f}, {unity['position']['y']:.3f}, {unity['position']['z']:.3f})")
    print(f"  Scale: ({unity['local_scale']['x']}, {unity['local_scale']['y']}, {unity['local_scale']['z']})")
    print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
