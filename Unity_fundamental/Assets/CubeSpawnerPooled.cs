using System.Collections;
using UnityEngine;
using UnityEngine.Pool;
using UnityEngine.UI;

// Pooled spawner: same timing UX as CubeSpawner, but cubes are reused via UnityEngine.Pool instead of CreatePrimitive each time.
/// <summary>
/// Pooled counterpart to <see cref="CubeSpawner"/>. Uses <see cref="ObjectPool{GameObject}"/> so instances are reused
/// rather than created and destroyed every cycle. Your prefab's root must carry <see cref="PooledCubeMover"/>.
/// </summary>
[DisallowMultipleComponent]
public sealed class CubeSpawnerPooled : MonoBehaviour
{
    [Header("Prefab")]
    [SerializeField]
    [Tooltip("Root object should hold mesh/collider as needed, plus PooledCubeMover on that same GameObject.")]
    private GameObject cubePrefab;

    [Header("World anchors")]
    [SerializeField]
    private Transform pointA;

    [SerializeField]
    private Transform pointB;

    [Header("Movement")]
    [SerializeField]
    [Min(0f)]
    private float moveSpeed = 5f;

    [Header("UI")]
    [SerializeField]
    private Slider spawnIntervalSlider;

    [SerializeField]
    [Tooltip("Used when the slider reference is left empty.")]
    private float defaultIntervalSeconds = 2f;

    [Header("Tuning")]
    [SerializeField]
    [Min(0.01f)]
    private float minimumIntervalSeconds = 0.2f;

    [Header("Pool")]
    [SerializeField]
    [Min(1)]
    [Tooltip("How many inactive instances the pool keeps ready by default — tune toward your typical peak concurrent cubes.")]
    private int defaultCapacity = 8;

    [SerializeField]
    [Min(1)]
    [Tooltip("Hard cap on pooled instances; protects you if spawn rate spikes.")]
    private int maxPoolSize = 64;

    private ObjectPool<GameObject> _pool;
    private Coroutine _spawnRoutine;

    private void Awake()
    {
        // collectionCheck: true catches accidental double-release in Editor builds (slight cost, worthwhile while learning).
        _pool = new ObjectPool<GameObject>(
            createFunc: CreatePooledInstance,
            actionOnGet: OnGetFromPool,
            actionOnRelease: OnReleaseToPool,
            actionOnDestroy: OnDestroyPooledInstance,
            collectionCheck: true,
            defaultCapacity: defaultCapacity,
            maxSize: maxPoolSize);
    }

    private void Start()
    {
        if (spawnIntervalSlider != null)
            spawnIntervalSlider.onValueChanged.AddListener(OnSpawnIntervalChanged);

        SpawnOneCube();
        _spawnRoutine = StartCoroutine(SpawnLoop());
    }

    private void OnDestroy()
    {
        if (spawnIntervalSlider != null)
            spawnIntervalSlider.onValueChanged.RemoveListener(OnSpawnIntervalChanged);

        // Dispose tears down remaining pooled GameObjects cleanly when this spawner leaves play mode.
        _pool?.Dispose();
        _pool = null;
    }

    private void OnSpawnIntervalChanged(float _) => RestartSpawnLoop();

    private void RestartSpawnLoop()
    {
        if (_spawnRoutine != null)
            StopCoroutine(_spawnRoutine);
        _spawnRoutine = StartCoroutine(SpawnLoop());
    }

    private IEnumerator SpawnLoop()
    {
        while (true)
        {
            float wait = GetIntervalSeconds();
            yield return new WaitForSeconds(wait);
            SpawnOneCube();
        }
    }

    private float GetIntervalSeconds()
    {
        float raw = spawnIntervalSlider != null ? spawnIntervalSlider.value : defaultIntervalSeconds;
        return Mathf.Max(minimumIntervalSeconds, raw);
    }

    private void SpawnOneCube()
    {
        if (cubePrefab == null || pointA == null || pointB == null)
        {
            Debug.LogWarning($"{nameof(CubeSpawnerPooled)}: assign cube prefab, Point A, and Point B.", this);
            return;
        }

        GameObject cube = _pool.Get();
        cube.transform.SetPositionAndRotation(pointA.position, pointA.rotation);

        if (!cube.TryGetComponent(out PooledCubeMover mover))
        {
            Debug.LogError($"{nameof(CubeSpawnerPooled)}: prefab must have {nameof(PooledCubeMover)} on the root.", cube);
            _pool.Release(cube);
            return;
        }

        mover.Initialize(pointB, moveSpeed, _pool);
    }

    private GameObject CreatePooledInstance()
    {
        // Parent under this spawner so the Hierarchy stays tidy; inactive until the pool hands it out.
        GameObject instance = Instantiate(cubePrefab, transform);
        instance.name = cubePrefab.name + " (Pooled)";
        instance.SetActive(false);
        return instance;
    }

    private static void OnGetFromPool(GameObject instance)
    {
        instance.SetActive(true);
    }

    private static void OnReleaseToPool(GameObject instance)
    {
        instance.SetActive(false);
    }

    private static void OnDestroyPooledInstance(GameObject instance)
    {
        Destroy(instance);
    }

    private void OnValidate()
    {
        if (maxPoolSize < defaultCapacity)
            maxPoolSize = defaultCapacity;
    }
}
