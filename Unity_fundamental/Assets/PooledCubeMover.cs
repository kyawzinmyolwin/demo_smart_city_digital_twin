using UnityEngine;
using UnityEngine.Pool;

// Like CubeMover, but hands the cube back to an ObjectPool instead of destroying it — handy when you spawn often.
/// <summary>
/// Mirrors <see cref="CubeMover"/>, but releases this instance to an <see cref="ObjectPool{GameObject}"/> on arrival
/// (or when the target or pool reference goes missing), rather than calling <see cref="Object.Destroy"/>.
/// </summary>
[DisallowMultipleComponent]
public sealed class PooledCubeMover : MonoBehaviour
{
    private Transform _target;
    private float _speed;
    private ObjectPool<GameObject> _pool;
    private bool _returned;

    private const float ArrivalEpsilon = 0.05f;

    private void OnEnable()
    {
        // Each time the pool reactivates this object, allow another release cycle.
        _returned = false;
    }

    /// <summary>Call straight after <see cref="ObjectPool{GameObject}.Get"/> positions the instance at Point A.</summary>
    /// <param name="targetB">Destination transform (Point B).</param>
    /// <param name="unitsPerSecond">Travel speed in world units per second.</param>
    /// <param name="pool">The pool that owns this instance — used for <see cref="ObjectPool{GameObject}.Release"/>.</param>
    public void Initialize(Transform targetB, float unitsPerSecond, ObjectPool<GameObject> pool)
    {
        _target = targetB;
        _speed = Mathf.Max(0f, unitsPerSecond);
        _pool = pool;
    }

    private void Update()
    {
        if (_returned)
            return;

        if (_target == null || _pool == null)
        {
            ReturnToPool();
            return;
        }

        transform.position = Vector3.MoveTowards(
            transform.position,
            _target.position,
            _speed * Time.deltaTime);

        if (Vector3.SqrMagnitude(transform.position - _target.position) <= ArrivalEpsilon * ArrivalEpsilon)
            ReturnToPool();
    }

    private void ReturnToPool()
    {
        // Guard against releasing twice, which would upset the pool's internal bookkeeping.
        if (_returned || _pool == null)
            return;

        _returned = true;
        _target = null;
        _pool.Release(gameObject);
    }
}
