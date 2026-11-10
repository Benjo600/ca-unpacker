# Update pipeline — how a push reaches every installed app

![update flow](update-flow.svg)

```mermaid
flowchart TB
    P["You or Darshan push to GitHub<br/>feat: = new feature · fix: = existing feature update · anything else = small update"]
    P --> CI{"GitHub Actions<br/>build-installer workflow"}
    CI -->|push is docs/web/landing only| SKIP["No build, no noise"]
    CI -->|"code changed"| BUILD["Bump version to 0.11.<run number><br/>PyInstaller app + updater helper<br/>Inno Setup one-file installer"]
    BUILD --> REL["Publish prerelease v0.11.X on GitHub Releases<br/>body carries the exact size + sha256"]
    REL --> TAB["Admin dashboard — New features tab:<br/>Auto-built installers ready to test"]
    TAB --> TEST["Install the build on a machine<br/>and try one real job"]
    TEST -->|not good| BAD["Skip this build — CI<br/>publishes a better one next push"]
    TEST -->|good| DRAFT['Create release draft' button<br/>version, url, size, sha256 and notes pre-filled]
    DRAFT --> PUB2["Publish — second confirmation,<br/>withdraws the previous release"]
    PUB2 --> POPUP["Every signed-in app pops:<br/>NEW UPDATE AVAILABLE"]
    POPUP --> NOW["Install now: download → verify size + sha256 twice<br/>→ silent install → reopen, still signed in"]
    POPUP --> LATER["Later: stays away until the<br/>app is closed and reopened"<br/>]
    BAD -.->|next push| P
```

## Roles

| Step | Who | Where |
| --- | --- | --- |
| Push feature/fix commits | you + Darshan | GitHub `main` (or branches, then merged) |
| Build installer | GitHub Actions (automatic) | `.github/workflows/build-installer.yml` |
| Test the build | founder | a Windows machine with the previous version |
| Publish the release | founder | dashboard `/admin/releases` |
| Receive the update | every signed-in customer | desktop app, `Install now` / `Later` |

## Safety rails

- The app refuses downloads whose **size or SHA-256** does not match the release record — verified again inside the update helper just before installing.
- Only HTTPS links on `github.com` / `objects.githubusercontent.com` / `github-releases.githubusercontent.com` are accepted.
- Prereleases on GitHub never install anywhere: installed apps only take versions **published in the Supabase control plane**.
- Publishing withdraws the previous release automatically, so exactly one is live.
- Mandatory releases (a flagged draft) drop the `Later` button and pause new imports until installed; existing packs stay open.
