"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText } from "lucide-react";
import { uploadDataset } from "@/services/api";
import { useChatStore } from "@/store/chatStore";
import { saveSessionState } from "@/utils/localStorage";

export default function UploadDropzone() {
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const setDatasetName = useChatStore((state) => state.setDatasetName);
  const resetConversation = useChatStore((state) => state.resetConversation);
  const setSessionId = useChatStore((state) => state.setSessionId);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    setError(null);
    if (acceptedFiles.length === 0) {
      setError("Please upload a valid CSV file.");
      return;
    }

    const file = acceptedFiles[0];
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Only CSV uploads are supported.");
      return;
    }

    setUploading(true);
    try {
      await uploadDataset(file);
      resetConversation();
      setSessionId(`session-${Date.now()}`);
      setDatasetName(file.name);
      saveSessionState("analytics-copilot-dataset", file.name);
    } catch (err) {
      setError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }, [resetConversation, setDatasetName, setSessionId]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, multiple: false, accept: { "text/csv": [".csv"] } });

  return (
    <section className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center dark:border-slate-700 dark:bg-slate-950">
      <div {...getRootProps()} className="cursor-pointer">
        <input {...getInputProps()} />
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-300">
          <Upload size={28} />
        </div>
        <div className="mt-4 space-y-2">
          <p className="text-lg font-semibold">Upload a dataset</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">Drag & drop CSV or click to select a file.</p>
          <div className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-4 py-2 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
            <FileText size={16} />
            Supported: .csv
          </div>
          <div className="mt-4">
            <button
              className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-500"
              type="button"
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Upload file"}
            </button>
          </div>
          {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
        </div>
      </div>
    </section>
  );
}
