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

/** One question and its answer inside a conversation. */
export interface ChatTurn {
  id: string;
  status: Exclude<AskStatus, "idle">;
  question: string;
  answer: string;
  sources: string[];
  error: string | null;
  askedAt: string;
}

export interface Conversation {
  id: string;
  title: string;
  turns: ChatTurn[];
  createdAt: string;
  updatedAt: string;
}
