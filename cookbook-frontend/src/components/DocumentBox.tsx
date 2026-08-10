import { useRef, useState } from "react";
import type { CookbookDoc, UploadStatus } from "../types";
import { relativeTime } from "../utils";
import { CheckIcon, UploadArrowIcon } from "./icons";

interface DocumentBoxProps {
  documents: CookbookDoc[];
  status: UploadStatus;
  progress: number;
  error: string | null;
  onUpload: (file: File) => void;
}

export default function DocumentBox({ documents, status, progress, error, onUpload }: DocumentBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    if (file.type !== "application/pdf") return;
    onUpload(file);
  }

  return (
    <aside className="box" aria-label="Your cookbooks">
      <p className="box__eyebrow">The box</p>
      <h2 className="box__title">Your cookbooks</h2>

      <label
        className={`filer ${dragging ? "filer--dragging" : ""} ${status === "uploading" ? "filer--busy" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="filer__input"
          disabled={status === "uploading"}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <UploadArrowIcon className="filer__icon" />
        <span className="filer__label">
          {status === "uploading" ? `Filing… ${progress}%` : "File a cookbook"}
        </span>
        <span className="filer__hint">PDF, dropped in or picked</span>
        {status === "uploading" && (
          <span className="filer__bar">
            <span className="filer__bar-fill" style={{ width: `${progress}%` }} />
          </span>
        )}
      </label>

      {error && <p className="box__error">{error}</p>}

      {documents.length === 0 ? (
        <p className="box__empty">
          Your box is empty. File a cookbook PDF above to start asking it questions.
        </p>
      ) : (
        <ul className="tabs">
          {documents.map((doc, i) => (
            <li key={doc.id} className={`tab tab--${i % 3}`}>
              <span className="tab__flap" aria-hidden="true">
                {doc.filename.charAt(0).toUpperCase()}
              </span>
              <span className="tab__body">
                <span className="tab__name">{doc.filename}</span>
                <span className="tab__meta">
                  {doc.chunksIndexed} chunks filed · {relativeTime(doc.filedAt)}
                </span>
              </span>
              <CheckIcon className="tab__check" aria-hidden="true" />
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
