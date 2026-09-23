/**
 * Backend client. Every response uses the same envelope, so unwrapping and error
 * handling live here rather than in each component.
 */

import type { AnalysisResult } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Envelope<T> = { status: "ok"; data: T } | { status: "error"; message: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  let body: Envelope<T>;
  try {
    body = (await response.json()) as Envelope<T>;
  } catch {
    // A proxy timing out, or the backend dying mid-request, never reaches the envelope.
    throw new ApiError(
      response.ok ? "the server sent a response we could not read" : response.statusText,
      response.status,
    );
  }

  if (body.status === "error") {
    throw new ApiError(body.message, response.status);
  }
  if (!response.ok) {
    throw new ApiError(response.statusText, response.status);
  }
  return body.data;
}

export interface AnalyseOptions {
  genre?: string;
  useLlm?: boolean;
  signal?: AbortSignal;
}

export async function analyse(
  file: File,
  { genre, useLlm = true, signal }: AnalyseOptions = {},
): Promise<AnalysisResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("use_llm", String(useLlm));
  if (genre?.trim()) {
    form.append("genre", genre.trim());
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/analyze`, { method: "POST", body: form, signal });
  } catch (cause) {
    if (signal?.aborted) {
      throw new ApiError("analysis cancelled", 0);
    }
    throw new ApiError(`could not reach the analysis server at ${BASE_URL}`, 0);
  }

  return unwrap<AnalysisResult>(response);
}

export async function health(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}
