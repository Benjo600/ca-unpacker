import {
  compareVersions,
  isApprovedInstallerUrl,
  normalizeChecksum,
  parseReleaseInput,
  parseVersion,
  publicRelease,
  selectLatestRelease,
  type ReleaseRecord,
} from "./releases.ts";

function assertEquals<T>(actual: T, expected: T, message?: string) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${message ?? "not equal"}: ${a} !== ${b}`);
}

function assertThrows(fn: () => unknown, contains?: string) {
  try {
    fn();
  } catch (err) {
    if (contains && !String((err as Error).message).includes(contains)) {
      throw new Error(`wrong error: ${(err as Error).message}`);
    }
    return;
  }
  throw new Error("expected an error");
}

function record(overrides: Partial<ReleaseRecord> = {}): ReleaseRecord {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    version: "0.12.0",
    title: "Faster reconciliation",
    release_notes: "Notes",
    installer_url:
      "https://github.com/Benjo600/ca-unpacker/releases/download/v0.12.0/CAUnpacker-Setup.exe",
    installer_sha256: "a".repeat(64),
    installer_size: 12345,
    status: "published",
    mandatory: false,
    minimum_supported_version: null,
    created_by: "founder@example.com",
    created_at: "2026-11-03T10:00:00Z",
    published_by: "founder@example.com",
    published_at: "2026-11-03T10:05:00Z",
    withdrawn_by: null,
    withdrawn_at: null,
    ...overrides,
  };
}

Deno.test("version parsing is strict", () => {
  assertEquals(parseVersion("v1.2.3"), "1.2.3");
  assertThrows(() => parseVersion("1.2"), "1.2.3");
  assertThrows(() => parseVersion("1.2.3-beta"), "1.2.3");
  assertThrows(() => parseVersion("1.2.3.4"), "1.2.3");
});

Deno.test("version comparison", () => {
  assertEquals(compareVersions("1.2.3", "1.2.3"), 0);
  assertEquals(compareVersions("1.2.4", "1.2.3"), 1);
  assertEquals(compareVersions("1.1.9", "1.2.0"), -1);
  assertEquals(compareVersions("2.0.0", "1.99.99"), 1);
});

Deno.test("installer URLs must be https on approved hosts", () => {
  assertEquals(
    isApprovedInstallerUrl(
      "https://github.com/Benjo600/ca-unpacker/releases/download/v1/Setup.exe",
    ),
    true,
  );
  assertEquals(
    isApprovedInstallerUrl("https://objects.githubusercontent.com/asset.exe"),
    true,
  );
  assertEquals(isApprovedInstallerUrl("http://github.com/a.exe"), false);
  assertEquals(isApprovedInstallerUrl("https://evil.example.com/a.exe"), false);
  assertEquals(isApprovedInstallerUrl("https://github.com.evil.example/a.exe"), false);
  assertEquals(isApprovedInstallerUrl("https://user:pass@github.com/a.exe"), false);
  assertEquals(isApprovedInstallerUrl("https://github.com:8443/a.exe"), false);
});

Deno.test("checksum normalisation", () => {
  assertEquals(normalizeChecksum("A".repeat(64)), "a".repeat(64));
  assertThrows(() => normalizeChecksum("abc"), "64");
  assertThrows(() => normalizeChecksum("z".repeat(64)), "64");
});

Deno.test("release input validation", () => {
  const input = parseReleaseInput({
    version: "v0.12.0",
    title: " Update ",
    release_notes: "Notes",
    installer_url:
      "https://github.com/Benjo600/ca-unpacker/releases/download/v0.12.0/Setup.exe",
    installer_sha256: "A".repeat(64),
    installer_size: 100,
    mandatory: true,
    minimum_supported_version: "0.10.0",
  });
  assertEquals(input.version, "0.12.0");
  assertEquals(input.title, "Update");
  assertEquals(input.installer_sha256, "a".repeat(64));
  assertEquals(input.mandatory, true);

  assertThrows(() => parseReleaseInput({ version: "0.12.0" }), "Title");
  assertThrows(
    () =>
      parseReleaseInput({
        version: "0.12.0",
        title: "x",
        installer_url: "http://github.com/a.exe",
        installer_sha256: "a".repeat(64),
        installer_size: 1,
      }),
    "approved",
  );
  assertThrows(
    () =>
      parseReleaseInput({
        version: "0.12.0",
        title: "x",
        installer_url: "https://github.com/a.exe",
        installer_sha256: "a".repeat(64),
        installer_size: 1,
        extra: true,
      }),
    "Unexpected field",
  );
});

Deno.test("only a newer published release is selected", () => {
  assertEquals(selectLatestRelease("0.12.0", record()), null);
  assertEquals(selectLatestRelease("0.11.0", record())?.version, "0.12.0");
  assertEquals(selectLatestRelease("0.13.0", record()), null);
  assertEquals(selectLatestRelease("0.11.0", record({ status: "draft" })), null);
  assertEquals(selectLatestRelease("0.11.0", record({ status: "withdrawn" })), null);
  assertEquals(selectLatestRelease("0.11.0", null), null);
});

Deno.test("mandatory comes from the flag or the minimum version", () => {
  assertEquals(selectLatestRelease("0.11.0", record({ mandatory: true }))?.mandatory, true);
  assertEquals(
    selectLatestRelease(
      "0.9.0",
      record({ mandatory: false, minimum_supported_version: "0.10.0" }),
    )?.mandatory,
    true,
  );
  assertEquals(
    selectLatestRelease(
      "0.11.0",
      record({ mandatory: false, minimum_supported_version: "0.10.0" }),
    )?.mandatory,
    false,
  );
});

Deno.test("public release hides internal identities", () => {
  const shown = publicRelease(record({ mandatory: true }));
  assertEquals(Object.keys(shown).sort(), [
    "installer_sha256",
    "installer_size",
    "installer_url",
    "mandatory",
    "published_at",
    "release_notes",
    "title",
    "version",
  ]);
});
