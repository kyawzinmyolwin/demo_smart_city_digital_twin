using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.Sockets;
using TraciConnector.Protocol;
using TraciConnector.Tudresden.Sumo.Cmd;
using TraciConnector.Tudresden.Sumo.Conf;
using TraciConnector.Tudresden.Sumo.Util;
using TraciConnector.Tudresden.Ws.Container;
using UnityEngine;

public class SumoVehicleSpawner : MonoBehaviour
{
    const string LastGoodServerIpPrefKey = "SumoVehicleSpawner.LastGoodServerIP";

    [Header("TraCI (SUMO server)")]
    [Tooltip("127.0.0.1 if SUMO runs on this Mac. If SUMO runs in VMware Windows, set to the VM IP from ipconfig.")]
    public string serverIP = "127.0.0.1";
    public int serverPort = 8813;
    public int connectRetries = 60;
    public float connectRetryIntervalSeconds = 0.5f;

    [Header("Simulation")]
    [Tooltip("Match SUMO step-length in your .sumocfg (area.sumocfg uses 0.05).")]
    public float stepLengthSeconds = 0.05f;

    [Header("Vehicle visuals")]
    [Tooltip("If set, vehicles spawn from this prefab (e.g. a car model). If null, spawns cubes.")]
    public GameObject vehiclePrefab;
    [Tooltip("Local scale applied to spawned prefab instances (ignored for cubes).")]
    public Vector3 prefabScale = Vector3.one;

    [Header("Vehicle cubes (fallback)")]
    public Vector3 cubeScale = new Vector3(1f, 1f, 2f);
    public float cubeYOffset = 0.5f;
    [Tooltip("Colour for spawned vehicle cubes (URP Base Color + legacy Albedo).")]
    public Color cubeColor = Color.yellow;
    [Header("Bus cubes (Christchurch Metro)")]
    [Tooltip("MAN A80 12 m urban bus size in metres: X=width, Y=height, Z=length (local +Z = forward).")]
    public Vector3 busScale = new Vector3(2.5f, 3.4f, 12f);
    [Tooltip("Christchurch Metro network teal (approx. #008C9A).")]
    public Color busColor = new Color(0f, 140f / 255f, 154f / 255f, 1f);
    [Tooltip("SUMO vType ids treated as buses (e.g. bus in .rou.xml).")]
    public string[] busTypeIds = { "bus" };
    [Tooltip("If enabled, vehicles rotate to face their driving direction.")]
    public bool orientVehiclesToMovement = true;
    [Tooltip("Use SUMO TraCI heading when movement is too small to infer direction.")]
    public bool useSumoVehicleAngle = true;
    [Tooltip("Extra degrees added to SUMO angle if the mesh faces the wrong way.")]
    public float sumoAngleOffsetDegrees = 0f;
    [Tooltip("Fallback only when useSumoVehicleAngle is off: rotation speed (deg/s).")]
    public float rotationSpeedDegPerSec = 720f;
    [Tooltip("Fallback only: minimum movement before updating rotation from displacement.")]
    public float minMoveDistanceForRotation = 0.01f;
    [Tooltip("Below this SUMO speed (m/s), a vehicle is treated as stopped.")]
    public float stationarySpeedThreshold = 0.1f;
    [Tooltip("Leave OFF for Christchurch: cubes use lat/lon via calibration.json, not raw SUMO X/Y as world position.")]
    public bool autoRecenterOnFirstVehicle = false;
    [Tooltip("If enabled, jumps Main Camera once when the first SUMO vehicle appears (usually leave off).")]
    public bool snapMainCameraOnFirstRecenter = false;
    public Vector2 sumoPlaneManualOffset = Vector2.zero;
    public float coordinateScale = 1f;

    Socket socket;
    CommandProcessor commandProcessor;
    bool traciReady;
    float nextStepTime;

    double recenterSumoX;
    double recenterSumoY;
    bool recenterApplied;
    bool mainCameraSnapped;
    bool loggedEmptyVehicleHint;
    bool loggedFirstVehicle;
    float nextStatusLogTime;
    bool isConnecting;

