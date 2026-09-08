import { useState } from "react";
import type { User } from "../api/client";

export default function Avatar({ user, large = false }: { user: Pick<User, "username" | "avatar_url">; large?: boolean }) {
  const [failed, setFailed] = useState<string | null>(null);
  return <span className={`profile-avatar ${large ? "profile-avatar-large" : ""}`} aria-hidden="true">
    {user.avatar_url && failed !== user.avatar_url
      ? <img src={user.avatar_url} alt="" onError={() => setFailed(user.avatar_url || null)} />
      : <span>{user.username.slice(0, 2).toUpperCase()}</span>}
  </span>;
}
