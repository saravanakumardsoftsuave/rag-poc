import { useRef, useState } from "react";
import type { CookbookDoc, UploadStatus } from "../types";
import { CheckIcon, TrashIcon, UploadArrowIcon } from "./icons";

const ACCEPTED_FILE_TYPES = [
  ".pdf",
  ".doc", ".docx", ".odt", ".rtf",
  ".ppt", ".pptx", ".odp",
  ".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".tsv",
  ".epub",
  ".html", ".htm", ".xml", ".json",
  ".txt", ".md", ".rst", ".log", ".yaml", ".yml",
  ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic",
].join(",");

interface DocumentBoxProps {
  documents: CookbookDoc[];
  status: UploadStatus;
  progress: number;
  error: string | null;
  onUpload: (file: File) => void;
  onDelete?: (id: string) => Promise<void>;
}

export default function DocumentBox({ documents, status, progress, error, onUpload, onDelete }: DocumentBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    onUpload(file);
  }

  async function handleDeleteClick(id: string) {
    if (!onDelete || deletingId) return;
    setDeletingId(id);
    try {
      await onDelete(id);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <aside className="box" aria-label="Your cookbooks">
      <p className="box__eyebrow">Library</p>
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
          accept={ACCEPTED_FILE_TYPES}
          className="filer__input"
          disabled={status === "uploading"}
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <UploadArrowIcon className="filer__icon" />
        <span className="filer__label">
          {status === "uploading" ? `Uploadingâ€¦ ${progress}%` : "Add a cookbook"}
        </span>
        <span className="filer__hint">Any document - PDF, Word, PowerPoint, Excel, images, and more</span>
        {status === "uploading" && (
          <span className="filer__bar">
            <span className="filer__bar-fill" style={{ width: `${progress}%` }} />
          </span>
        )}
      </label>

      {error && <p className="box__error">{error}</p>}

      {documents.length === 0 ? (
        <p className="box__empty">
          Add a document to begin.
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
              </span>
              {onDelete && (
                <button
                  type="button"
                  className="tab__delete"
                  title={`Delete ${doc.filename}`}
                  aria-label={`Delete ${doc.filename}`}
                  disabled={deletingId === doc.id}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteClick(doc.id);
                  }}
                >
                  <TrashIcon className="tab__delete-icon" />
                </button>
              )}
              <CheckIcon className="tab__check" aria-hidden="true" />
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
