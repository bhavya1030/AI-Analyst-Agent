"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { FileSpreadsheet, Loader2, Upload, X } from "lucide-react";
import { uploadDataset } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { saveSessionState } from "@/utils/localStorage";

export default function UploadDropzone() {
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const setDatasetName = useChatStore((state) => state.setDatasetName);
  const setFilePath = useChatStore((state) => state.setFilePath);
  const clearDataset = useChatStore((state) => state.clearDataset);
  const datasetName = useChatStore((state) => state.datasetName);
  const filePath = useChatStore((state) => state.filePath);
  const addMessage = useChatStore((state) => state.addMessage);

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
        saveSessionState("analytics-copilot-dataset", file.name);
        saveSessionState("analytics-copilot-filepath", result.file_path);
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
    [addMessage, setDatasetName, setFilePath]
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
      className={`rounded-2xl border border-dashed px-3 py-2.5 transition ${
        isDragActive
          ? "border-blue-400 bg-blue-50/70"
          : filePath
            ? "border-emerald-200 bg-emerald-50/40"
            : "border-slate-200 bg-slate-50/50"
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
              isDragActive
                ? "bg-blue-100 text-blue-700"
                : filePath
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-white text-slate-500 shadow-soft ring-1 ring-slate-100"
            }`}
          >
            {uploading ? <Loader2 className="animate-spin" size={16} /> : <Upload size={16} />}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-800">
              {isDragActive
                ? "Drop to upload"
                : datasetName
                  ? "Dataset loaded"
                  : "Upload dataset (optional)"}
            </p>
            <p className="truncate text-[11px] text-slate-500">
              {datasetName
                ? datasetName
                : "CSV / Excel — or skip and ask for open data"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {filePath ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearDataset();
                saveSessionState("analytics-copilot-dataset", "");
                saveSessionState("analytics-copilot-filepath", "");
              }}
              className="btn-secondary !py-1.5"
            >
              <X size={13} /> Clear
            </button>
          ) : null}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              open();
            }}
            disabled={uploading}
            className="btn-secondary !py-1.5 disabled:opacity-50"
          >
            <FileSpreadsheet size={13} />
            {uploading ? "Uploading…" : "Browse"}
          </button>
        </div>
      </div>
      {error ? <p className="mt-1.5 text-[11px] font-medium text-red-500">{error}</p> : null}
    </section>
  );
}
