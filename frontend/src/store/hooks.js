import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

// Loads something through Redux and returns the same four values the useAsync hook returned,
// so a page changes very little:
//     const { data, loading, error, reload } = useQuery(selectJobSearch, fetchJobs, params);
//
//   selector  reads the query object from the store (see store/query.js)
//   thunk     the action creator that asks the server (dispatched whenever `args` changes, and on reload)
export function useQuery(selector, thunk, args) {
  const dispatch = useDispatch();
  const query = useSelector(selector);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    dispatch(thunk(args));
    // `args` is compared by its JSON text, so a new object with the same values does not ask again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dispatch, thunk, JSON.stringify(args), attempt]);

  return {
    data: query.data,
    loading: query.status === "loading" || query.status === "idle",
    error: query.error,
    reload: () => setAttempt((n) => n + 1),
  };
}
