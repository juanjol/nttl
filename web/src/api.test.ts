import { describe, expect, it, vi, beforeEach } from "vitest";
import { api, getIn, patchFor, setIn } from "./api";

describe("config path helpers", () => {
  it("builds a nested patch", () => {
    expect(patchFor(["capture", "output", "jpeg_quality"], 80)).toEqual({
      capture: { output: { jpeg_quality: 80 } },
    });
  });

  it("keeps sibling values when setting", () => {
    const base = { capture: { session_name: "a", interval_s: 5 } };
    expect(setIn(base, ["capture", "interval_s"], 10)).toEqual({
      capture: { session_name: "a", interval_s: 10 },
    });
  });

  it("reads nested values and tolerates gaps", () => {
    expect(getIn({ a: { b: 2 } }, ["a", "b"])).toBe(2);
    expect(getIn({ a: {} }, ["a", "b", "c"])).toBeUndefined();
  });
});

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends json and returns the parsed body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ name: "gain", value: 200 }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.setControl("gain", 200)).resolves.toEqual({ name: "gain", value: 200 });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/camera/control");
    expect(JSON.parse(init.body)).toEqual({ name: "gain", value: 200 });
    expect(init.headers["content-type"]).toBe("application/json");
  });

  it("surfaces the server detail on errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        statusText: "Bad Request",
        json: async () => ({ detail: "unknown control" }),
      }),
    );
    await expect(api.setControl("nope", 1)).rejects.toThrow("unknown control");
  });

  it("falls back to the status text when there is no detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        statusText: "Conflict",
        json: async () => {
          throw new Error("no body");
        },
      }),
    );
    await expect(api.stopSession()).rejects.toThrow("Conflict");
  });
});
