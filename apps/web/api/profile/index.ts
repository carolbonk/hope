import { API_URL, online } from "@/api/http";
import { FixtureProfileApi } from "./fixture";
import { HttpProfileApi } from "./http";
import type { ProfileApi } from "./types";

export * from "./types";

let shared: ProfileApi | undefined;

/** HTTP client when `NEXT_PUBLIC_HOPE_API_URL` is set; otherwise one shared offline fixture. */
export function profileApi(): ProfileApi {
  shared ??= online ? new HttpProfileApi(API_URL) : new FixtureProfileApi("empty", 400);
  return shared;
}
