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
          text: `Dataset “${file.name}” uploaded successfully. Ask a question and I’ll analyze this file.`,
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
      className={`rounded-2xl border-2 border-dashed px-4 py-3 transition ${
        isDragActive
          ? "border-sky-500 bg-sky-50 dark:bg-sky-950/40"
          : "border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-950"
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
              isDragActive ? "bg-sky-100 text-sky-700" : "bg-white text-slate-500 shadow-sm dark:bg-slate-900"
            }`}
          >
            {uploading ? <Loader2 className="animate-spin" size={20} /> : <Upload size={20} />}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              {isDragActive ? "Drop dataset to load" : "Drag & drop a dataset"}
            </p>
            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
              {datasetName
                ? `Loaded: ${datasetName}`
                : "CSV / Excel from your computer — used for your questions"}
            </p>
            {filePath ? (
              <p className="truncate text-[10px] text-slate-400" title={filePath}>
                {filePath}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {filePath ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearDataset();
                saveSessionState("analytics-copilot-dataset", "");
                saveSessionState("analytics-copilot-filepath", "");
              }}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
            >
              <X size={14} /> Clear
            </button>
          ) : null}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              open();
            }}
            disabled={uploading}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50 dark:bg-sky-600 dark:hover:bg-sky-500"
          >
            <FileSpreadsheet size={14} />
            {uploading ? "Uploading…" : "Browse files"}
          </button>
        </div>
      </div>
      {error ? <p className="mt-2 text-xs text-red-500">{error}</p> : null}
    </section>
  );
}
