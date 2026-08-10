import type { QueryResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {}

export async function askQuestion(question: string): Promise<QueryResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiError(`Couldn't reach the kitchen at ${API_BASE}. Make sure the API is running and try again.`);
  }
  if (!res.ok) {
    throw new ApiError(`The kitchen sent back an error (${res.status}). Try that question again.`);
  }
  return res.json();
}

export interface UploadResult {
  filename: string;
  chunks_ingested: number;
}

export function uploadCookbook(file: File, onProgress: (pct: number) => void): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
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
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}
