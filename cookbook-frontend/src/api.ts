import type { CookbookDoc, QueryResult } from "./types";

// Support both common local FastAPI ports unless one is explicitly configured.
const configuredApiBase = import.meta.env.VITE_API_BASE_URL;
const API_BASES = configuredApiBase ? [configuredApiBase] : ["http://127.0.0.1:8000", "http://127.0.0.1:8001"];
let activeApiBase = API_BASES[0];

export class ApiError extends Error {}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown;
  const bases = [activeApiBase, ...API_BASES.filter((base) => base !== activeApiBase)];

  for (const base of bases) {
    try {
      const response = await fetch(`${base}${path}`, init);
      activeApiBase = base;
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function getErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail || fallback;
  } catch {
    return fallback;
  }
}

interface DocumentResponse {
  id: number;
  filename: string;
  chunks_ingested: number;
  created_at: string;
}

export async function getCookbooks(): Promise<CookbookDoc[]> {
  let res: Response;
  try {
    res = await apiFetch("/documents");
  } catch {
    throw new ApiError(`Couldn't reach the kitchen at ${API_BASES.join(" or ")}. Make sure the API is running and try again.`);
  }
  if (!res.ok) {
    throw new ApiError(await getErrorMessage(res, `The kitchen sent back an error (${res.status}). Try again.`));
  }
  const documents = (await res.json()) as DocumentResponse[];
  return documents.map((document) => ({
    id: String(document.id),
    filename: document.filename,
    chunksIndexed: document.chunks_ingested,
    filedAt: document.created_at,
  }));
}

export async function askQuestion(question: string): Promise<QueryResult> {
  let res: Response;
  try {
    res = await apiFetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiError(`Couldn't reach the kitchen at ${API_BASES.join(" or ")}. Make sure the API is running and try again.`);
  }
  if (!res.ok) {
    throw new ApiError(
      await getErrorMessage(res, `The kitchen sent back an error (${res.status}). Try that question again.`),
    );
  }
  return res.json();
}

export interface UploadResult {
  filename: string;
  chunks_ingested: number;
}

export async function uploadCookbook(file: File, onProgress: (pct: number) => void): Promise<UploadResult> {
  try {
    await apiFetch("/health");
  } catch {
    throw new ApiError(`Couldn't reach the kitchen at ${API_BASES.join(" or ")}. Make sure the API is running and try again.`);
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${activeApiBase}/upload`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string };
          if (body.detail) {
            reject(new ApiError(body.detail));
            return;
          }
        } catch {
          // Use the generic fallback below when the API did not return JSON.
        }
        reject(new ApiError(`${file.name} wouldn't file — the kitchen sent back an error (${xhr.status}).`));
      }
    };
    xhr.onerror = () => reject(new ApiError(`Couldn't reach the kitchen to file ${file.name}. Check the API is running.`));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await apiFetch("/health");
    return res.ok;
  } catch {
    return false;
  }
}

export async function deleteCookbook(id: string): Promise<void> {
  let res: Response;
  try {
    res = await apiFetch(`/documents/${id}`, {
      method: "DELETE",
    });
  } catch {
    throw new ApiError(`Couldn't reach the kitchen at ${API_BASES.join(" or ")}. Make sure the API is running and try again.`);
  }
  if (!res.ok) {
    throw new ApiError(await getErrorMessage(res, `Failed to delete document (${res.status}).`));
  }
}
