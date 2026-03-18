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

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      resolve(dataUrl.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export async function uploadPdf(database: string, file: File) {
  const file_data = await readFileAsBase64(file);
  return client.POST("/{database}/-/ca460/api/upload", {
    params: { path: { database } },
    body: {
      file_data,
      filename: file.name,
    } as any,
  });
}

export async function processDocument(database: string, data: {
  document_id: number;
  page_type_model: string;
  parser_model: string;
}) {
  return client.POST("/{database}/-/ca460/api/process", {
    params: { path: { database } },
    body: data as any,
  });
}
