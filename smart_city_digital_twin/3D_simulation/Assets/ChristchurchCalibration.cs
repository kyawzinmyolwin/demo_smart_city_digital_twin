using System;
using System.IO;
using UnityEngine;

/// <summary>
/// NZTM easting/northing from intersection_geo.csv (2D X,Y) -> Unity on the FBX map.
/// TraCI: SUMO -> NZTM offset (preferred) or SUMO -> WGS84 -> NZTM.
/// </summary>
public static class ChristchurchCalibration
{
    const string RelativePath = "Christchurch/calibration.json";

    [Serializable]
    public class CalibrationFile
    {
        public NztmPlane nztmPlane;
        public Wgs84ToNztmCoeffs wgs84ToNztm;
        public SumoToNztmOffsetCoeffs sumoToNztmOffset;
        public Wgs84ToSumo wgs84ToSumo;
        public SumoToWgs84 sumoToWgs84;
        public CubeTransform cubeTransform;
        public MapTransform mapTransform;
        public VehicleSpawnerSettings vehicleSpawner;
    }

    /// <summary>SUMO network (x,y) -> NZTM plane offset (metres from nztmPlane origin).</summary>
    [Serializable]
    public class SumoToNztmOffsetCoeffs
    {
        public InvertAxis offsetX;
        public InvertAxis offsetZ;
    }

    [Serializable]
    public class NztmPlane
    {
        public double originEasting;
        public double originNorthing;
        /// <summary>WGS84 at Unity world (0, 0, z) on the NZTM grid (lat, lon).</summary>
        public double originLatitude;
        public double originLongitude;
        public string originIntersectionId;
        /// <summary>Extra Y rotation applied to the FBX map root during calibration (e.g. 180).</summary>
        public float mapYawOffsetDegrees;
        public string[] cornerIntersectionIds;
    }

    [Serializable]
    public class Wgs84ToNztmCoeffs
    {
        public SumoAxis easting;
        public SumoAxis northing;
    }

    [Serializable]
    public class Wgs84ToSumo
    {
        public SumoAxis sumoX;
        public SumoAxis sumoY;
        public int junctionPairsUsed;
    }

    [Serializable]
    public class SumoToWgs84
    {
        public InvertAxis longitude;
        public InvertAxis latitude;
    }

    [Serializable]
    public class SumoAxis
    {
        public double lon;
        public double lat;
        public double constant;
    }

    [Serializable]
    public class InvertAxis
    {
        public double sumoX;
        public double sumoY;
        public double constant;
    }

    [Serializable]
    public class CubeTransform
    {
        public float yawDegrees;
        public float translationX;
        public float translationZ;
        public float mapScaleZ = 1f;
        public float uniformScale = 1f;
    }

    [Serializable]
    public class MapTransform
    {
        public float positionX;
        public float positionY;
        public float positionZ;
        public float rotationEulerY;
        public float scaleX = 1f;
        public float scaleY = 1f;
        public float scaleZ = 1f;
        public string notes;
    }

    [Serializable]
    public class VehicleSpawnerSettings
    {
        public bool autoRecenterOnFirstVehicle;
        public Offset2 sumoPlaneManualOffset;
        public float coordinateScale;
        /// <summary>MAN A80 12 m urban bus (width, height, length) in Unity metres.</summary>
        public Scale3 busScale;
        public ColorRgba busColor;
        public string[] busTypeIds;
    }

    [Serializable]
    public class Scale3
    {
        public float x;
        public float y;
        public float z;

        public Vector3 ToVector3() => new Vector3(x, y, z);
    }

    [Serializable]
    public class ColorRgba
    {
        public float r;
        public float g;
        public float b;
        public float a = 1f;

        public Color ToColor() => new Color(r, g, b, a);
    }

    [Serializable]
    public class Offset2
    {
        public float x;
        public float y;
    }

    static CalibrationFile cached;
    static bool loadAttempted;
    static bool loggedMissingCalibration;