    [Header("Christchurch calibration")]
    [Tooltip("FBX map root — vehicles are placed via lon/lat on this transform, not raw SUMO X/Y.")]
    public Transform mapRoot;
    [Tooltip("Apply vehicle_spawner settings from StreamingAssets/Christchurch/calibration.json on Start.")]
    public bool applyChristchurchCalibrationOnStart = true;
    [Tooltip("Apply mapTransform from StreamingAssets/Christchurch/calibration.json on Start.")]
    public bool applyMapTransformOnStart = true;

    [Header("Debug")]
    [Tooltip("Every 5s while Play is running, log how many vehicles TraCI reports.")]
    public bool logVehicleCountPeriodically = true;

    readonly Dictionary<string, GameObject> activeVehicles = new Dictionary<string, GameObject>();
    readonly Dictionary<string, Vector3> lastVehiclePositions = new Dictionary<string, Vector3>();
    readonly Dictionary<string, Vector3> lastVehicleForwards = new Dictionary<string, Vector3>();
    readonly Dictionary<string, SumoGeometry> laneShapeCache = new Dictionary<string, SumoGeometry>();

    void Start()
    {
        ChristchurchCalibration.InvalidateCache();
        if (applyChristchurchCalibrationOnStart)
            ChristchurchCalibration.ApplySpawnerDefaults(this);
        if (applyMapTransformOnStart)
            ChristchurchCalibration.ApplyMapTransform(mapRoot);
        // If you previously connected to a VM IP, prefer that over 127.0.0.1 on Mac.
        if (serverIP == "127.0.0.1")
        {
            string lastGood = PlayerPrefs.GetString(LastGoodServerIpPrefKey, "");
            if (!string.IsNullOrWhiteSpace(lastGood) && lastGood != "127.0.0.1")
            {
                serverIP = lastGood;
                Debug.Log($"Using remembered SUMO server IP: {serverIP}:{serverPort}");
            }
        }

        StartCoroutine(ConnectToSumoRoutine());
    }

    IEnumerator ConnectToSumoRoutine()
    {
        if (isConnecting) yield break;
        isConnecting = true;

        Exception lastError = null;

        for (int attempt = 1; attempt <= connectRetries; attempt++)
        {
            if (TryOpenTcpSocket(out lastError))
            {
                try
                {
                    CompleteTraCIHandshake();
                    traciReady = true;
                    nextStepTime = Time.realtimeSinceStartup;
                    nextStatusLogTime = Time.realtimeSinceStartup + 5f;
                    Debug.Log($"TraCI ready on {serverIP}:{serverPort} (TCP attempt {attempt}).");
                    if (!string.IsNullOrWhiteSpace(serverIP))
                    {
                        PlayerPrefs.SetString(LastGoodServerIpPrefKey, serverIP);
                        PlayerPrefs.Save();
                    }
                    isConnecting = false;
                    yield break;
                }
                catch (Exception ex)
                {
                    Debug.LogError("TraCI handshake failed: " + ex.Message);
                    CloseSocket();
                }
            }

            if (attempt == connectRetries)
            {
                Debug.LogError(
                    "Could not connect to SUMO: " + lastError?.Message +
                    $"\nNo TraCI server at {serverIP}:{serverPort}." +
                    "\n• Same Mac: serverIP = 127.0.0.1, run: sumo-gui -c area.sumocfg --remote-port " + serverPort + " --start" +
                    "\n• VMware Windows: serverIP = VM IP; allow TCP " + serverPort + " in Windows Firewall.");
                isConnecting = false;
                yield break;
            }

            if (attempt == 1 || attempt % 10 == 0)
            {
                string vmHint = serverIP == "127.0.0.1"
                    ? " (127.0.0.1 is this Mac only — if SUMO runs in VMware Windows, set Server IP to the VM IPv4 from ipconfig)"
                    : "";
                Debug.LogWarning($"Waiting for SUMO on {serverIP}:{serverPort} ({attempt}/{connectRetries})...{vmHint}");
            }

            yield return new WaitForSeconds(connectRetryIntervalSeconds);
        }

        isConnecting = false;
    }

