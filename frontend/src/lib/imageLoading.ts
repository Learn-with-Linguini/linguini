export function imageLoadingAttrs(lazy?: boolean): { loading: "lazy" | "eager"; fetchPriority?: "high" } {
  return lazy ? { loading: "lazy" } : { loading: "eager", fetchPriority: "high" };
}