    public static bool TryLoad(out CalibrationFile data)
    {
        if (loadAttempted)
        {
            data = cached;
            return cached != null;
        }

        loadAttempted = true;
        string path = Path.Combine(Application.streamingAssetsPath, RelativePath);
        if (!File.Exists(path))
        {
            cached = null;
            data = null;
            return false;
        }

        try
        {
            cached = JsonUtility.FromJson<CalibrationFile>(File.ReadAllText(path));
            data = cached;
            return cached != null;
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"ChristchurchCalibration: failed to read {path}: {ex.Message}");
            cached = null;
            data = null;
            return false;
        }
    }

    public static Vector2 Wgs84ToSumoNetwork(double longitude, double latitude)
    {
        if (!TryLoad(out var cal) || cal.wgs84ToSumo == null)
            return Vector2.zero;

        var x = cal.wgs84ToSumo.sumoX;
        var y = cal.wgs84ToSumo.sumoY;
        float sumoX = (float)(x.lon * longitude + x.lat * latitude + x.constant);
        float sumoY = (float)(y.lon * longitude + y.lat * latitude + y.constant);
        return new Vector2(sumoX, sumoY);
    }

    public static Vector2 SumoNetworkToWgs84(double sumoX, double sumoY)
    {
        if (!TryLoad(out var cal) || cal.sumoToWgs84 == null)
            return Vector2.zero;

        var lonAxis = cal.sumoToWgs84.longitude;
        var latAxis = cal.sumoToWgs84.latitude;
        double lon = lonAxis.sumoX * sumoX + lonAxis.sumoY * sumoY + lonAxis.constant;
        double lat = latAxis.sumoX * sumoX + latAxis.sumoY * sumoY + latAxis.constant;
        return new Vector2((float)lon, (float)lat);
    }

    public static bool HasNztmPlane(CalibrationFile cal) => cal?.nztmPlane != null;

    public static Vector2 Wgs84ToNztm(double longitude, double latitude)
    {
        if (!TryLoad(out var cal) || cal.wgs84ToNztm == null)
            return Vector2.zero;

        var e = cal.wgs84ToNztm.easting;
        var n = cal.wgs84ToNztm.northing;
        float easting = (float)(e.lon * longitude + e.lat * latitude + e.constant);
        float northing = (float)(n.lon * longitude + n.lat * latitude + n.constant);
        return new Vector2(easting, northing);
    }

    /// <summary>
    /// NZTM offset from origin -> world (x, 0, z). Gizmos/cubes use this fixed 2D grid; the FBX map is moved to match in the Editor.
    /// </summary>
    public static Vector3 NztmOffsetToWorld(Transform mapRoot, float nx, float nz, float height)
    {
        if (mapRoot != null && mapRoot.parent != null)
            return mapRoot.parent.TransformPoint(nx, height, nz);
        return new Vector3(nx, height, nz);
    }

    /// <summary>
    /// 2D intersection_geo.csv (X,Y) NZTM metres -> Unity world (x, 0, z).
    /// </summary>
    public static Vector3 NztmToUnityWorld(Transform mapRoot, double easting, double northing, float height)
    {
        if (!TryLoad(out var cal) || !HasNztmPlane(cal))
            return new Vector3((float)easting, height, (float)northing);

        float nx = (float)(easting - cal.nztmPlane.originEasting);
        float nz = (float)(northing - cal.nztmPlane.originNorthing);
        return NztmOffsetToWorld(mapRoot, nx, nz, height);
    }

    /// <summary>Map-local XZ for a point on the NZTM grid (used when aligning the FBX in the Editor).</summary>
    public static Vector2 NztmOffsetToMapLocal(float nx, float nz, Transform mapRoot, CubeTransform cubeFallback = null)
    {
        if (mapRoot == null)
            return new Vector2(nx, nz);

        Vector3 world = NztmOffsetToWorld(mapRoot, nx, nz, 0f);
        Vector3 local = mapRoot.InverseTransformPoint(world);
        return new Vector2(local.x, local.z);
    }

    /// <summary>SUMO network (x,y) -> Unity grid offset (x, z); identity when calibrated to SUMO grid.</summary>
    public static Vector2 SumoToNztmOffset(double sumoX, double sumoY)
    {
        if (!TryLoad(out var cal) || cal.sumoToNztmOffset == null)
            return Vector2.zero;

        var ox = cal.sumoToNztmOffset.offsetX;
        var oz = cal.sumoToNztmOffset.offsetZ;
        if (ox == null || oz == null)
            return Vector2.zero;

        float nx = (float)(ox.sumoX * sumoX + ox.sumoY * sumoY + ox.constant);
        float nz = (float)(oz.sumoX * sumoX + oz.sumoY * sumoY + oz.constant);
        return new Vector2(nx, nz);
    }

    /// <summary>Clear cached calibration.json (e.g. after re-running an Editor calibrator).</summary>
    public static void InvalidateCache()
    {
        loadAttempted = false;
        cached = null;
        loggedMissingCalibration = false;
    }

    /// <summary>WGS84 -> NZTM -> Unity world on the map.</summary>
    public static Vector3 Wgs84ToUnityWorld(Transform mapRoot, double longitude, double latitude, float height)
    {
        if (!TryLoad(out var cal) || !HasNztmPlane(cal) || cal.wgs84ToNztm == null)
        {
            LogMissingCalibrationOnce();
            return Vector3.zero;
        }

        Vector2 nztm = Wgs84ToNztm(longitude, latitude);
        return NztmToUnityWorld(mapRoot, nztm.x, nztm.y, height);
    }

    /// <summary>
    /// TraCI SUMO (x,y) -> lon/lat -> map world. Does not use raw SUMO as Unity XZ when calibration is present.
    /// </summary>
    public static Vector3 SumoNetworkToUnityWorld(Transform mapRoot, double sumoX, double sumoY, float height)
    {
        if (!TryLoad(out var cal) || !HasNztmPlane(cal))
        {
            LogMissingCalibrationOnce();
            return new Vector3((float)sumoX, height, (float)sumoY);
        }

        if (cal.sumoToNztmOffset != null)
        {
            Vector2 grid = SumoToNztmOffset(sumoX, sumoY);
            return NztmOffsetToWorld(mapRoot, grid.x, grid.y, height);
        }

        if (cal.sumoToWgs84 != null || cal.wgs84ToSumo != null)
        {
            Vector2 wgs = cal.sumoToWgs84 != null
                ? SumoNetworkToWgs84(sumoX, sumoY)
                : SumoNetworkToWgs84FromForwardOnly(sumoX, sumoY);
            return Wgs84ToUnityWorld(mapRoot, wgs.x, wgs.y, height);
        }

        LogMissingCalibrationOnce();
        return new Vector3((float)sumoX, height, (float)sumoY);
    }

    static void LogMissingCalibrationOnce()
    {
        if (loggedMissingCalibration) return;
        loggedMissingCalibration = true;
        Debug.LogError(
            "ChristchurchCalibration: missing or incomplete calibration.json (nztmPlane / sumoToNztmOffset).\n" +
            "Ensure StreamingAssets/Christchurch/calibration.json is present, then Play again.");
    }

    static Vector2 SumoNetworkToWgs84FromForwardOnly(double sumoX, double sumoY)
    {
        if (!TryLoad(out var cal) || cal.wgs84ToSumo == null)
            return Vector2.zero;

        var ax = cal.wgs84ToSumo.sumoX;
        var ay = cal.wgs84ToSumo.sumoY;
        double sx = sumoX - ax.constant;
        double sy = sumoY - ay.constant;
        double det = ax.lon * ay.lat - ax.lat * ay.lon;
        if (Math.Abs(det) < 1e-12)
            return Vector2.zero;

        double lon = (sx * ay.lat - ax.lat * sy) / det;
        double lat = (ax.lon * sy - sx * ay.lon) / det;
        return new Vector2((float)lon, (float)lat);
    }

    public static void ApplySpawnerDefaults(SumoVehicleSpawner spawner)
    {
        if (spawner == null || !TryLoad(out var cal) || cal.vehicleSpawner == null)
            return;

        spawner.autoRecenterOnFirstVehicle = cal.vehicleSpawner.autoRecenterOnFirstVehicle;
        spawner.sumoPlaneManualOffset = new Vector2(
            cal.vehicleSpawner.sumoPlaneManualOffset.x,
            cal.vehicleSpawner.sumoPlaneManualOffset.y);
        spawner.coordinateScale = cal.vehicleSpawner.coordinateScale;

        if (cal.vehicleSpawner.busScale != null)
            spawner.busScale = cal.vehicleSpawner.busScale.ToVector3();
        if (cal.vehicleSpawner.busColor != null)
            spawner.busColor = cal.vehicleSpawner.busColor.ToColor();
        if (cal.vehicleSpawner.busTypeIds != null && cal.vehicleSpawner.busTypeIds.Length > 0)
            spawner.busTypeIds = cal.vehicleSpawner.busTypeIds;
    }

    public static void ApplyMapTransform(Transform mapRoot)
    {
        if (mapRoot == null || !TryLoad(out var cal) || cal.mapTransform == null)
            return;

        mapRoot.localPosition = new Vector3(
            cal.mapTransform.positionX,
            cal.mapTransform.positionY,
            cal.mapTransform.positionZ);
        mapRoot.localRotation = Quaternion.Euler(0f, cal.mapTransform.rotationEulerY, 0f);
        mapRoot.localScale = new Vector3(
            cal.mapTransform.scaleX,
            cal.mapTransform.scaleY,
            cal.mapTransform.scaleZ);
    }
}
