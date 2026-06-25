"use client";

import { useEffect, useState } from "react";

// Returns `value` after it has stayed unchanged for `delay` ms. The initial
// value is returned immediately (no delay on first render).
export function useDebounced<T>(value: T, delay = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}
