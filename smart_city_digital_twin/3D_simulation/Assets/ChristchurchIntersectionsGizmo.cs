using System;
using System.IO;
using UnityEngine;

public class ChristchurchIntersectionsGizmo : MonoBehaviour
{
    [Header("Data")]
    public string geoUnityRelativePath = "Christchurch/intersection_geo_unity.json";
    [Tooltip("FBX map root (Christchurch_Central_City_3D). SUMO (x,y) = Unity (x,0,z).")]
    public Transform mapRoot;
    [Tooltip("Apply mapTransform from StreamingAssets/Christchurch/calibration.json while drawing gizmos.")]
    public bool applyMapTransform = true;

    [Header("Draw")]
    public bool draw = true;
    public float radius = 3f;
    public Color color = new Color(1f, 0f, 0f, 0.8f);
    public int maxToDraw = 500;

    [Serializable]
    class GeoUnityFile
    {
        public GeoUnityRow[] intersections;
    }

    [Serializable]
    class GeoUnityRow
    {
        public string id;
        public double X;
        public double Y;
        public double latitude;
        public double longitude;
        public bool hasSumo;
        public float sumo_x;
        public float sumo_y;
    }

    GeoUnityFile cachedGeo;
    float nextReloadTime;

    void OnDrawGizmos()
    {
        if (!draw) return;

        if (applyMapTransform)
            ChristchurchCalibration.ApplyMapTransform(mapRoot);

        if (Time.realtimeSinceStartup >= nextReloadTime)
        {
            nextReloadTime = Time.realtimeSinceStartup + 2f;
            ReloadData();
        }

        if (cachedGeo?.intersections == null) return;

        Gizmos.color = color;
        int count = Mathf.Min(maxToDraw, cachedGeo.intersections.Length);
        for (int i = 0; i < count; i++)
        {
            var it = cachedGeo.intersections[i];
            float sumoX = it.hasSumo ? it.sumo_x : 0f;
            float sumoY = it.hasSumo ? it.sumo_y : 0f;
            if (!it.hasSumo)
            {
                Vector2 fromWgs = ChristchurchCalibration.Wgs84ToSumoNetwork(it.longitude, it.latitude);
                sumoX = fromWgs.x;
                sumoY = fromWgs.y;
            }

            Vector3 p = sumoX != 0f || sumoY != 0f
                ? ChristchurchCalibration.SumoNetworkToUnityWorld(mapRoot, sumoX, sumoY, 0f)
                : ChristchurchCalibration.NztmToUnityWorld(mapRoot, it.X, it.Y, 0f);
            Gizmos.DrawSphere(p, radius);
        }
    }

    void ReloadData()
    {
        ChristchurchCalibration.InvalidateCache();
        cachedGeo = TryLoadGeo();
    }

    GeoUnityFile TryLoadGeo()
    {
        try
        {
            string path = Path.Combine(Application.streamingAssetsPath, geoUnityRelativePath);
            if (!File.Exists(path)) return null;
            return JsonUtility.FromJson<GeoUnityFile>(File.ReadAllText(path));
        }
        catch
        {
            return null;
        }
    }
}
