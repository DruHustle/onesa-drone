import { api, APIError } from "./api.ts";
import type { Operations } from "./types";

export type StreamStatus =
  | "connecting"
  | "receiving"
  | "updates delayed"
  | "reconnecting"
  | "storage unavailable"
  | "account service unavailable"
  | "updates unavailable";

// The API sends a snapshot every second, including when the fleet is idle.
const silenceLimitMs = 12_000;

export function subscribeToOperations(
  onSnapshot: (value: Operations) => void,
  onStatus: (status: StreamStatus) => void,
  onExpired: () => void,
) {
  let active: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout>;
  let retries = 0;
  let lastSnapshotAt = -Infinity;

  function stop() {
    clearTimeout(timer);
    const stream = active;
    active = null;
    stream?.close();
  }

  function connect() {
    const stream = new EventSource("/api/v1/stream");
    active = stream;
    let receivedFrame = false;

    function retry(status: StreamStatus) {
      if (active !== stream) return;
      stop();
      onStatus(status);
      const delay = Math.min(30_000, 1000 * 2 ** Math.min(retries++, 5));
      timer = setTimeout(connect, delay);
    }

    function watchForSilence() {
      clearTimeout(timer);
      timer = setTimeout(() => retry("updates delayed"), silenceLimitMs);
    }

    watchForSilence();
    stream.addEventListener("telemetry", (event: MessageEvent<string>) => {
      if (active !== stream) return;
      let snapshot: Operations;
      try {
        snapshot = JSON.parse(event.data);
        if (
          snapshot?.mode !== "simulation" ||
          !Number.isFinite(snapshot.at) ||
          !Array.isArray(snapshot.aircraft) ||
          !Array.isArray(snapshot.missions) ||
          !snapshot.counts ||
          !snapshot.truncated
        )
          return retry("updates unavailable");
      } catch {
        return retry("updates unavailable");
      }
      // A replay from a stale intermediary cannot restore a healthy feed or
      // extend the silence timer. Preserve the newest snapshot across reconnects.
      if (snapshot.at <= lastSnapshotAt) return;
      lastSnapshotAt = snapshot.at;
      receivedFrame = true;
      retries = 0;
      watchForSilence();
      onSnapshot(snapshot);
      onStatus("receiving");
    });
    stream.addEventListener("expired", () => {
      if (active !== stream) return;
      stop();
      onExpired();
    });
    stream.addEventListener("unavailable", (event: MessageEvent<string>) => {
      if (active !== stream) return;
      let reason: unknown;
      try {
        reason = JSON.parse(event.data)?.reason;
      } catch {
        // Older servers may omit the reason.
      }
      retry(
        reason === "identity"
          ? "account service unavailable"
          : reason === "storage"
            ? "storage unavailable"
            : "updates unavailable",
      );
    });
    stream.onerror = async () => {
      if (active !== stream) return;
      if (receivedFrame) return retry("reconnecting");

      // EventSource hides the HTTP status when a new stream is rejected.
      // Recheck the signed-in session before repeatedly opening a new stream.
      stream.onerror = null;
      stream.close();
      clearTimeout(timer);
      onStatus("reconnecting");
      try {
        await api("/auth/me");
      } catch (error) {
        if (active !== stream) return;
        if (error instanceof APIError && [401, 403].includes(error.status)) {
          stop();
          onExpired();
          return;
        }
      }
      retry("reconnecting");
    };
  }

  connect();
  return stop;
}
