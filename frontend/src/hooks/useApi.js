import { useCallback, useEffect, useState } from "react";

/**
 * Runs an async API call and tracks loading / error / data.
 *
 * Every page needs the same three states, and forgetting the error state
 * is how you end up with a blank white screen and no idea why. Putting it
 * in one hook means no page can forget.
 *
 * `deps` works like useEffect's dependency array.
 *
 * ESLint's react-hooks rules are disabled below, deliberately:
 *   - set-state-in-effect fires on `setLoading(true)`. That is the standard
 *     data-fetching pattern: the state is set ONCE when the request starts,
 *     not in a render-triggered loop, so there is no cascade. Removing it
 *     would leave stale data on screen while a new request is in flight.
 *   - use-memo wants a literal dependency array, which a generic hook
 *     taking `deps` as a parameter cannot provide.
 * Both are false positives for this shape of hook.
 */
/* eslint-disable react-hooks/set-state-in-effect, react-hooks/use-memo */
export function useApi(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    run()
      .then((result) => {
        // Guard against a slow response landing after the user navigated
        // away or changed the filter -- otherwise stale data overwrites new.
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [run]);

  return { data, error, loading };
}
