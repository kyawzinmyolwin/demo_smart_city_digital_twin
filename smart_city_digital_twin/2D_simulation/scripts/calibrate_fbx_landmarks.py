#!/usr/bin/env python3
"""
Calibrate FBX map vs SUMO using Christchurch landmarks.

1. SUMO XY for landmarks: WGS84 -> net XY (junction regression on osm.xml + net.xml).
2. FBX local XY: snap each landmark to nearest road mesh vertex (map_4.osm_roads_*).
3. Solve 2D similarity (yaw + translation + optional Z flip) from landmark pairs.
"""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from _sim_root import PROJECT_ROOT as root

try:
    import ufbx
except ImportError as e:
    raise SystemExit("pip install ufbx") from e


LANDMARKS_WGS84: list[tuple[str, float, float]] = [
    ("ChristChurch Cathedral", 172.6378899, -43.5310073),
    ("Cathedral Square", 172.6356666, -43.5308537),
    ("Victoria Square", 172.6363273, -43.5287022),
    ("Bus Interchange", 172.6376917, -43.5342022),
    ("Te Kaha stadium", 172.6422, -43.5330),
    ("The Arts Centre", 172.6278, -43.5316),
    ("Christchurch Hospital", 172.6215, -43.5345),
]


def fit_wgs84_to_sumo(net_path: Path, osm_path: Path) -> tuple[np.ndarray, np.ndarray]:
    juncs: dict[str, tuple[float, float]] = {}
    for j in ET.parse(net_path).getroot().findall("junction"):
        if j.get("type") == "internal":
            continue
        juncs[j.get("id")] = (float(j.get("x")), float(j.get("y")))

    nodes: dict[str, tuple[float, float]] = {}
    for n in ET.parse(osm_path).getroot().findall("node"):
        nodes[n.get("id")] = (float(n.get("lon")), float(n.get("lat")))

    pairs = [(nodes[j][0], nodes[j][1], xy[0], xy[1]) for j, xy in juncs.items() if j in nodes]
    a = np.column_stack([np.array(pairs)[:, 0], np.array(pairs)[:, 1], np.ones(len(pairs))])
    cx, _, _, _ = np.linalg.lstsq(a, np.array(pairs)[:, 2], rcond=None)
    cy, _, _, _ = np.linalg.lstsq(a, np.array(pairs)[:, 3], rcond=None)
    return cx, cy


def wgs_to_sumo(lon: float, lat: float, cx: np.ndarray, cy: np.ndarray) -> np.ndarray:
    v = np.array([lon, lat, 1.0])
    return np.array([float(v @ cx), float(v @ cy)])


def load_osm_nodes(osm_map: Path) -> dict[str, tuple[float, float]]:
    nodes: dict[str, tuple[float, float]] = {}
    for ev, el in ET.iterparse(osm_map, events=("end",)):
        if el.tag == "node":
            nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
        el.clear()
    return nodes


def te_kaha_centroid(osm_map: Path, nodes: dict[str, tuple[float, float]]) -> tuple[float, float]:
    for el in ET.parse(osm_map).getroot().iter("way"):
        name = next((t.get("v") for t in el.findall("tag") if t.get("k") == "name"), None)
        if name != "Te Kaha":
            continue
        pts = [nodes[r] for r in (nd.get("ref") for nd in el.findall("nd")) if r in nodes]
        if pts:
            return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return 172.6422, -43.5330


def load_fbx_road_vertices(fbx_path: Path) -> np.ndarray:
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
        raise RuntimeError("No road meshes in FBX")
    return np.asarray(pts, dtype=np.float64)


def snap_road(roads: np.ndarray, fbx_xy: np.ndarray) -> np.ndarray:
    d = np.linalg.norm(roads - fbx_xy, axis=1)
    return roads[int(np.argmin(d))]


def similarity_fit(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, float]:
    src_m, dst_m = src.mean(0), dst.mean(0)
    src_c, dst_c = src - src_m, dst - dst_m
    h = src_c.T @ dst_c
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T
    var = (src_c**2).sum()
    scale = float(np.trace(r @ h) / var) if var > 1e-9 else 1.0
    t = dst_m - scale * (r @ src_m)
    yaw = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return scale, r, t, yaw


