import { useEffect, useState } from "react";
import { getErrorMessage } from "../utils/errors";

// Runs an async function and keeps track of the three things every screen needs:
//   loading (spinner), error (message), data (the result)  + reload() to try again.
// Usage:  const { data, loading, error, reload } = useAsync(() => getThing(id), [id]);
export function useAsync(asyncFn, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true; // ignore the answer if the screen was closed or the inputs changed meanwhile
    setState((s) => ({ ...s, loading: true, error: null }));
    asyncFn()
      .then((data) => active && setState({ data, loading: false, error: null }))
      .catch((err) => active && setState({ data: null, loading: false, error: getErrorMessage(err) }));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  return { ...state, reload: () => setAttempt((n) => n + 1) };
}
