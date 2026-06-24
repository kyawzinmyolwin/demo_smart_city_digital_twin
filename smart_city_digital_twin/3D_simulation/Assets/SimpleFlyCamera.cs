using System;
using UnityEngine;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif
#if UNITY_EDITOR
using UnityEditor;
#endif

/// <summary>
/// Fly camera for Play mode. Uses the Input System when enabled in Player Settings.
/// </summary>
[RequireComponent(typeof(Camera))]
public class SimpleFlyCamera : MonoBehaviour
{
    public enum LookActivation
    {
        HoldRightMouse,
        HoldAnyMouseButton,
        Always
    }

    public float lookSensitivity = 2f;
    public float moveSpeed = 15f;
    public float fastMultiplier = 4f;
    public KeyCode fastKey = KeyCode.LeftShift;

    [Header("Look / Focus")]
    public LookActivation lookActivation = LookActivation.Always;
    public bool showDebugOverlay = true;

    [Header("Map framing")]
    [Tooltip("On Play, move the camera to see all meshes in the scene (useful after swapping the map).")]
    public bool frameSceneOnStart = false;
    [Tooltip("Multiply auto move speed by scene size after framing.")]
    public bool scaleMoveSpeedToSceneSize = true;
    public float framePadding = 1.35f;
    public float minMoveSpeed = 15f;
    public float maxMoveSpeed = 800f;

    float yaw;
    float pitch;

#if ENABLE_INPUT_SYSTEM
    Vector2 lastMouseDelta;
    bool lastLooking;
    bool lastFast;
    Vector3 lastMoveInput;
    string lastInputWarning;
#endif

    void Awake()
    {
        SyncLookAnglesFromTransform();
    }

    void Start()
    {
        if (frameSceneOnStart)
            TryFrameSceneBounds();
    }

    /// <summary>Call after moving the camera in code so mouse-look stays consistent.</summary>
    public void SyncLookAnglesFromTransform()
    {
        Vector3 forward = transform.forward;
        pitch = -Mathf.Asin(Mathf.Clamp(forward.y, -1f, 1f)) * Mathf.Rad2Deg;
        yaw = Mathf.Atan2(forward.x, forward.z) * Mathf.Rad2Deg;
    }

    /// <summary>Fit the camera to visible mesh bounds (e.g. after changing the map).</summary>
    public bool TryFrameSceneBounds()
    {
        if (!TryGetSceneMeshBounds(out Bounds bounds))
            return false;

        Vector3 center = bounds.center;
        float radius = Mathf.Max(bounds.extents.x, bounds.extents.y, bounds.extents.z, 1f);

        Camera cam = GetComponent<Camera>();
        float fovRad = cam.fieldOfView * Mathf.Deg2Rad;
        float distance = (radius / Mathf.Tan(fovRad * 0.5f)) * framePadding;

        transform.position = center + new Vector3(0f, distance * 0.55f, -distance * 0.85f);
        transform.LookAt(center);
        SyncLookAnglesFromTransform();

        if (scaleMoveSpeedToSceneSize)
            moveSpeed = Mathf.Clamp(radius * 0.2f, minMoveSpeed, maxMoveSpeed);

        return true;
    }

#if UNITY_EDITOR
    [ContextMenu("Frame Scene Now (Edit Mode)")]
    void EditorFrameSceneNow()
    {
        if (!TryFrameSceneBounds())
            Debug.LogWarning("SimpleFlyCamera: no mesh bounds found to frame.");
        else if (!Application.isPlaying)
            EditorUtility.SetDirty(this);
    }
#endif

    static bool TryGetSceneMeshBounds(out Bounds bounds)
    {
        bounds = default;
        bool hasBounds = false;

        var renderers = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
        foreach (Renderer renderer in renderers)
        {
            if (renderer == null || !renderer.enabled || !renderer.gameObject.activeInHierarchy)
                continue;
            if (renderer is ParticleSystemRenderer)
                continue;
            if (renderer.GetComponent<Camera>() != null)
                continue;
            if (renderer.gameObject.name.StartsWith("Vehicle_", StringComparison.Ordinal))
                continue;

            if (!hasBounds)
            {
                bounds = renderer.bounds;
                hasBounds = true;
            }
            else
            {
                bounds.Encapsulate(renderer.bounds);
            }
        }

        return hasBounds;
    }

