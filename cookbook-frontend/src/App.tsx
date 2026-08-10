import { useEffect, useState } from "react";
import Header from "./components/Header";
import DocumentBox from "./components/DocumentBox";
import AskCard from "./components/AskCard";
import AnswerCard from "./components/AnswerCard";
import { ApiError, askQuestion, checkHealth, uploadCookbook } from "./api";
import type { AskStatus, CookbookDoc, QueryResult, UploadStatus } from "./types";

const STORAGE_KEY = "ask-my-cookbook.documents.v1";

function loadDocuments(): CookbookDoc[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as CookbookDoc[]) : PREVIEW_DOCS;
  } catch {
    return PREVIEW_DOCS;
  }
}

const PREVIEW_DOCS: CookbookDoc[] = [
  { id: "1", filename: "Italian_Cookbook.pdf", chunksIndexed: 86, filedAt: new Date(Date.now() - 3600e3).toISOString() },
  { id: "2", filename: "Dessert_Recipes.pdf", chunksIndexed: 54, filedAt: new Date(Date.now() - 7200e3).toISOString() },
  { id: "3", filename: "Breakfast_Recipes.pdf", chunksIndexed: 41, filedAt: new Date(Date.now() - 86400e3).toISOString() },
];

export default function App() {
  const [documents, setDocuments] = useState<CookbookDoc[]>(loadDocuments);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [question, setQuestion] = useState("How long should the lasagna rest before cutting?");
  const [askStatus, setAskStatus] = useState<AskStatus>("done");
  const [result, setResult] = useState<QueryResult | null>({
    answer:
      "Let the lasagna rest for 15 minutes after it comes out of the oven before cutting. This gives the layers time to set so slices hold together instead of sliding apart.",
    sources: ["documents/Italian_Cookbook.pdf", "documents/Italian_Cookbook.pdf"],
  });
  const [askError, setAskError] = useState<string | null>(null);

  const [kitchenStatus, setKitchenStatus] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(documents));
  }, [documents]);

  useEffect(() => {
    checkHealth().then((ok) => setKitchenStatus(ok ? "online" : "offline"));
  }, []);

  async function handleUpload(file: File) {
    setUploadStatus("uploading");
    setUploadProgress(0);
    setUploadError(null);
    try {
      const res = await uploadCookbook(file, setUploadProgress);
      setDocuments((docs) => [
        ...docs,
        {
          id: `${Date.now()}-${res.filename}`,
          filename: res.filename,
          chunksIndexed: res.chunks_ingested,
          filedAt: new Date().toISOString(),
        },
      ]);
      setUploadStatus("idle");
    } catch (err) {
      setUploadStatus("error");
      setUploadError(err instanceof ApiError ? err.message : "That cookbook wouldn't file. Try again.");
    }
  }

  async function runAsk(q: string) {
    setQuestion(q);
    setAskStatus("loading");
    setAskError(null);
    try {
      const res = await askQuestion(q);
      setResult(res);
      setAskStatus("done");
    } catch (err) {
      setAskError(err instanceof ApiError ? err.message : "Something went wrong asking that question.");
      setAskStatus("error");
    }
  }

  function handleClear() {
    setQuestion("");
    setResult(null);
    setAskError(null);
    setAskStatus("idle");
  }

  return (
    <div className="app">
      <Header
        kitchenStatus={kitchenStatus}
        onClear={handleClear}
        clearDisabled={askStatus === "idle"}
      />
      <main className="layout">
        <DocumentBox
          documents={documents}
          status={uploadStatus}
          progress={uploadProgress}
          error={uploadError}
          onUpload={handleUpload}
        />
        <div className="layout__main">
          <AskCard onAsk={runAsk} disabled={askStatus === "loading"} />
          <AnswerCard
            status={askStatus}
            question={question}
            result={result}
            errorMessage={askError}
            onRetry={() => runAsk(question)}
          />
          <p className="footnote">
            Every answer comes straight from your uploaded cookbooks — nothing outside them.
            <br />
            If it's not in your books, this app says so instead of guessing.
          </p>
        </div>
      </main>
    </div>
  );
}
