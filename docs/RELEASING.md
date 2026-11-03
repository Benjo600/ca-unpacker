# Releasing a desktop update

This is the founder checklist for shipping a new CA Unpacker build to installed
copies. It matches the self-update flow in the app: the app asks Supabase for the
one published release, downloads it from GitHub, checks the exact size and
fingerprint, installs it silently, and reopens.

Nothing here uploads client documents. Only release metadata (version, notes,
installer link, size, fingerprint) lives in Supabase.

---

## 1. Build and verify the installer

1. Bump the version in exactly one place: `apps/version.py` (`APP_VERSION`).
2. Run `build_installer.bat`. It reads that version, builds the app, builds
   `CAUnpackerUpdater.exe`, copies the helper into the app folder, and passes
   `/DAppVersion=<version>` to Inno Setup.
3. Check `dist\CAUnpacker\CAUnpackerUpdater.exe` exists next to
   `dist\CAUnpacker\CAUnpacker.exe`.
4. Install the new build on a clean Windows VM and complete one small job
   (import a file, open the pack). This proves the build itself is sound before
   anyone else sees it.

## 2. Get the exact size and fingerprint

PowerShell, from the repo root:

```powershell
$file = "dist\CAUnpacker-Setup.exe"
(Get-Item $file).Length
(Get-FileHash $file -Algorithm SHA256).Hash.ToLower()
```

Both values go into the release record. The app refuses the download if either
does not match, so copy them exactly.

## 3. Upload the installer to GitHub Releases

1. Create a GitHub Release tagged `v<version>` in the `Benjo600/ca-unpacker`
   repository.
2. Attach `CAUnpacker-Setup.exe` as the release asset.
3. Copy the asset's download URL. It must start with
   `https://github.com/` (or the `objects.githubusercontent.com` /
   `github-releases.githubusercontent.com` asset hosts). Other hosts are refused
   by both the server and the desktop app.

## 4. Deploy the release control plane (first time only)

The Supabase side must be deployed before any release can be published:

- Apply `supabase/migrations/20261103120000_app_releases.sql`.
- Deploy these Edge Functions with JWT verification on:
  `admin-list-releases`, `admin-save-release`, `admin-publish-release`,
  `admin-withdraw-release`, `latest-release`.
- Keep `ADMIN_ALLOWED_EMAILS` set to the founder addresses; the admin functions
  reject anyone else.

## 5. Create the draft

In the admin dashboard (`/admin/releases/new`) fill in:

- version (must be `major.minor.patch`, higher than the installed version),
- title and release notes (shown to the user),
- installer URL from step 3,
- SHA-256 and size from step 2,
- mandatory (only when old versions must stop processing),
- minimum supported version (optional; older clients are forced to update).

Save as a draft. Drafts are never visible to users.

## 6. Publish, with the second confirmation

Publishing asks for the version, mandatory/optional status, host, checksum
prefix and an acknowledgement before the final button enables. Publishing also
withdraws the previously published release automatically, so there is exactly
one live release.

What users see:

- A newer optional release shows the Profile update card with Download, Install
  and Later.
- A mandatory release shows the same card without Later and a banner saying new
  processing is paused. Existing packs, profile and logout keep working.

## 7. Verify on a real install

1. On a machine with the previous version signed in, open Profile.
2. Check the card appears with the right version and notes.
3. Download, then Install and restart. The app should close, install silently
   and reopen, still signed in, with local work untouched.
4. Re-run the same check: no update should be offered.
5. If the release is mandatory, confirm a new dump is refused with the exact
   message and that existing packs still open.

## 8. Withdrawing a bad release

Withdraw from the admin list. Installed copies are unaffected, but future checks
stop seeing the release. Publish a corrected higher version instead of
re-publishing the withdrawn one; a withdrawn version cannot return to draft.

## Safety rules that must not be relaxed

- Never execute an installer that has not passed the size and SHA-256 check
  twice (after download, and again in the helper just before running).
- Never allow an HTTP link or a host outside the approved list.
- Never delete `%LOCALAPPDATA%\CAUnpacker` during an update.
- A mandatory update blocks new processing only; it must not lock the app.
