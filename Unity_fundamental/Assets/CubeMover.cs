using UnityEngine;

// Drives a single cube from its spawn pose toward Point B, then removes it from the scene.
// The spawner adds this component at runtime; you do not usually place it in the Hierarchy yourself.
/// <summary>
/// Moves this GameObject toward a target transform in world space, then destroys itself on arrival.
/// </summary>
public sealed class CubeMover : MonoBehaviour
{
    private Transform _target;
    private float _speed;

    // Small tolerance so we do not overshoot forever when frames do not land exactly on the target.
    private const float ArrivalEpsilon = 0.05f;

    /// <summary>Wire up movement before the first <see cref="Update"/> tick (call right after you spawn the cube).</summary>
    /// <param name="targetB">Where to head (typically your Point B empty).</param>
    /// <param name="unitsPerSecond">Travel speed in world units per second.</param>
    public void Initialize(Transform targetB, float unitsPerSecond)
    {
        _target = targetB;
        _speed = Mathf.Max(0f, unitsPerSecond);
    }

    private void Update()
    {
        if (_target == null)
            return;

        // MoveTowards keeps motion smooth and frame-rate independent when multiplied by Time.deltaTime.
        transform.position = Vector3.MoveTowards(
            transform.position,
            _target.position,
            _speed * Time.deltaTime);

        // Compare squared distance to skip a comparatively costly Sqrt call.
        if (Vector3.SqrMagnitude(transform.position - _target.position) <= ArrivalEpsilon * ArrivalEpsilon)
            Destroy(gameObject);
    }
}
