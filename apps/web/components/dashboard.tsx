"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import type { Session } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/client";

type Workspace = { id: string; name: string; slug: string };
type Agent = {
  id: string;
  kind: string;
  configured: boolean;
  capabilities?: string[];
  provider?: string;
  durable_checkpointing?: boolean;
};
type ModelStatus = {
  provider: string;
  configured: boolean;
  reachable: boolean | null;
  model_available: boolean | null;
  model?: string | null;
  message?: string;
};
type Memory = {
  id: string;
  memory_key: string;
  title: string;
  content: string;
  memory_type: string;
  status: string;
};
type Run = {
  id: string;
  thread_id: string;
  status: string;
  objective: string;
  result?: { coordinator?: { output?: string } };
  error_summary?: string;
  created_at: string;
};
type KnowledgeFile = { id: string; original_name: string; mime_type: string; size_bytes: number; department?: string | null; status: string; extraction_summary?: string | null; created_at: string };
type KnowledgeChunk = { id: string; chunk_index: number; content: string; locator_type: string; locator: Record<string, unknown> };
type Approval = {
  id: string;
  title: string;
  description: string;
  status: string;
  risk_level: string;
  expires_at?: string;
};
type RunResponse = {
  run_id: string;
  thread_id: string;
  status: string;
  memories_used?: number;
  coordinator?: { output?: string; error?: string; agent_id?: string };
};

const API_BASE = (process.env.NEXT_PUBLIC_CHARVI_API_URL || "").replace(/\/$/, "");

