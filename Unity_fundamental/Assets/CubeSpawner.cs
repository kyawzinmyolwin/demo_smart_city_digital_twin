using System;
using System.Collections;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

// Spawns a primitive cube at Point A when play begins, then keeps spawning on a timer.
// The wait between spawns comes from your UI slider (seconds), clamped so it never drops below a sensible floor.
/// <summary>
/// Spawns a cube at Point A on start, then repeats on an interval driven by a UI slider (or defaults).
/// </summary>
public sealed class CubeSpawner : MonoBehaviour
{
    [Header("World anchors")]
    [SerializeField] private Transform pointA;
    [SerializeField] private Transform pointB;

    [Header("Movement")]
    [SerializeField] private float moveSpeed = 5f;

    [Header("UI")]
    [SerializeField] private Slider spawnIntervalSlider;
    [Tooltip("Falls back to this value when no slider is assigned in the Inspector.")]
    [SerializeField] private float defaultIntervalSeconds = 2f;

    [Header("Tuning")]
    [Tooltip("Never wait shorter than this many seconds, so the loop stays stable if the slider hits zero.")]
    [SerializeField] private float minimumIntervalSeconds = 0.2f;

    [Header("New Variables")]
    [SerializeField] private int sliderValue = 0;
    [SerializeField] private TextMeshProUGUI lblRate;
    private Coroutine _spawnRoutine;

    private void Start()
    {
        if (spawnIntervalSlider != null)
        {
            spawnIntervalSlider.onValueChanged.AddListener(OnSpawnIntervalChanged);
            sliderValue = Mathf.RoundToInt(spawnIntervalSlider.value);
            if (sliderValue > 0) _spawnRoutine = StartCoroutine(SpawnLoop());
        }

        // One cube straight away, then the coroutine handles the repeating timer.
        //SpawnOneCube();

    }

    private void OnDestroy()
    {
        // Drop the listener so Unity does not call back into a destroyed object.
        if (spawnIntervalSlider != null)
            spawnIntervalSlider.onValueChanged.RemoveListener(OnSpawnIntervalChanged);
    }

    private void OnSpawnIntervalChanged(float _) => RestartSpawnLoop();

    private void RestartSpawnLoop()
    {
        if (_spawnRoutine != null)
            StopCoroutine(_spawnRoutine);
        _spawnRoutine = StartCoroutine(SpawnLoop());
    }

    // Coroutine: wait, spawn, repeat — avoids blocking the main thread the way a tight loop would.
    private IEnumerator SpawnLoop()
    {
        // while (true)
        // {
        //     float wait = GetIntervalSeconds();
        //     yield return new WaitForSeconds(wait);
        //     SpawnOneCube();
        // }

        while (true)
        {
            float wait = GetWaitingTimeInSeconds();
            yield return new WaitForSeconds(wait);
            SpawnOneCube();
        }
    }

    private float GetIntervalSeconds()
    {
        float raw = spawnIntervalSlider != null ? spawnIntervalSlider.value : defaultIntervalSeconds;
        return Mathf.Max(minimumIntervalSeconds, raw);
    }

    private float GetWaitingTimeInSeconds()
    {
        //0 = 0 cube, 1 = 1 cube per minute,
        float waitingTime = defaultIntervalSeconds;
        sliderValue = Mathf.RoundToInt(spawnIntervalSlider.value);

        if (lblRate != null)
            lblRate.text = $"{sliderValue} cubes per minute";


        if (spawnIntervalSlider != null && sliderValue > 0f)
        {
            waitingTime = 60f / sliderValue;
        }

        return waitingTime;
    }

    private void SpawnOneCube()
    {
        if (pointA == null || pointB == null)
        {
            Debug.LogWarning("CubeSpawner: assign Point A and Point B transforms.");
            return;
        }

        GameObject cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
        cube.name = "SpawnedCube";
        cube.transform.position = pointA.position;
        cube.transform.rotation = pointA.rotation;

        var mover = cube.AddComponent<CubeMover>();
        mover.Initialize(pointB, moveSpeed);
    }
}
