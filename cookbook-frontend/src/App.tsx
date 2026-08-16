import { useEffect, useState } from "react";
import Header from "./components/Header";
import DocumentBox from "./components/DocumentBox";
import AskCard from "./components/AskCard";
import AnswerCard from "./components/AnswerCard";
import { ApiError, askQuestion, checkHealth, deleteCookbook, getCookbooks, uploadCookbook } from "./api";
import type { AskStatus, CookbookDoc, QueryResult, UploadStatus } from "./types";

export default function App() {
  const [documents, setDocuments] = useState<CookbookDoc[]>([]);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [askStatus, setAskStatus] = useState<AskStatus>("idle");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const [kitchenStatus, setKitchenStatus] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    checkHealth().then((ok) => setKitchenStatus(ok ? "online" : "offline"));
    getCookbooks()
      .then(setDocuments)
      .catch((err) => setUploadError(err instanceof ApiError ? err.message : "Couldn't load your cookbooks."));
  }, []);

  async function handleUpload(file: File) {
    setUploadStatus("uploading");
    setUploadProgress(0);
    setUploadError(null);
    try {
      await uploadCookbook(file, setUploadProgress);
      await getCookbooks().then(setDocuments);
      setUploadStatus("idle");
    } catch (err) {
      setUploadStatus("error");
      setUploadError(err instanceof ApiError ? err.message : "That cookbook wouldn't file. Try again.");
    }
  }

  async function handleDelete(id: string) {
    setUploadError(null);
    try {
      await deleteCookbook(id);
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Couldn't delete that cookbook. Try again.");
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
    <div className="app app--chat">
      <Header
        kitchenStatus={kitchenStatus}
        onClear={handleClear}
        clearDisabled={askStatus === "idle"}
      />
      <main className={`layout ${askStatus !== "idle" ? "layout--conversation" : ""}`}>
        <DocumentBox
          documents={documents}
          status={uploadStatus}
          progress={uploadProgress}
          error={uploadError}
          onUpload={handleUpload}
          onDelete={handleDelete}
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
          <p className="footnote">Cookbook AI can only answer from the cookbooks you upload.</p>
        </div>
      </main>
    </div>
  );
}