def try_transforms(fbx_pts: np.ndarray, sumo_pts: np.ndarray) -> dict:
    """Pick best among yaw-only and flip variants (Unity-friendly)."""
    candidates: list[dict] = []

    for flip_z in (False, True):
        src = fbx_pts.copy()
        if flip_z:
            src[:, 1] *= -1.0
        for yaw in range(-180, 181, 5):
            rad = math.radians(yaw)
            c, s = math.cos(rad), math.sin(rad)
            rot = np.array([[c, -s], [s, c]])
            rotated = src @ rot.T
            t = sumo_pts.mean(0) - rotated.mean(0)
            pred = rotated + t
            err = np.linalg.norm(pred - sumo_pts, axis=1)
            candidates.append(
                {
                    "mean_m": float(err.mean()),
                    "max_m": float(err.max()),
                    "yaw": float(yaw),
                    "flip_z": flip_z,
                    "position": [float(t[0]), float(t[1])],
                    "per_landmark_m": err.tolist(),
                }
            )

    best = min(candidates, key=lambda c: c["mean_m"])
    pos = best["position"]
    unity = {
        "position": {"x": pos[0], "y": 0.0, "z": pos[1]},
        "rotation_euler": {"x": 0.0, "y": best["yaw"], "z": 0.0},
        "rotation_quaternion": {
            "x": 0.0,
            "y": math.sin(math.radians(best["yaw"]) / 2.0),
            "z": 0.0,
            "w": math.cos(math.radians(best["yaw"]) / 2.0),
        },
        "local_scale": {"x": 1.0, "y": 1.0, "z": -1.0 if best["flip_z"] else 1.0},
    }
    return {"best": best, "unity_transform": unity}


def main() -> None:
    parser = argparse.ArgumentParser()
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
    parser.add_argument(
        "--osm-net",
        type=Path,
        default=root / "2D_simulation/data/output/network/Christchurch_Central_City_main_streets.osm.xml",
    )
    parser.add_argument(
        "--osm-map",
        type=Path,
        default=root / "2D_simulation/data/output/network/Christchurch_Central_City.osm.xml",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=root / "2D_simulation/calibration_fbx_landmarks.json",
    )
    args = parser.parse_args()

    cx, cy = fit_wgs84_to_sumo(args.net, args.osm_net)
    osm_nodes = load_osm_nodes(args.osm_map)
    tk_lon, tk_lat = te_kaha_centroid(args.osm_map, osm_nodes)

    landmarks = []
    for name, lon, lat in LANDMARKS_WGS84:
        if name.startswith("Te Kaha"):
            lon, lat = tk_lon, tk_lat
        landmarks.append((name, lon, lat))

    roads = load_fbx_road_vertices(args.fbx)

    # Initial inverse from previous road calibration: sumo ≈ (fx, -fy) + t0
    t0 = np.array([1257.71, 1220.55])

    sumo_pts: list[np.ndarray] = []
    fbx_pts: list[np.ndarray] = []
    rows: list[dict] = []

    for name, lon, lat in landmarks:
        s = wgs_to_sumo(lon, lat, cx, cy)
        guess_fbx = np.array([s[0] - t0[0], -(s[1] - t0[1])])
        f = snap_road(roads, guess_fbx)
        sumo_pts.append(s)
        fbx_pts.append(f)
        rows.append(
            {
                "name": name,
                "wgs84": {"lon": lon, "lat": lat},
                "sumo_xy": [float(s[0]), float(s[1])],
                "fbx_road_xy": [float(f[0]), float(f[1])],
            }
        )

    src = np.asarray(fbx_pts)
    dst = np.asarray(sumo_pts)
    fit = try_transforms(src, dst)
    best = fit["best"]
    per = best["per_landmark_m"]

    out = {
        "method": "landmark_road_snap",
        "landmarks": [
            {**r, "residual_m": per[i]} for i, r in enumerate(rows)
        ],
        "mean_residual_m": best["mean_m"],
        "max_residual_m": best["max_m"],
        "unity_transform": fit["unity_transform"],
    }
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"Landmarks: {len(landmarks)}  mean error {best['mean_m']:.1f} m  max {best['max_m']:.1f} m")
    for r, res in zip(rows, per):
        print(f"  {r['name']:28s}  {res:6.1f} m")
    u = fit["unity_transform"]
    p = u["position"]
    print(f"\nUnity: Position ({p['x']:.2f}, 0, {p['z']:.2f})  Rotation Y={u['rotation_euler']['y']:.1f}°  Scale Z={u['local_scale']['z']}")
    print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
