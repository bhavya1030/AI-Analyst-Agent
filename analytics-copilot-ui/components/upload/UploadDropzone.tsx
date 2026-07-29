"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FileSpreadsheet, Loader2, Upload, X } from "lucide-react";
import { uploadDataset } from "@/services/api";
import { useChatStore } from "@/store/chatStore";

export default function UploadDropzone() {
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const setDatasetName = useChatStore((state) => state.setDatasetName);
  const setFilePath = useChatStore((state) => state.setFilePath);
  const clearDataset = useChatStore((state) => state.clearDataset);
  const datasetName = useChatStore((state) => state.datasetName);
  const filePath = useChatStore((state) => state.filePath);
  const addMessage = useChatStore((state) => state.addMessage);
  const ensureServerSession = useChatStore((state) => state.ensureServerSession);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setError(null);
      if (acceptedFiles.length === 0) {
        setError("Please drop a valid CSV or Excel file.");
        return;
      }

      const file = acceptedFiles[0];
      const lower = file.name.toLowerCase();
      if (!lower.endsWith(".csv") && !lower.endsWith(".xlsx") && !lower.endsWith(".xls")) {
        setError("Supported formats: .csv, .xlsx, .xls");
        return;
      }

      setUploading(true);
      try {
        const result = await uploadDataset(file);
        setDatasetName(file.name);
        setFilePath(result.file_path);
        await ensureServerSession(file.name);
        addMessage({
          id: `system-upload-${Date.now()}`,
          role: "assistant",
          text: `Dataset “${file.name}” is ready. Ask a question and I’ll analyze this file.`,
          timestamp: Date.now(),
        });
      } catch {
        setError("Upload failed. Check that the backend is running.");
      } finally {
        setUploading(false);
      }
    },
    [addMessage, ensureServerSession, setDatasetName, setFilePath]
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    multiple: false,
    noClick: true,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.ms-excel": [".xls"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
  });

  return (
    <section
      {...getRootProps()}
      className={`rounded-xl border border-dashed px-2.5 py-2 transition ${
        isDragActive
          ? "border-accent bg-accent-soft/60"
          : filePath
            ? "border-success/40 bg-success-soft/40"
            : "border-border bg-surface-muted/50"
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
              isDragActive
                ? "bg-accent-soft text-accent"
                : filePath
                  ? "bg-success-soft text-success"
                  : "bg-surface text-muted-foreground shadow-soft ring-1 ring-border"
            }`}
          >
            {uploading ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />}
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold text-foreground">
              {isDragActive
                ? "Drop to upload"
                : datasetName
                  ? "Dataset loaded"
                  : "Upload dataset"}
            </p>
            <p className="truncate text-[10px] text-muted-foreground">
              {datasetName || "CSV / Excel — optional"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {filePath ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearDataset();
              }}
              className="btn-secondary !px-2 !py-1"
            >
              <X size={12} /> Clear
            </button>
          ) : null}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              open();
            }}
            disabled={uploading}
            className="btn-secondary !px-2 !py-1 disabled:opacity-50"
          >
            <FileSpreadsheet size={12} />
            {uploading ? "…" : "Browse"}
          </button>
        </div>
      </div>
      {error ? <p className="mt-1 text-[10px] font-medium text-danger">{error}</p> : null}
    </section>
  );
}
