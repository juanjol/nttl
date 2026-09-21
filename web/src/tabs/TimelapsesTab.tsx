import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, Section } from "../components/controls";
import type { SessionEntry, VideoEntry } from "../types";
import type { TabProps } from "./common";

function megabytes(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export function TimelapsesTab({ snapshot }: TabProps) {
  const [videos, setVideos] = useState<VideoEntry[]>([]);
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [playing, setPlaying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const compileState = snapshot.jobs.find((job) => job.name.startsWith("compile:"))?.state;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.videos(), api.sessions()])
      .then(([videoBody, sessionBody]) => {
        if (cancelled) return;
        setVideos(videoBody.videos);
        setSessions(sessionBody.sessions);
        setError(null);
      })
      .catch((exc: Error) => !cancelled && setError(exc.message));
    return () => {
      cancelled = true;
    };
  }, [compileState, snapshot.session.state]);

  const pending = sessions.filter((session) => session.videos.length === 0 && session.frames > 0);

  return (
    <div>
      <Section title="Compiled timelapses">
        <div className="flex gap-2 pb-2">
          <Button onClick={() => void api.openFolder("sessions").catch((exc: Error) => setError(exc.message))}>
            Open folder
          </Button>
        </div>
        {videos.length === 0 && (
          <p className="text-sm text-slate-500">No timelapse compiled yet.</p>
        )}
        <ul className="flex flex-col gap-2">
          {videos.map((video) => (
            <li
              key={video.path}
              className="rounded-md border border-edge bg-panel-soft/60 px-2 py-1.5 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-slate-200">{video.name}</div>
                  <div className="text-slate-500">
                    {video.session}, {megabytes(video.size_bytes)},{" "}
                    {video.modified_utc.slice(0, 16).replace("T", " ")}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    onClick={() => setPlaying(playing === video.url ? null : video.url)}
                  >
                    {playing === video.url ? "Hide" : "Play"}
                  </Button>
                  <Button
                    onClick={() =>
                      void api
                        .openFolder("sessions", video.session)
                        .catch((exc: Error) => setError(exc.message))
                    }
                  >
                    Folder
                  </Button>
                </div>
              </div>
              {playing === video.url && (
                <video className="mt-2 w-full rounded" src={video.url} controls autoPlay />
              )}
            </li>
          ))}
        </ul>
        {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      </Section>

      <Section title="Sessions without a video">
        {pending.length === 0 && <p className="text-sm text-slate-500">Every session is compiled.</p>}
        <ul className="flex flex-col gap-2">
          {pending.map((session) => (
            <li
              key={session.name}
              className="flex items-center justify-between gap-2 rounded-md border border-edge bg-panel-soft/60 px-2 py-1.5 text-xs"
            >
              <div>
                <div className="text-slate-200">{session.name}</div>
                <div className="text-slate-500">{session.frames} frames</div>
              </div>
              <Button
                disabled={!snapshot.ffmpeg.available}
                onClick={() =>
                  void api.compile(session.name).catch((exc: Error) => setError(exc.message))
                }
              >
                Compile
              </Button>
            </li>
          ))}
        </ul>
        {!snapshot.ffmpeg.available && (
          <p className="mt-2 text-xs text-amber-300">
            ffmpeg was not found, so videos cannot be compiled.
          </p>
        )}
      </Section>
    </div>
  );
}
