#!/usr/bin/env python3
"""
Option C: geometry-based calibration (ICP) between:
- SUMO lane centrelines (lane @shape) from Christchurch_Central_City_main_streets.net.xml
- FBX road mesh vertices (map_4.osm_roads_*) from Christchurch_Central_City_3D.fbx

Solves a 2D similarity transform (scale + rotation + translation) and allows mirror/reflection.

Outputs:
- 3D_simulation/Assets/StreamingAssets/Christchurch/calibration.json
- optional: patch SampleScene.unity map transform

Usage:
  python3 calibrate_christchurch_icp.py --map-scale-z 1 --update-scene
  python3 calibrate_christchurch_icp.py --map-scale-z 1 --cubes-only
"""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from _sim_root import PROJECT_ROOT as root

try:
    import ufbx
except ImportError as e:
    raise SystemExit("pip install ufbx") from e


@dataclass
class Similarity2D:
    scale: float
    rot: np.ndarray  # 2x2
    trans: np.ndarray  # (2,)
    reflection: bool


def parse_conv_boundary(net_path: Path) -> tuple[float, float, float, float]:
    root = ET.parse(net_path).getroot()
    loc = root.find("location")
    if loc is None:
        raise RuntimeError("No <location> in net.xml")
    cb = loc.get("convBoundary")
    if not cb:
        raise RuntimeError("No convBoundary")
    x0, y0, x1, y1 = [float(x) for x in cb.split(",")]
    return x0, y0, x1, y1


def load_sumo_lane_samples(net_path: Path, step_m: float, max_points: int) -> np.ndarray:
    # Sample points along each lane polyline in shape="x,y x,y ..."
    pts: list[tuple[float, float]] = []
    root = ET.parse(net_path).getroot()
    for lane in root.iter("lane"):
        shape = lane.get("shape")
        if not shape:
            continue
        coords = []
        for tok in shape.split():
            x, y = tok.split(",")
            coords.append((float(x), float(y)))
        if len(coords) < 2:
            continue
        # sample along segments
        for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
            dx, dy = x1 - x0, y1 - y0
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-6:
                continue
            n = max(1, int(seg_len / step_m))
            for i in range(n + 1):
                t = i / n
                pts.append((x0 + dx * t, y0 + dy * t))
                if len(pts) >= max_points:
                    return np.asarray(pts, dtype=np.float64)
    return np.asarray(pts, dtype=np.float64)


def load_fbx_road_vertices(fbx_path: Path, max_points: int, seed: int) -> np.ndarray:
    scene = ufbx.load_file(str(fbx_path))
    pts: list[tuple[float, float]] = []
    for node in scene.nodes:
        if not node.mesh:
            continue
        name = node.mesh.name or node.name or ""
        if "osm_roads_" not in name:
            continue
        for v in node.mesh.vertices:
            pts.append((float(v.x), float(v.y)))
    if not pts:
        raise RuntimeError("No osm_roads vertices in FBX")
    arr = np.asarray(pts, dtype=np.float64)
    if len(arr) <= max_points:
        return arr
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(arr), size=max_points, replace=False)
    return arr[idx]


def fit_similarity_allow_reflection(src: np.ndarray, dst: np.ndarray, weights: np.ndarray | None = None) -> Similarity2D:
    """
    Umeyama-like similarity fit with optional reflection.
    src, dst: Nx2
    """
    if weights is None:
        w = np.ones(len(src), dtype=np.float64)
    else:
        w = weights.astype(np.float64)
    w = w / w.sum()

    mu_src = (src * w[:, None]).sum(axis=0)
    mu_dst = (dst * w[:, None]).sum(axis=0)
    xs = src - mu_src
    yd = dst - mu_dst

    cov = (xs * w[:, None]).T @ yd
    u, s, vt = np.linalg.svd(cov)
    r = vt.T @ u.T
    reflection = False
    if np.linalg.det(r) < 0:
        reflection = True
        vt[-1, :] *= -1
        r = vt.T @ u.T

    var = (w[:, None] * (xs ** 2)).sum()
    scale = float(np.trace(np.diag(s)) / var) if var > 1e-12 else 1.0
    t = mu_dst - scale * (r @ mu_src)
    return Similarity2D(scale=scale, rot=r, trans=t, reflection=reflection)


def apply_sim(sim: Similarity2D, pts: np.ndarray) -> np.ndarray:
    return (sim.scale * (pts @ sim.rot.T)) + sim.trans