    bool TryOpenTcpSocket(out Exception error)
    {
        CloseSocket();
        error = null;

        try
        {
            socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp)
            {
                NoDelay = true
            };
            socket.Connect(serverIP, serverPort);
            return true;
        }
        catch (Exception e)
        {
            error = e;
            CloseSocket();
            return false;
        }
    }

    /// <summary>
    /// One NetworkStream per socket only (see TraciLibrary Query.cs). Handshake must use the same
    /// stream CommandProcessor will use, or SUMO often logs "peer shutdown" and Unity gets cast errors.
    /// </summary>
    void CompleteTraCIHandshake()
    {
        socket.ReceiveTimeout = 0;
        socket.SendTimeout = 0;

        commandProcessor = new CommandProcessor(socket);
        TraCIHandshake.PerformGetVersion(commandProcessor.GetOutStream());

        socket.ReceiveTimeout = 10000;
        socket.SendTimeout = 10000;
    }

    void Update()
    {
        if (!traciReady || commandProcessor == null || socket == null || !socket.Connected)
            return;

        if (Time.realtimeSinceStartup < nextStepTime)
            return;

        nextStepTime += stepLengthSeconds;

        try
        {
            commandProcessor.Do_job_set(new SumoCommand(Constants.CMD_SIMSTEP2, 0.0));

            if (FetchSumoVehicleData(out List<SumoVehicleData> vehicles))
                UpdateSceneCubes(vehicles);
        }
        catch (Exception ex)
        {
            Debug.LogError(
                "TraCI step failed: " + ex.Message +
                "\nIf SUMO shows 'peer shutdown', restart SUMO then Play Unity (one client on port " + serverPort + ")." +
                "\n" + ex);
            traciReady = false;
            CloseSocket();
        }
    }

    bool FetchSumoVehicleData(out List<SumoVehicleData> dataList)
    {
        dataList = new List<SumoVehicleData>();

        var ids = GetVehicleIds();

        if (ids.Count == 0 && !loggedEmptyVehicleHint)
        {
            loggedEmptyVehicleHint = true;
            Debug.Log(
                "SUMO reports 0 vehicles right now (often normal at sim time ≈ 0). " +
                "Unity is stepping the sim; vehicles appear when trips depart in data/output/demand/traffic_trips.routed.rou.xml. " +
                "Watch SUMO-GUI time increase and vehicle count, or enable logVehicleCountPeriodically.");
        }

        if (ids.Count > 0 && !loggedFirstVehicle)
        {
            loggedFirstVehicle = true;
            Debug.Log($"First SUMO vehicle seen: '{ids.First.Value}' (total {ids.Count}). Cubes should appear in Hierarchy.");
        }

        if (logVehicleCountPeriodically && Time.realtimeSinceStartup >= nextStatusLogTime)
        {
            nextStatusLogTime = Time.realtimeSinceStartup + 5f;
            Debug.Log($"TraCI vehicle count: {ids.Count}");
        }

        if (autoRecenterOnFirstVehicle && !recenterApplied && ids.Count > 0)
        {
            string firstId = ids.First.Value;
            var p0 = GetVehiclePosition(firstId);
            recenterSumoX = p0.x;
            recenterSumoY = p0.y;
            recenterApplied = true;
            Debug.Log($"Recentered on first vehicle '{firstId}' at SUMO ({recenterSumoX:F1}, {recenterSumoY:F1}).");
            TrySnapMainCameraOnce();
        }

        foreach (string id in ids)
        {
            var pos = GetVehiclePosition(id);
            Vector3 world = SumoNetworkToUnityWorld(pos.x, pos.y, pos.z);
            string typeId = GetVehicleTypeId(id);
            float groundHeight = (float)(pos.z * coordinateScale);
            bool isBus = IsBusType(typeId);
            float yCenter = isBus ? groundHeight + busScale.y * 0.5f : groundHeight + cubeYOffset;
            bool hasHeading = TryGetVehicleAngleDegrees(id, out double headingDeg);
            float speed = GetVehicleSpeed(id);
            Vector3 worldForward = ComputeWorldForwardFromSumo(pos.x, pos.y, pos.z, (float)headingDeg, hasHeading);
            bool hasLaneForward = TryGetLaneWorldForward(id, pos.z, out Vector3 laneForward);

            dataList.Add(new SumoVehicleData
            {
                id = id,
                sumoX = world.x,
                sumoY = world.z,
                height = yCenter,
                typeId = typeId,
                isBus = isBus,
                headingDegrees = (float)headingDeg,
                hasHeading = hasHeading,
                worldForward = worldForward,
                laneForward = laneForward,
                hasLaneForward = hasLaneForward,
                speed = speed,
                sumoNetX = pos.x,
                sumoNetY = pos.y,
                sumoNetZ = pos.z
            });
        }

        return true;
    }

    void ApplyCubeColor(Renderer renderer, Color color)
    {
        if (renderer == null)
            return;

        Material mat = renderer.material;
        mat.color = color;
        if (mat.HasProperty("_BaseColor"))
            mat.SetColor("_BaseColor", color);
    }

    bool IsBusType(string typeId)
    {
        if (string.IsNullOrEmpty(typeId) || busTypeIds == null)
            return false;

        foreach (string busId in busTypeIds)
        {
            if (string.IsNullOrEmpty(busId))
                continue;
            if (typeId.Equals(busId, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        return false;
    }

    string GetVehicleTypeId(string vehicleId)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetTypeID(vehicleId));
        if (raw is string typeId)
            return typeId;
        return string.Empty;
    }

    float GetVehicleSpeed(string vehicleId)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetSpeed(vehicleId));
        if (raw is double speed)
            return (float)speed;
        return 0f;
    }

    string GetVehicleLaneId(string vehicleId)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetLaneID(vehicleId));
        if (raw is string laneId)
            return laneId;
        return string.Empty;
    }

    bool TryGetVehicleLanePosition(string vehicleId, out double lanePosition)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetLanePosition(vehicleId));
        if (raw is double pos)
        {
            lanePosition = pos;
            return true;
        }

        lanePosition = 0;
        return false;
    }

    bool TryGetLaneShape(string laneId, out SumoGeometry shape)
    {
        if (laneShapeCache.TryGetValue(laneId, out shape) && shape != null)
            return shape.coords != null && shape.coords.Count >= 2;

        object raw = commandProcessor.Do_job_get(Lane.GetShape(laneId));
        if (raw is SumoGeometry geometry && geometry.coords != null && geometry.coords.Count >= 2)
        {
            laneShapeCache[laneId] = geometry;
            shape = geometry;
            return true;
        }

        shape = null;
        return false;
    }

    bool TryGetLaneWorldForward(string vehicleId, double sumoZ, out Vector3 worldForward)
    {
        worldForward = Vector3.zero;

        string laneId = GetVehicleLaneId(vehicleId);
        if (string.IsNullOrEmpty(laneId) || !TryGetLaneShape(laneId, out SumoGeometry shape))
            return false;

        if (!TryGetVehicleLanePosition(vehicleId, out double lanePos))
            return false;

        SumoPosition2D prev = null;
        double traveled = 0;
        foreach (SumoPosition2D point in shape.coords)
        {
            if (prev == null)
            {
                prev = point;
                continue;
            }

            double dx = point.x - prev.x;
            double dy = point.y - prev.y;
            double segmentLength = Math.Sqrt(dx * dx + dy * dy);
            if (segmentLength < 1e-9)
            {
                prev = point;
                continue;
            }

            bool onSegment = lanePos <= traveled + segmentLength;
            bool lastPoint = point == shape.coords.Last?.Value;
            if (onSegment || lastPoint)
            {
                Vector3 from = SumoNetworkToUnityWorld(prev.x, prev.y, sumoZ);
                Vector3 to = SumoNetworkToUnityWorld(point.x, point.y, sumoZ);
                worldForward = to - from;
                worldForward.y = 0f;
                if (worldForward.sqrMagnitude > 1e-6f)
                {
                    worldForward.Normalize();
                    return true;
                }

                return false;
            }

            traveled += segmentLength;
            prev = point;
        }

        return false;
    }

    bool TryGetVehicleAngleDegrees(string vehicleId, out double angleDegrees)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetAngle(vehicleId));
        if (raw is double angle)
        {
            angleDegrees = angle;
            return true;
        }

        angleDegrees = 0;
        return false;
    }

    void RememberVehicleForward(string vehicleId, Vector3 forward)
    {
        if (forward.sqrMagnitude > 1e-6f)
            lastVehicleForwards[vehicleId] = forward;
    }

    bool TryGetRememberedForward(string vehicleId, out Vector3 forward)
    {
        if (lastVehicleForwards.TryGetValue(vehicleId, out forward) && forward.sqrMagnitude > 1e-6f)
            return true;

        forward = Vector3.zero;
        return false;
    }

    Quaternion GetVehicleRotation(Vector3 forward)
    {
        return Quaternion.LookRotation(forward, Vector3.up);
    }

    void ApplyVehicleScale(GameObject cube, SumoVehicleData veh)
    {
        cube.transform.localScale = veh.isBus ? busScale : cubeScale;
    }

    /// <summary>
    /// Derive forward in Unity world space via the same calibration path as vehicle position
    /// (avoids sideways orientation from a mismatched angle transform).
    /// </summary>
    Vector3 ComputeWorldForwardFromSumo(double sumoX, double sumoY, double sumoZ, float angleDegrees, bool hasAngle)
    {
        if (!hasAngle)
            return Vector3.forward;

        float rad = (angleDegrees + sumoAngleOffsetDegrees) * Mathf.Deg2Rad;
        double aheadX = sumoX + Math.Cos(rad);
        double aheadY = sumoY + Math.Sin(rad);

        Vector3 origin = SumoNetworkToUnityWorld(sumoX, sumoY, sumoZ);
        Vector3 ahead = SumoNetworkToUnityWorld(aheadX, aheadY, sumoZ);
        Vector3 forward = ahead - origin;
        forward.y = 0f;
        return forward.sqrMagnitude > 1e-6f ? forward.normalized : Vector3.forward;
    }

    Vector3 ResolveVehicleForward(SumoVehicleData veh, Vector3 targetPosition, bool hasLastPos, Vector3 lastPos)
    {
        // Lane tangent uses the same calibration as position — best for long buses on curves and at lights.
        if (veh.hasLaneForward && veh.laneForward.sqrMagnitude > 1e-6f)
            return veh.laneForward;

        if (hasLastPos)
        {
            Vector3 delta = targetPosition - lastPos;
            delta.y = 0f;
            if (delta.sqrMagnitude >= minMoveDistanceForRotation * minMoveDistanceForRotation)
                return delta.normalized;
        }

        if (useSumoVehicleAngle && veh.hasHeading && veh.worldForward.sqrMagnitude > 1e-6f)
            return veh.worldForward;

        if (veh.speed < stationarySpeedThreshold
            && TryGetRememberedForward(veh.id, out Vector3 cachedForward))
            return cachedForward;

        return Vector3.zero;
    }

    void UpdateSceneCubes(List<SumoVehicleData> vehiclesInStep)
    {
        var currentIDs = new HashSet<string>();

        foreach (var veh in vehiclesInStep)
        {
            currentIDs.Add(veh.id);
            var targetPosition = new Vector3(veh.sumoX, veh.height, veh.sumoY);

            if (!activeVehicles.TryGetValue(veh.id, out GameObject cube) || cube == null)
            {
                cube = vehiclePrefab != null
                    ? Instantiate(vehiclePrefab)
                    : GameObject.CreatePrimitive(PrimitiveType.Cube);

                cube.name = veh.isBus ? "Bus_" + veh.id : "Vehicle_" + veh.id;
                if (vehiclePrefab != null)
                {
                    cube.transform.localScale = prefabScale;
                }
                else
                {
                    ApplyVehicleScale(cube, veh);
                    ApplyCubeColor(cube.GetComponent<Renderer>(), veh.isBus ? busColor : cubeColor);
                }

                activeVehicles[veh.id] = cube;
            }
            else if (vehiclePrefab == null)
            {
                ApplyVehicleScale(cube, veh);
                ApplyCubeColor(cube.GetComponent<Renderer>(), veh.isBus ? busColor : cubeColor);
            }

            cube.transform.position = targetPosition;

            if (orientVehiclesToMovement)
            {
                bool hasLastPos = lastVehiclePositions.TryGetValue(veh.id, out Vector3 lastPos);
                Vector3 forward = ResolveVehicleForward(veh, targetPosition, hasLastPos, lastPos);
                if (forward.sqrMagnitude > 1e-6f)
                {
                    cube.transform.rotation = GetVehicleRotation(forward);
                    RememberVehicleForward(veh.id, forward);
                }

                lastVehiclePositions[veh.id] = targetPosition;
            }
        }

        var idsToRemove = new List<string>();
        foreach (string activeId in activeVehicles.Keys)
        {
            if (!currentIDs.Contains(activeId))
                idsToRemove.Add(activeId);
        }

        foreach (string id in idsToRemove)
        {
            if (activeVehicles.TryGetValue(id, out GameObject go) && go != null)
                Destroy(go);
            activeVehicles.Remove(id);
            lastVehiclePositions.Remove(id);
            lastVehicleForwards.Remove(id);
        }
    }

    LinkedList<string> GetVehicleIds()
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetIDList());
        if (raw is SumoStringList ssl)
            return ssl.getList();

        if (raw is object[] compound)
        {
            var ids = new LinkedList<string>();
            foreach (object item in compound)
            {
                if (item is string s)
                    ids.AddLast(s);
            }
            return ids;
        }

        throw new InvalidOperationException(
            "Unexpected TraCI vehicle ID list type: " + (raw?.GetType().FullName ?? "null"));
    }

    SumoPosition3D GetVehiclePosition(string vehicleId)
    {
        object raw = commandProcessor.Do_job_get(Vehicle.GetPosition3D(vehicleId));
        if (raw is SumoPosition3D pos3)
            return pos3;

        if (raw is SumoPosition2D pos2)
            return new SumoPosition3D(pos2.x, pos2.y, 0.0);

        throw new InvalidOperationException(
            $"Unexpected TraCI position type for '{vehicleId}': " + (raw?.GetType().FullName ?? "null"));
    }

    void TrySnapMainCameraOnce()
    {
        if (!snapMainCameraOnFirstRecenter || mainCameraSnapped)
            return;

        Camera mainCam = Camera.main;
        if (mainCam == null)
            return;

        Transform cam = mainCam.transform;
        cam.SetPositionAndRotation(
            new Vector3(0f, 100f, -150f),
            Quaternion.Euler(35f, 0f, 0f));
        if (cam.TryGetComponent(out SimpleFlyCamera flyCam))
            flyCam.SyncLookAnglesFromTransform();

        mainCameraSnapped = true;
        Debug.Log("Main Camera moved once for SUMO traffic (disable Snap Main Camera On First Recenter to prevent this).");
    }

    Vector3 SumoNetworkToUnityWorld(double sumoX, double sumoY, double sumoZ)
    {
        double sx = (sumoX - recenterSumoX - sumoPlaneManualOffset.x) * coordinateScale;
        double sz = (sumoY - recenterSumoY - sumoPlaneManualOffset.y) * coordinateScale;
        float height = (float)(sumoZ * coordinateScale + cubeYOffset);
        return ChristchurchCalibration.SumoNetworkToUnityWorld(mapRoot, sx, sz, height);
    }

    void CloseSocket()
    {
        traciReady = false;
        commandProcessor = null;

        if (socket == null)
            return;

        try { socket.Close(); } catch { }
        socket = null;
    }

    void OnApplicationQuit()
    {
        CloseSocket();
    }
}

public class SumoVehicleData
{
    public string id;
    public float sumoX;
    public float sumoY;
    public float height;
    public string typeId;
    public bool isBus;
    public float headingDegrees;
    public bool hasHeading;
    public Vector3 worldForward;
    public Vector3 laneForward;
    public bool hasLaneForward;
    public float speed;
    public double sumoNetX;
    public double sumoNetY;
    public double sumoNetZ;
}
