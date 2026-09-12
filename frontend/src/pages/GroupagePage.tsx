import { Navigate, useSearchParams } from "react-router";

/** Keep shared bookmarks and exported links usable after merging the two screens. */
export default function GroupagePage() {
  const [params] = useSearchParams();
  const query = new URLSearchParams();
  if (params.has("trip")) query.set("trip", params.get("trip")!);
  else if (params.has("shipments")) query.set("shipments", params.get("shipments")!);
  return <Navigate to={`/trips${query.size ? `?${query}` : ""}`} replace />;
}