def nearest_neighbors_bruteforce(src: np.ndarray, dst: np.ndarray, chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """
    For each point in src, find nearest in dst. Returns (indices, distances).
    Bruteforce but chunked; OK for downsampled point clouds.
    """
    idx = np.empty(len(src), dtype=np.int64)
    dist = np.empty(len(src), dtype=np.float64)
    for i0 in range(0, len(src), chunk):
        a = src[i0 : i0 + chunk]
        # (m,1,2) - (1,n,2) -> (m,n,2)
        d2 = ((a[:, None, :] - dst[None, :, :]) ** 2).sum(axis=2)
        j = np.argmin(d2, axis=1)
        idx[i0 : i0 + len(a)] = j
        dist[i0 : i0 + len(a)] = np.sqrt(d2[np.arange(len(a)), j])
    return idx, dist


def icp_similarity(
    sumo_pts: np.ndarray,
    fbx_pts: np.ndarray,
    *,
    iters: int,
    trim_fraction: float,
    seed: int,
    initial_yaw_deg: float,
    initial_trans: tuple[float, float],
    allow_reflection: bool,
) -> tuple[Similarity2D, dict]:
    # We solve: sumo ≈ sim( fbx_local )
    yaw = math.radians(initial_yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    r0 = np.array([[c, -s], [s, c]], dtype=np.float64)
    sim = Similarity2D(scale=1.0, rot=r0, trans=np.array(initial_trans, dtype=np.float64), reflection=False)

    history = []
    for k in range(iters):
        moved = apply_sim(sim, fbx_pts)
        nn_idx, nn_dist = nearest_neighbors_bruteforce(moved, sumo_pts)

        # Trim outliers
        n_keep = max(50, int(len(nn_dist) * trim_fraction))
        keep = np.argpartition(nn_dist, n_keep)[:n_keep]
        src_keep = fbx_pts[keep]
        dst_keep = sumo_pts[nn_idx[keep]]

        # Fit similarity (optionally allow reflection). If reflection is not allowed, we can flip back by forcing det>0.
        sim_new = fit_similarity_allow_reflection(src_keep, dst_keep)
        if not allow_reflection and sim_new.reflection:
            # Refit forcing no reflection by removing the det<0 fix:
            # easiest: just ignore and keep previous rotation, only update translation.
            sim_new = Similarity2D(scale=sim_new.scale, rot=sim.rot, trans=sim_new.trans, reflection=False)

        moved2 = apply_sim(sim_new, fbx_pts)
        _, dist2 = nearest_neighbors_bruteforce(moved2, sumo_pts)
        history.append(
            {
                "iter": k,
                "mean_m": float(dist2.mean()),
                "median_m": float(np.median(dist2)),
                "p90_m": float(np.quantile(dist2, 0.9)),
                "scale": float(sim_new.scale),
                "det": float(np.linalg.det(sim_new.rot)),
            }
        )
        sim = sim_new
    return sim, {"history": history}


def patch_scene(scene_path: Path, *, pos_x: float, pos_z: float, rot_y_deg: float, scale_z: float) -> None:
    text = scene_path.read_text(encoding="utf-8")
    qy = math.sin(math.radians(rot_y_deg) / 2.0)
    qw = math.cos(math.radians(rot_y_deg) / 2.0)
    replacements = [
        (r"(propertyPath: m_LocalPosition\.x\n\s+value: )[-\d.]+", f"\\g<1>{pos_x:.4f}"),
        (r"(propertyPath: m_LocalPosition\.z\n\s+value: )[-\d.]+", f"\\g<1>{pos_z:.4f}"),
        (r"(propertyPath: m_LocalRotation\.w\n\s+value: )[-\d.]+", f"\\g<1>{qw:.8f}"),
        (r"(propertyPath: m_LocalRotation\.y\n\s+value: )[-\d.]+", f"\\g<1>{qy:.8f}"),
        (r"(propertyPath: m_LocalRotation\.x\n\s+value: )[-\d.]+", "\\g<1>0"),
        (r"(propertyPath: m_LocalRotation\.z\n\s+value: )[-\d.]+", "\\g<1>0"),
        (r"(propertyPath: m_LocalScale\.z\n\s+value: )[-\d.]+", f"\\g<1>{scale_z:.1f}"),
        (r"(propertyPath: m_LocalEulerAnglesHint\.y\n\s+value: )[-\d.]+", f"\\g<1>{rot_y_deg:.1f}"),
    ]
    for pat, repl in replacements:
        text, _ = re.subn(pat, repl, text, count=1)
    scene_path.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fbx", type=Path, default=root / "3D_simulation/Assets/Christchurch_Central_City_3D.fbx")
    ap.add_argument("--net", type=Path, default=root / "2D_simulation/data/output/network/Christchurch_Central_City_main_streets.net.xml")
    ap.add_argument("--scene", type=Path, default=root / "3D_simulation/Assets/Scenes/SampleScene.unity")
    ap.add_argument("--json-out", type=Path, default=root / "3D_simulation/Assets/StreamingAssets/Christchurch/calibration.json")
    ap.add_argument("--update-scene", action="store_true")
    ap.add_argument("--cubes-only", action="store_true")
    ap.add_argument("--map-scale-z", type=float, default=1.0)
    ap.add_argument("--sumo-step-m", type=float, default=7.0)
    ap.add_argument("--sumo-max", type=int, default=25000)
    ap.add_argument("--fbx-max", type=int, default=25000)
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--trim", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    x0, y0, x1, y1 = parse_conv_boundary(args.net)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    sumo_pts = load_sumo_lane_samples(args.net, step_m=args.sumo_step_m, max_points=args.sumo_max)
    fbx_pts = load_fbx_road_vertices(args.fbx, max_points=args.fbx_max, seed=args.seed)

    # Initial: align centroids, no rotation
    initial_trans = (cx - fbx_pts[:, 0].mean(), cy - fbx_pts[:, 1].mean())
    sim, dbg = icp_similarity(
        sumo_pts,
        fbx_pts,
        iters=args.iters,
        trim_fraction=args.trim,
        seed=args.seed,
        initial_yaw_deg=0.0,
        initial_trans=initial_trans,
        allow_reflection=True,
    )

    # Convert sim (sumo ≈ s*R*fbx + t) into Unity-friendly map root parameters.
    # We keep map scale Z forced by user (usually 1). We only output yaw+translation and a uniform scale estimate.
    yaw_deg = math.degrees(math.atan2(sim.rot[1, 0], sim.rot[0, 0]))
    pos_x, pos_z = float(sim.trans[0]), float(sim.trans[1])
    uniform_scale = float(sim.scale)

    out = {
        "description": "ICP geometry calibration (SUMO lane shapes vs FBX road vertices).",
        "source": {
            "net": str(args.net),
            "fbx": str(args.fbx),
            "sumo_points": int(len(sumo_pts)),
            "fbx_points": int(len(fbx_pts)),
        },
        "icp": {
            "iterations": args.iters,
            "trim_fraction": args.trim,
            "history": dbg["history"],
        },
        "unityMapTransform": {
            "position": {"x": pos_x, "y": 0.0, "z": pos_z},
            "rotation_euler": {"x": 0.0, "y": yaw_deg, "z": 0.0},
            "rotation_quaternion": {
                "x": 0.0,
                "y": math.sin(math.radians(yaw_deg) / 2.0),
                "z": 0.0,
                "w": math.cos(math.radians(yaw_deg) / 2.0),
            },
            "local_scale": {"x": uniform_scale, "y": 1.0, "z": float(args.map_scale_z)},
            "reflection": bool(sim.reflection),
        },
        "cubeTransform": {
            "yawDegrees": yaw_deg,
            "translationX": pos_x,
            "translationZ": pos_z,
            "mapScaleZ": float(args.map_scale_z),
            "uniformScale": uniform_scale,
        },
        "vehicleSpawner": {
            "autoRecenterOnFirstVehicle": False,
            "sumoPlaneManualOffset": {"x": 0.0, "y": 0.0},
            "coordinateScale": 1.0,
        },
    }

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    if args.update_scene and not args.cubes_only:
        patch_scene(args.scene, pos_x=pos_x, pos_z=pos_z, rot_y_deg=yaw_deg, scale_z=float(args.map_scale_z))

    print(f"SUMO pts: {len(sumo_pts)}  FBX pts: {len(fbx_pts)}")
    print(f"ICP final: yaw={yaw_deg:.2f}°  pos=({pos_x:.2f},{pos_z:.2f})  scale={uniform_scale:.4f}  reflection={sim.reflection}")
    print(f"Wrote {args.json_out}")
    if args.update_scene and not args.cubes_only:
        print(f"Updated {args.scene}")


if __name__ == "__main__":
    main()