async function apiRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  if (!API_BASE) {
    throw new Error("Set NEXT_PUBLIC_CHARVI_API_URL in apps/web/.env.local.");
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload as T;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function statusClass(value: string | boolean | null | undefined) {
  if (value === true || value === "succeeded" || value === "completed" || value === "approved") {
    return "status good";
  }
  if (value === false || value === "failed" || value === "rejected") {
    return "status bad";
  }
  return "status neutral";
}

export function Dashboard({ initialEmail }: { initialEmail: string | null }) {
  const supabase = useMemo(() => createClient(), []);
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [email, setEmail] = useState(initialEmail || "");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceName, setWorkspaceName] = useState("My Workspace");
  const [workspaceBusy, setWorkspaceBusy] = useState(false);

  const [agents, setAgents] = useState<Agent[]>([]);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [knowledgeFiles, setKnowledgeFiles] = useState<KnowledgeFile[]>([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadDepartment, setUploadDepartment] = useState("");
  const [extractingFileId, setExtractingFileId] = useState("");
  const [selectedKnowledgeFile, setSelectedKnowledgeFile] = useState("");
  const [knowledgeChunks, setKnowledgeChunks] = useState<KnowledgeChunk[]>([]);
  const [dataBusy, setDataBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);

  const [task, setTask] = useState("");
  const [taskContext, setTaskContext] = useState("");
  const [threadId, setThreadId] = useState("");
  const [useMemory, setUseMemory] = useState(true);
  const [taskBusy, setTaskBusy] = useState(false);
  const [lastResult, setLastResult] = useState<RunResponse | null>(null);

  const [memoryKey, setMemoryKey] = useState("");
  const [memoryTitle, setMemoryTitle] = useState("");
  const [memoryContent, setMemoryContent] = useState("");
  const [memoryType, setMemoryType] = useState("preference");
  const [memoryBusy, setMemoryBusy] = useState(false);

  const [history, setHistory] = useState<Array<{ role: string; content: string }>>([]);
  const [historyTitle, setHistoryTitle] = useState("");
  const [voiceLanguage, setVoiceLanguage] = useState("en-IN");
  const [voiceId, setVoiceId] = useState("af_heart");
  const [voiceStatus, setVoiceStatus] = useState("");
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordStatus, setRecordStatus] = useState("");
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
      mediaRecorderRef.current?.stop();
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const refreshVoices = () => setAvailableVoices(window.speechSynthesis.getVoices());
    refreshVoices();
    window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", refreshVoices);
  }, []);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("charvi.voiceId");
      if (saved && /^(af_(heart|bella|nicole)|bf_emma|hf_(alpha|beta))$/.test(saved)) {
        setVoiceId(saved);
      }
    } catch {
      // Voice preferences are optional; private browsing may disable local storage.
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("charvi.voiceId", voiceId);
    } catch {
      // Keep the current in-memory choice if browser storage is unavailable.
    }
  }, [voiceId]);

  useEffect(() => {
  if (!supabase) {
      setAuthLoading(false);
      return;
    }

    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        if (data.session?.user.email) setEmail(data.session.user.email);
        setAuthLoading(false);
      }
    });

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession?.user.email) setEmail(nextSession.user.email);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, [supabase]);

  const token = session?.access_token || "";

  const refreshWorkspaceData = useCallback(async (accessToken: string, id: string) => {
    setDataBusy(true);
    setError("");
    const results = await Promise.allSettled([
      apiRequest<Agent[]>("/v1/agents", accessToken),
      apiRequest<ModelStatus>("/v1/models/status", accessToken),
      apiRequest<Memory[]>(`/v1/workspaces/${id}/memories`, accessToken),
      apiRequest<Run[]>(`/v1/workspaces/${id}/agent-runs`, accessToken),
      apiRequest<Approval[]>(`/v1/workspaces/${id}/approvals?status=pending`, accessToken),
      apiRequest<KnowledgeFile[]>(`/v1/workspaces/${id}/knowledge-files`, accessToken),
    ]);

    if (results[0].status === "fulfilled") setAgents(results[0].value);
    if (results[1].status === "fulfilled") setModel(results[1].value);
    if (results[2].status === "fulfilled") setMemories(results[2].value);
    if (results[3].status === "fulfilled") setRuns(results[3].value);
    if (results[4].status === "fulfilled") setApprovals(results[4].value);
    if (results[5].status === "fulfilled") setKnowledgeFiles(results[5].value);

    const failed = results.find((result) => result.status === "rejected");
    if (failed?.status === "rejected") {
      setError(failed.reason instanceof Error ? failed.reason.message : "Some dashboard data could not be loaded.");
    }
    setDataBusy(false);
  }, []);

  useEffect(() => {
    if (!token || !API_BASE) return;
    let active = true;
    apiRequest<Workspace[]>("/v1/workspaces", token)
      .then((items) => {
        if (!active) return;
        setWorkspaces(items);
        setWorkspaceId((current) =>
          current && items.some((item) => item.id === current) ? current : items[0]?.id || "",
        );
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load workspaces.");
      });
    return () => {
      active = false;
    };
  }, [token, refreshTick]);

  useEffect(() => {
    if (!token || !workspaceId) return;
    void refreshWorkspaceData(token, workspaceId);
  }, [token, workspaceId, refreshTick, refreshWorkspaceData]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setAuthBusy(true);
    setAuthError("");
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError) setAuthError(signInError.message);
    setAuthBusy(false);
  }

  async function signUp() {
    if (!supabase) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      const { error: signUpError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback?next=/`,
        },
      });
      setAuthError(
        signUpError
          ? signUpError.message
          : "Account created. Check your email to confirm it, then sign in here.",
      );
    } catch (reason) {
      setAuthError(reason instanceof Error ? reason.message : "Account creation failed.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    if (supabase) await supabase.auth.signOut();
    setSession(null);
    setWorkspaceId("");
    setWorkspaces([]);
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setWorkspaceBusy(true);
    setError("");
    try {
      const created = await apiRequest<Workspace>("/v1/workspaces", token, {
        method: "POST",
        body: JSON.stringify({ name: workspaceName }),
      });
      setWorkspaces((current) => [...current, created]);
      setWorkspaceId(created.id);
      setNotice("Workspace created.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workspace creation failed.");
    } finally {
      setWorkspaceBusy(false);
    }
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !workspaceId || !task.trim()) return;
    setTaskBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest<RunResponse>("/v1/agent-runs", token, {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          task: task.trim(),
          context: taskContext,
          thread_id: threadId || undefined,
          use_saved_memory: useMemory,
        }),
      });
      setLastResult(result);
      setThreadId(result.thread_id);
      setNotice(`Task ${result.status}. Saved memories used: ${result.memories_used ?? 0}.`);
      setTask("");
      setRefreshTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The task could not be started.");
    } finally {
      setTaskBusy(false);
    }
  }



  async function extractKnowledgeFile(fileId: string) {
    if (!token || !workspaceId) return;
    setExtractingFileId(fileId);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest<{ summary: string }>(
        `/v1/workspaces/${workspaceId}/knowledge-files/${fileId}/extract`, token, { method: "POST" },
      );
      setNotice(result.summary);
      setSelectedKnowledgeFile(fileId);
      const chunks = await apiRequest<KnowledgeChunk[]>(
        `/v1/workspaces/${workspaceId}/knowledge-files/${fileId}/chunks`, token,
      );
      setKnowledgeChunks(chunks);
      await refreshWorkspaceData(token, workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Document extraction failed.");
      await refreshWorkspaceData(token, workspaceId);
    } finally {
      setExtractingFileId("");
    }
  }

  async function viewKnowledgeChunks(fileId: string) {
    if (!token || !workspaceId) return;
    setSelectedKnowledgeFile(fileId);
    try {
      const chunks = await apiRequest<KnowledgeChunk[]>(
        `/v1/workspaces/${workspaceId}/knowledge-files/${fileId}/chunks`, token,
      );
      setKnowledgeChunks(chunks);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load extracted text.");
    }
  }

  async function uploadKnowledgeFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("knowledgeFiles");
    if (!(input instanceof HTMLInputElement) || !input.files?.length || !token || !workspaceId) return;
    setUploadBusy(true);
    setError("");
    setNotice("");
    try {
      for (const file of Array.from(input.files)) {
        const form = new FormData();
        form.append("file", file);
        if (uploadDepartment) form.append("department", uploadDepartment);
        const response = await fetch(`${API_BASE}/v1/workspaces/${workspaceId}/knowledge-files`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
          cache: "no-store",
        });
        const result: unknown = await response.json().catch(() => null);
        if (!response.ok) {
          const detail = typeof result === "object" && result !== null && "detail" in result
            ? String((result as { detail: unknown }).detail)
            : `Upload failed (${response.status})`;
          throw new Error(`${file.name}: ${detail}`);
        }
      }
      input.value = "";
      setNotice("Upload complete. Files are stored privately; extraction is the next pipeline stage.");
      await refreshWorkspaceData(token, workspaceId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "One or more files could not be uploaded.");
    } finally {
      setUploadBusy(false);
    }
  }

  async function saveMemory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !workspaceId) return;
    setMemoryBusy(true);
    setError("");
    try {
      const key =
        memoryKey.trim() ||
        memoryTitle.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      await apiRequest("/v1/workspaces/" + workspaceId + "/memories", token, {
        method: "POST",
        body: JSON.stringify({
          memory_key: key,
          title: memoryTitle,
          content: memoryContent,
          memory_type: memoryType,
        }),
      });
      setMemoryKey("");
      setMemoryTitle("");
      setMemoryContent("");
      setNotice("Memory saved to this workspace.");
      setRefreshTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Memory could not be saved.");
    } finally {
      setMemoryBusy(false);
    }
  }

  async function archiveMemory(id: string) {
    if (!token || !workspaceId) return;
    try {
      await apiRequest(
        `/v1/workspaces/${workspaceId}/memories/${id}/archive`,
        token,
        { method: "POST" },
      );
      setNotice("Memory archived.");
      setRefreshTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Memory could not be archived.");
    }
  }

  async function decideApproval(id: string, decision: "approved" | "rejected") {
    if (!token) return;
    try {
      await apiRequest(`/v1/approvals/${id}/decision`, token, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setNotice(`Approval ${decision}.`);
      setRefreshTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approval decision failed.");
    }
  }

  async function resumeRun(id: string) {
    if (!token) return;
    try {
      const result = await apiRequest<RunResponse>(`/v1/agent-runs/${id}/resume`, token, {
        method: "POST",
      });
      setLastResult(result);
      setNotice("Task recovery completed.");
      setRefreshTick((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Task could not be resumed.");
    }
  }

  async function showHistory(run: Run) {
    if (!token || !workspaceId || !run.thread_id) return;
    try {
      const items = await apiRequest<Array<{ role: string; content: string }>>(
        `/v1/workspaces/${workspaceId}/threads/${run.thread_id}/history`,
        token,
      );
      setHistory(items);
      setHistoryTitle(run.objective);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Thread history could not be loaded.");
    }
  }

  function toggleVoiceInput() {
  if (recognitionRef.current) {
    recognitionRef.current.stop();
    setIsListening(false);
    setVoiceStatus("Voice capture stopped.");
    return;
  }

  const SpeechRecognitionApi =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionApi) {
    setVoiceStatus("Voice dictation is not supported in this browser. You can still type your task.");
    return;
  }

  const recognition = new SpeechRecognitionApi();
  recognition.lang = voiceLanguage;
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onresult = (event) => {
    let finalTranscript = "";
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0]?.transcript || "";
      if (event.results[index].isFinal) finalTranscript += transcript;
      else interimTranscript += transcript;
    }
    if (finalTranscript.trim()) {
      setTask((current) =>
        current.trim()
          ? `${current.trim()} ${finalTranscript.trim()}`
          : finalTranscript.trim(),
      );
    }
    setVoiceStatus(
      interimTranscript
        ? `Listening: ${interimTranscript}`
        : finalTranscript
          ? "Speech added to your task."
          : "Listening…",
    );
  };
  recognition.onerror = (event) => {
    setVoiceStatus(`Voice input error: ${event.error}`);
    setIsListening(false);
    recognitionRef.current = null;
  };
  recognition.onend = () => {
    setIsListening(false);
    recognitionRef.current = null;
  };

  recognitionRef.current = recognition;
  setIsListening(true);
  setVoiceStatus("Listening…");
  recognition.start();
  }

  async function togglePrivateRecording() {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setRecordStatus("Recording stopped. Transcribing privately…");
      return;
    }
    if (!token || !API_BASE) {
      setRecordStatus("Sign in and connect the Charvi API before using private transcription.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setRecordStatus("Private microphone recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      audioChunksRef.current = [];
      const preferredMime = "audio/webm;codecs=opus";
      const recorder = MediaRecorder.isTypeSupported(preferredMime)
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setRecordStatus("The microphone recording failed.");
        setIsRecording(false);
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaStreamRef.current = null;
      };
      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaStreamRef.current = null;
        setIsRecording(false);
        if (!audioBlob.size) {
          setRecordStatus("No audio was captured. Please try again.");
          return;
        }

        const extension = audioBlob.type.includes("mp4")
          ? "m4a"
          : audioBlob.type.includes("ogg")
            ? "ogg"
            : "webm";
        const form = new FormData();
        form.append("file", audioBlob, `charvi-recording.${extension}`);
        form.append(
          "language",
          voiceLanguage === "hi-IN" ? "hi" : voiceLanguage === "kn-IN" ? "kn" : "en",
        );
        try {
          const response = await fetch(`${API_BASE}/v1/voice/transcribe`, {
            method: "POST",
            headers: { Authorization: `Bearer ${token}` },
            body: form,
            cache: "no-store",
          });
          const result: unknown = await response.json().catch(() => null);
          if (!response.ok) {
            const detail =
              typeof result === "object" && result !== null && "detail" in result
                ? String((result as { detail: unknown }).detail)
                : `Private transcription failed (${response.status}).`;
            throw new Error(detail);
          }
          const transcript =
            typeof result === "object" && result !== null && "text" in result
              ? String((result as { text: unknown }).text).trim()
              : "";
          if (!transcript) {
            setRecordStatus("I couldn't detect speech in that recording.");
            return;
          }
          setTask((current) =>
            current.trim() ? `${current.trim()} ${transcript}` : transcript,
          );
          setRecordStatus("Transcription added to your task. Audio was discarded by the worker.");
        } catch (reason) {
          setRecordStatus(
            reason instanceof Error
              ? `Private transcription unavailable: ${reason.message}. Use device dictation as a fallback.`
              : "Private transcription unavailable. Use device dictation as a fallback.",
          );
        }
      };
      recorder.start();
      setIsRecording(true);
      setRecordStatus("Recording on this device. Press Stop when finished.");
    } catch (reason) {
      setRecordStatus(
        reason instanceof Error
          ? `Microphone permission or device error: ${reason.message}`
          : "Microphone permission or device error.",
      );
    }
  }

  async function speakLastResponse(previewText?: string) {
    const text = previewText || lastResult?.coordinator?.output;
    if (!text) return;

    if (voiceLanguage !== "kn-IN") {
      try {
        if (!token || !API_BASE) throw new Error("Private voice service is not connected.");
        const response = await fetch(`${API_BASE}/v1/voice/speak`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ text: text.slice(0, 4000), voice: voiceId }),
          cache: "no-store",
        });
        if (response.ok) {
          const audioBlob = await response.blob();
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          audio.onended = () => URL.revokeObjectURL(audioUrl);
          audio.onerror = () => URL.revokeObjectURL(audioUrl);
          await audio.play();
          setVoiceStatus(`Speaking with Charvi's ${voiceId} feminine voice.`);
          return;
        }
        if (response.status !== 503) {
          throw new Error("Private voice service returned an error.");
        }
      } catch (reason) {
        setVoiceStatus(
          reason instanceof Error
            ? `Using your device voice fallback. ${reason.message}`
            : "Using your device voice fallback.",
        );
      }
    } else {
      setVoiceStatus("Kokoro does not currently offer Kannada; using an available device voice.");
    }

    if (!("speechSynthesis" in window)) {
      setVoiceStatus("Speech playback is not supported in this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.slice(0, 4000));
    utterance.lang = voiceLanguage;
    const languagePrefix = voiceLanguage.split("-")[0].toLowerCase();
    const preferred = availableVoices.filter((voice) =>
      voice.lang.toLowerCase().startsWith(languagePrefix),
    );
    const femaleName = /female|woman|samantha|victoria|karen|zira|susan|siri|aria|jenny|sonia|heera|priya|lekha|swara/i;
    utterance.voice =
      preferred.find((voice) => femaleName.test(voice.name)) ||
      availableVoices.find((voice) => femaleName.test(voice.name)) ||
      null;
    window.speechSynthesis.speak(utterance);
    setVoiceStatus(
      utterance.voice
        ? `Reading with device voice: ${utterance.voice.name}. Availability depends on your device.`
        : "No feminine device voice was detected. Install/select a feminine voice in your operating system's speech settings.",
    );
  }


  if (!supabase) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div className="brand-mark">C</div>
          <p className="eyebrow">CHARVI / OWNER CONSOLE</p>
          <h1>Connect your workspace.</h1>
          <p className="muted">Add the public Supabase URL and publishable key to apps/web/.env.local. Never add a service-role key here.</p>
        </section>
      </main>
    );
  }

  if (authLoading) {
    return <main className="auth-shell"><div className="loader">Loading Charvi…</div></main>;
  }

  if (!session) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div className="brand-mark">C</div>
          <p className="eyebrow">CHARVI / OWNER CONSOLE</p>
          <h1>Your AI workforce, in one place.</h1>
          <p className="muted">Sign in to manage your agents, saved memories, approvals and tasks.</p>
          <form className="stack" onSubmit={signIn}>
            <label>Email<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            {authError && <p className="error">{authError}</p>}
            <button className="primary" disabled={authBusy}>{authBusy ? "Please wait…" : "Sign in"}</button>
            <button className="text-button" type="button" disabled={authBusy} onClick={() => { window.location.href = "/reset-password"; }}>Forgot password?</button>
            <button className="quiet" type="button" disabled={authBusy} onClick={signUp}>Create account</button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-row"><div className="brand-mark small">C</div><div><strong>CHARVI</strong><span>AI WORKSPACE</span></div></div>
        <nav>
          <a href="#overview" className="nav-active">Overview</a>
          <a href="#workforce">Workforce</a>
          <a href="#knowledge">Knowledge Hub</a><a href="#run-task">Run a task</a>
          <a href="#memories">Memory vault</a>
          <a href="#approvals">Approvals <span className="nav-count">{approvals.length}</span></a>
          <a href="#activity">Activity</a>
        </nav>
        <div className="sidebar-bottom">
          <span className="muted tiny">{session.user.email || initialEmail}</span>
          <button className="quiet full" onClick={signOut}>Sign out</button>
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div><p className="eyebrow">PERSONAL AI OPERATING SYSTEM</p><h1>Good to see you.</h1></div>
          <div className="top-actions">
            <select aria-label="Workspace" value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
            <button className="quiet" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "Light mode" : "Dark mode"}</button>
          </div>
        </header>

        {error && <div className="alert error-box">{error}</div>}
        {notice && <div className="alert notice-box">{notice}</div>}

        {workspaces.length === 0 ? (
          <section className="panel empty-workspace">
            <p className="eyebrow">FIRST STEP</p><h2>Create your workspace</h2>
            <p className="muted">Your tasks, memories and approvals are kept inside a workspace you own.</p>
            <form className="inline-form" onSubmit={createWorkspace}>
              <input value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} aria-label="Workspace name" maxLength={80} required />
              <button className="primary" disabled={workspaceBusy}>{workspaceBusy ? "Creating…" : "Create workspace"}</button>
            </form>
          </section>
        ) : (
          <>
            <section id="overview" className="stats-grid">
              <article className="stat-card"><span className="muted">Configured agents</span><strong>{agents.filter((agent) => agent.configured).length}</strong><small>{agents.length} listed in registry</small></article>
              <article className="stat-card"><span className="muted">Saved memories</span><strong>{memories.length}</strong><small>Owner-controlled facts</small></article>
              <article className="stat-card"><span className="muted">Recent runs</span><strong>{runs.length}</strong><small>Latest 50 tasks</small></article>
              <article className="stat-card"><span className="muted">Pending approvals</span><strong>{approvals.length}</strong><small>Owner decisions required</small></article>
            </section>

            <section className="panel model-panel">
              <div><p className="eyebrow">COORDINATOR MODEL</p><h2>{model?.provider || "Model status unavailable"}</h2><p className="muted">{model?.message || "Connect the Charvi API to inspect model readiness."}</p></div>
              <span className={statusClass(model?.configured && model?.reachable !== false)}>{model?.configured ? (model?.reachable ? "Reachable" : "Configured") : "Not configured"}</span>
            </section>

            <section id="workforce" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">SPECIALIST NETWORK</p><h2>Workforce</h2></div><button className="quiet" onClick={() => setRefreshTick((value) => value + 1)} disabled={dataBusy}>{dataBusy ? "Refreshing…" : "Refresh"}</button></div>
              <div className="agent-grid">
                {agents.map((agent) => (
                  <article className="agent-card" key={agent.id}>
                    <div className="card-top"><strong>{agent.id.replaceAll("_", " ")}</strong><span className={statusClass(agent.configured)}>{agent.configured ? "Configured" : "Setup needed"}</span></div>
                    <p className="muted tiny">{agent.kind.replaceAll("_", " ")}</p>
                    <p className="tiny">{agent.capabilities?.slice(0, 3).join(" · ") || "Agent capability registry"}</p>
                    {agent.durable_checkpointing !== undefined && <small className="muted">Durable checkpoints: {agent.durable_checkpointing ? "on" : "waiting for database URI"}</small>}
                  </article>
                ))}
                {agents.length === 0 && <p className="muted">Agent registry is not connected yet.</p>}
              </div>
            </section>


            <section id="knowledge" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">PRIVATE DOCUMENT VAULT</p><h2>Knowledge Hub</h2></div><span className="status neutral">15 MB per file</span></div>
              <form className="panel stack" onSubmit={uploadKnowledgeFiles}>
                <label>Choose documents, spreadsheets, presentations or images
                  <input name="knowledgeFiles" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.ppt,.pptx,.txt,.jpg,.jpeg,.png,.webp" />
                </label>
                <label>Department
                  <select value={uploadDepartment} onChange={(event) => setUploadDepartment(event.target.value)}>
                    <option value="">Unassigned — let Charvi classify later</option>
                    <option>Finance &amp; Treasury</option><option>Accounting &amp; Tax</option><option>Sales &amp; Revenue</option><option>Marketing</option><option>Human Resources</option><option>Operations &amp; Supply Chain</option><option>Customer Support</option><option>Legal &amp; Compliance</option><option>Projects &amp; IT</option><option>Procurement &amp; Vendors</option><option>Strategy &amp; Executive Office</option>
                  </select>
                </label>
                <div className="form-row"><p className="muted tiny">PDF, Office files, CSV, TXT, JPG, PNG and WEBP. File signature is checked; browser MIME headers are not trusted.</p><button className="primary" disabled={uploadBusy}>{uploadBusy ? "Uploading…" : "Upload privately"}</button></div>
              </form>
              <div className="run-list">
                {knowledgeFiles.map((file) => <article className="run-card" key={file.id}>
                  <div className="card-top"><strong>{file.original_name}</strong><span className={statusClass(file.status === "ready" ? "completed" : file.status === "failed" ? "failed" : null)}>{file.status}</span></div>
                  <small className="muted">{file.department || "Unassigned"} · {(file.size_bytes / 1024 / 1024).toFixed(2)} MB · {formatDate(file.created_at)}</small>
                  <small className="muted">{file.extraction_summary || "Original stored privately; extract to make its contents searchable."}</small>
                  <div className="form-row">
                    <button className="quiet" type="button" onClick={() => void viewKnowledgeChunks(file.id)}>View extracted text</button>
                    <button className="primary" type="button" disabled={extractingFileId === file.id || file.status === "processing"} onClick={() => void extractKnowledgeFile(file.id)}>
                      {extractingFileId === file.id ? "Extracting…" : file.status === "ready" ? "Re-extract" : "Extract document"}
                    </button>
                  </div>
                </article>)}
                {selectedKnowledgeFile && <article className="panel stack">
                  <div className="card-top"><strong>Extracted source text</strong><button className="text-button" type="button" onClick={() => { setSelectedKnowledgeFile(""); setKnowledgeChunks([]); }}>Close</button></div>
                  {knowledgeChunks.map((chunk) => <div className="history-message" key={chunk.id}>
                    <small className="muted">Chunk {chunk.chunk_index + 1} · {chunk.locator_type} · {JSON.stringify(chunk.locator)}</small>
                    <p>{chunk.content}</p>
                  </div>)}
                  {knowledgeChunks.length === 0 && <p className="muted">No extracted chunks are available yet.</p>}
                </article>}
                {knowledgeFiles.length === 0 && <p className="muted">No files uploaded to this workspace yet.</p>}
              </div>
            </section>

            <section id="run-task" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">COMMAND CENTRE</p><h2>Give Charvi a task</h2></div></div>
              <form className="panel stack" onSubmit={submitTask}>
                <label>What should Charvi do?<textarea value={task} onChange={(event) => setTask(event.target.value)} rows={3} maxLength={12000} placeholder="Research, analyse, build or organise something…" required /></label>
                <label>Additional context <textarea value={taskContext} onChange={(event) => setTaskContext(event.target.value)} rows={2} maxLength={20000} placeholder="Optional context or instructions" /></label>
                <div className="voice-controls">
                  <button className="quiet" type="button" onClick={toggleVoiceInput} disabled={isListening && !recognitionRef.current}>
                    {isListening ? "Stop listening" : "🎙 Device dictation"}
                  </button>
                  <button className={isRecording ? "primary" : "quiet"} type="button" onClick={() => void togglePrivateRecording()}>
                    {isRecording ? "Stop private recording" : "Record privately"}
                  </button>
                  <label className="voice-language">Speech language
                    <select value={voiceLanguage} onChange={(event) => {
                      const language = event.target.value;
                      setVoiceLanguage(language);
                      if (language === "hi-IN") setVoiceId("hf_alpha");
                      if (language === "en-IN") setVoiceId("af_heart");
                    }}>
                      <option value="en-IN">English (India)</option>
                      <option value="kn-IN">Kannada</option>
                      <option value="hi-IN">Hindi</option>
                    </select>
                  </label>
                  <label className="voice-language">Charvi's voice
                    <select value={voiceId} onChange={(event) => {
                      const selected = event.target.value;
                      setVoiceId(selected);
                      setVoiceLanguage(selected.startsWith("hf_") ? "hi-IN" : "en-IN");
                    }}>
                      <option value="af_heart">Heart — warm feminine English</option>
                      <option value="af_bella">Bella — friendly feminine English</option>
                      <option value="af_nicole">Nicole — clear feminine English</option>
                      <option value="bf_emma">Emma — British feminine English</option>
                      <option value="hf_alpha">Alpha — feminine Hindi</option>
                      <option value="hf_beta">Beta — feminine Hindi</option>
                    </select>
                  </label>
                  <button className="quiet" type="button" onClick={() => void speakLastResponse("Hello, I'm Charvi. How can I help you today?")}>Preview feminine voice</button>
                  <span className="muted tiny">{availableVoices.length} device voices detected. Kokoro voices are used when the private voice worker is connected; otherwise Charvi selects an available device voice.</span>
                  <span className="muted tiny">{recordStatus || "Private Whisper records only while you press Record privately."}</span>
                  <span className="muted tiny">{voiceStatus || "Browser speech recognition may use your browser or device speech provider."}</span>
                </div>

                <div className="form-row"><label className="check-label"><input type="checkbox" checked={useMemory} onChange={(event) => setUseMemory(event.target.checked)} /> Use relevant saved memories</label><button className="primary" disabled={taskBusy || !task.trim()}>{taskBusy ? "Working…" : "Send to Charvi"}</button></div>
                {threadId && <p className="muted tiny">Continuing thread: {threadId} <button className="text-button" type="button" onClick={() => setThreadId("")}>Start new thread</button></p>}
              </form>
              {lastResult && <article className="panel result-panel"><div className="card-top"><strong>Latest response</strong><span className={statusClass(lastResult.status)}>{lastResult.status}</span></div><p>{lastResult.coordinator?.output || lastResult.coordinator?.error || "No response text returned."}</p><div className="form-row"><small className="muted">Run {lastResult.run_id} · {lastResult.memories_used ?? 0} memories used</small>{lastResult.coordinator?.output && <button className="quiet" type="button" onClick={() => void speakLastResponse()}>Read response aloud</button>}</div></article>}
            </section>

            <section id="memories" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">OWNER-CONTROLLED</p><h2>Memory vault</h2></div></div>
              <form className="panel stack" onSubmit={saveMemory}>
                <div className="form-row two">
                  <label>Memory title<input value={memoryTitle} onChange={(event) => setMemoryTitle(event.target.value)} maxLength={160} required placeholder="My GST workflow" /></label>
                  <label>Memory type<select value={memoryType} onChange={(event) => setMemoryType(event.target.value)}><option value="preference">Preference</option><option value="profile">Profile</option><option value="project">Project</option><option value="workflow">Workflow</option><option value="reference">Reference</option></select></label>
                </div>
                <label>Memory key <input value={memoryKey} onChange={(event) => setMemoryKey(event.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, "-"))} maxLength={160} placeholder="Optional — generated from title" /></label>
                <label>What should Charvi remember?<textarea value={memoryContent} onChange={(event) => setMemoryContent(event.target.value)} rows={3} maxLength={4000} required placeholder="Write a useful fact or preference. Do not save passwords or API keys." /></label>
                <div className="form-row"><p className="muted tiny">Only save information you want retained across tasks.</p><button className="primary" disabled={memoryBusy}>{memoryBusy ? "Saving…" : "Save memory"}</button></div>
              </form>
              <div className="memory-list">
                {memories.map((memory) => <article className="memory-card" key={memory.id}><div className="card-top"><div><strong>{memory.title}</strong><small className="muted">{memory.memory_type} · {memory.memory_key}</small></div><button className="text-button" onClick={() => archiveMemory(memory.id)}>Archive</button></div><p>{memory.content}</p></article>)}
                {memories.length === 0 && <p className="muted">No saved memories yet. Add one above; Charvi won't silently save every conversation.</p>}
              </div>
            </section>

            <section id="approvals" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">OWNER IN CONTROL</p><h2>Pending approvals</h2></div></div>
              <div className="approval-list">
                {approvals.map((approval) => <article className="approval-card" key={approval.id}><div className="card-top"><strong>{approval.title}</strong><span className="status neutral">{approval.risk_level}</span></div><p className="muted">{approval.description}</p><small className="muted">Expires {approval.expires_at ? formatDate(approval.expires_at) : "according to policy"}</small><div className="form-row approval-actions"><button className="quiet" onClick={() => decideApproval(approval.id, "rejected")}>Reject</button><button className="primary" onClick={() => decideApproval(approval.id, "approved")}>Approve</button></div></article>)}
                {approvals.length === 0 && <p className="muted">No pending approvals.</p>}
              </div>
            </section>

            <section id="activity" className="section-block">
              <div className="section-heading"><div><p className="eyebrow">TASK HISTORY</p><h2>Recent activity</h2></div></div>
              <div className="run-list">
                {runs.map((run) => <article className="run-card" key={run.id}><div className="card-top"><strong>{run.objective}</strong><span className={statusClass(run.status)}>{run.status}</span></div><small className="muted">{formatDate(run.created_at)}</small>{run.result?.coordinator?.output && <p>{run.result.coordinator.output.slice(0, 260)}{run.result.coordinator.output.length > 260 ? "…" : ""}</p>}{run.error_summary && <p className="error">{run.error_summary}</p>}<div className="form-row run-actions"><button className="text-button" onClick={() => showHistory(run)}>View thread</button>{(run.status === "failed" || run.status === "running") && <button className="quiet" onClick={() => resumeRun(run.id)}>Resume task</button>}</div></article>)}
                {runs.length === 0 && <p className="muted">Your completed and interrupted tasks will appear here.</p>}
              </div>
            </section>
          </>
        )}

        {history.length > 0 && <section className="history-drawer"><div className="card-top"><strong>Thread history</strong><button className="text-button" onClick={() => setHistory([])}>Close</button></div><p className="muted tiny">{historyTitle}</p>{history.map((message, index) => <div className="history-message" key={index}><strong>{message.role}</strong><p>{message.content}</p></div>)}</section>}
        <footer className="footer-note">Charvi Control Plane · Your data stays in your Supabase workspace.</footer>
      </section>
    </main>
  );
}
