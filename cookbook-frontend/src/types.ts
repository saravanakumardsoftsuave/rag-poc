export interface CookbookDoc {
  id: string;
  filename: string;
  chunksIndexed: number;
  filedAt: string;
}

export interface QueryResult {
  answer: string;
  sources: string[];
}

export type AskStatus = "idle" | "loading" | "done" | "error";
export type UploadStatus = "idle" | "uploading" | "error";
