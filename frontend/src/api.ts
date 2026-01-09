import createClient from "openapi-fetch";
import type { paths } from "../api.d.ts";

export let BASE_URL = "/";

const client = createClient<paths>({
  baseUrl: BASE_URL,
});

export async function documents(database: string) {
  return client.GET("/{database}/-/ca460/api/documents", {
    params: { path: { database } },
  });
}