    void Update()
    {
#if ENABLE_INPUT_SYSTEM
        var keyboard = Keyboard.current;
        var mouse = Mouse.current;

        if (keyboard == null)
        {
            lastInputWarning = "Keyboard device missing — click the Game tab, then press Play again.";
            return;
        }

        lastInputWarning = null;

        bool looking =
            lookActivation == LookActivation.Always ||
            (mouse != null && lookActivation == LookActivation.HoldRightMouse && mouse.rightButton.isPressed) ||
            (mouse != null && lookActivation == LookActivation.HoldAnyMouseButton &&
             (mouse.leftButton.isPressed || mouse.rightButton.isPressed || mouse.middleButton.isPressed));

        if (looking && mouse != null)
        {
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible = false;

            Vector2 md = mouse.delta.ReadValue();
            lastMouseDelta = md;
            yaw += md.x * lookSensitivity * 0.02f;
            pitch -= md.y * lookSensitivity * 0.02f;
            pitch = Mathf.Clamp(pitch, -89f, 89f);
            transform.rotation = Quaternion.Euler(pitch, yaw, 0f);
        }
        else if (lookActivation != LookActivation.Always)
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        bool fast = keyboard.leftShiftKey.isPressed;
        float speed = moveSpeed * (fast ? fastMultiplier : 1f);
        float dt = Time.unscaledDeltaTime;

        Vector3 input =
            (keyboard.upArrowKey.isPressed ? Vector3.forward : Vector3.zero) +
            (keyboard.downArrowKey.isPressed ? Vector3.back : Vector3.zero) +
            (keyboard.leftArrowKey.isPressed ? Vector3.left : Vector3.zero) +
            (keyboard.rightArrowKey.isPressed ? Vector3.right : Vector3.zero);

        if (input.sqrMagnitude > 1f) input.Normalize();
        transform.position += transform.TransformDirection(input) * (speed * dt);

        lastLooking = looking;
        lastFast = fast;
        lastMoveInput = input;
#else
        bool looking = Input.GetMouseButton(1);

        if (looking)
        {
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible = false;

            yaw += Input.GetAxisRaw("Mouse X") * lookSensitivity;
            pitch -= Input.GetAxisRaw("Mouse Y") * lookSensitivity;
            pitch = Mathf.Clamp(pitch, -89f, 89f);
            transform.rotation = Quaternion.Euler(pitch, yaw, 0f);
        }
        else
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }

        float speed = moveSpeed * (Input.GetKey(fastKey) ? fastMultiplier : 1f);
        float dt = Time.unscaledDeltaTime;

        Vector3 input =
            (Input.GetKey(KeyCode.UpArrow) ? Vector3.forward : Vector3.zero) +
            (Input.GetKey(KeyCode.DownArrow) ? Vector3.back : Vector3.zero) +
            (Input.GetKey(KeyCode.LeftArrow) ? Vector3.left : Vector3.zero) +
            (Input.GetKey(KeyCode.RightArrow) ? Vector3.right : Vector3.zero);

        if (input.sqrMagnitude > 1f) input.Normalize();
        transform.position += transform.TransformDirection(input) * (speed * dt);
#endif
    }

    void OnGUI()
    {
        if (!showDebugOverlay) return;

#if ENABLE_INPUT_SYSTEM
        var mouse = Mouse.current;
        var keyboard = Keyboard.current;

        GUI.color = new Color(1f, 1f, 1f, 0.9f);
        GUI.Label(new Rect(10, 10, 900, 22),
            $"Input: keyboard={(keyboard != null)} mouse={(mouse != null)} | moveSpeed={moveSpeed:F0}");
        GUI.Label(new Rect(10, 32, 900, 22),
            $"Click inside the Game tab. Arrow keys/Shift move. Look mode: {lookActivation}");
        GUI.Label(new Rect(10, 54, 900, 22),
            $"looking={lastLooking} move={lastMoveInput} shiftFast={lastFast}");
        if (!string.IsNullOrEmpty(lastInputWarning))
            GUI.Label(new Rect(10, 76, 900, 22), lastInputWarning);
        else
            GUI.Label(new Rect(10, 76, 900, 22), $"mouse.delta={lastMouseDelta}");
#else
        GUI.color = new Color(1f, 1f, 1f, 0.9f);
        GUI.Label(new Rect(10, 10, 900, 22), "SimpleFlyCamera: legacy Input path (ENABLE_INPUT_SYSTEM is off).");
#endif
    }
}
