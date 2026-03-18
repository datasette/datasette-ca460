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

export async function models(database: string) {
  return client.GET("/{database}/-/ca460/api/models", {
    params: { path: { database } },
  });
}

export async function sync(database: string, data: {
  project_id: number;
  page_type_model: string;
  parser_model: string;
}) {
  return await client.POST("/{database}/-/ca460/api/sync", {
    params: { path: { database } },
    body: {
      project_id: data.project_id,
      page_type_model: data.page_type_model,
      parser_model: data.parser_model,
    }
  });
}

export async function syncEvents(database: string, syncJobId: string) {
  return client.GET("/{database}/-/ca460/sync/{sync_job_id}/events", {
    params: { path: { database, sync_job_id: syncJobId } },
  });
}

export async function documentParsed(database: string, documentId: string) {
  return client.GET("/{database}/-/ca460/api/document/{document_id}/parsed", {
    params: { path: { database, document_id: documentId } },
  });
}
