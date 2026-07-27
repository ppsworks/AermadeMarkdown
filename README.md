# AermadeMarkdown

Convert office documents, PDFs, email and HTML to Markdown, for use as grounding material
for AI agents.

Two modes share the same conversion core:

- **[SharePoint mode](#sharepoint-mode-microsoft-graph)** (`md-convert-sp`) reads files
  directly from SharePoint and writes Markdown mirrors back to a dedicated SharePoint
  site. This is the main path.
- **[Local mode](#local-mode)** (`md-convert`) converts files on disk, folder to folder.
  Useful for one-off files, and for testing conversions without touching SharePoint.

## Supported formats

| Extension | Converter |
|-----------|-----------|
| `.docx` | MarkItDown |
| `.html`, `.htm` | MarkItDown |
| `.pptx` | MarkItDown |
| `.xlsx`, `.xlsm`, `.xls` | MarkItDown |
| `.pdf` | PyMuPDF4LLM (long text-only) or MarkItDown (short/image-heavy) |
| `.msg` | MarkItDown (Outlook email) |
| `.eml` | Python stdlib `email` (RFC-822 email) |
| `.zip` | MarkItDown (extracts and converts the contents) |

The PDF converter picks its backend from page count and image density.

`.xlsm` files are converted as `.xlsx`. It's the same OOXML format underneath, and any
embedded macros are ignored.

Email output leads with the `From` / `To` / `Cc` / `Date` / `Subject` headers and lists
attachment filenames, followed by the body. `.eml` prefers the plain-text part and falls
back to converting the HTML alternative. Attachments themselves are not extracted or
converted.

`.zip` archives are expanded, and every file inside that matches a supported format is
converted into one concatenated Markdown document.

Both modes share the same converters, so a format added here works in both.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate      # source .venv/bin/activate on macOS/Linux
pip install -e .
```

This installs two commands: `md-convert-sp` (SharePoint) and `md-convert` (local).

## SharePoint mode (Microsoft Graph)

`md-convert-sp` reads source files **directly from one or more SharePoint sites/libraries**
and writes the Markdown mirrors into a dedicated SharePoint site (e.g. *Aermade AI*). Each
file lands at `<site>/<library>/<original folders>/<file>.md`, so the original site,
library and folder structure survives the trip.

Authentication is **app-only** (client credentials), with no user sign-in. Each file is
downloaded to a temp path just long enough to convert it locally. Nothing is written back
to the source sites, and no file content leaves the machine except the finished Markdown.

### 1. Get an app registration (IT ticket)

Ask IT for an **Entra ID (Azure AD) app registration** with:

1. Microsoft **Graph application permission `Sites.Selected`**, admin-consented.
2. A **client secret** (note the expiry date).
3. A per-site grant of **Read** on each source site and **Read/Write** on the destination
   site. This is the `Sites.Selected` grant an admin performs, so provide the site URLs for
   all sites involved, e.g. `AERMADE`, `Aermade prosjekter`, and `Aermade AI`.
   `Sites.Selected` is least-privilege; `Sites.ReadWrite.All` is the broad fallback if
   `Sites.Selected` isn't available.

You get back three values: **Tenant ID, Client ID, Client secret**. Azure also shows a
*Secret ID*, which is a portal reference rather than the credential. The tool needs the
secret **value**, and that's only visible once, right after the secret is created.

### 2. Configure

```bash
cp .env.example .env                       # AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET
cp sharepoint.example.toml sharepoint.toml # hostname + source/destination sites
```

Both files are git-ignored. `.env` holds the secrets; `sharepoint.toml` holds the
(non-secret) site and library paths.

A site path is the part of the site URL after the hostname. Open the site in a browser and
copy it: `https://contoso.sharepoint.com/sites/AERMADE` → `/sites/AERMADE`. The URL slug is
often not identical to the site's display name.

### 3. Verify the connection

```bash
md-convert-sp --check
```

`--check` tests each part separately: credentials first, then read access per source site,
then write access to the destination (by uploading and deleting a small probe file). That
way a failure points at a single cause.

- **403** on a site while credentials succeed means the app registration is missing that
  site's `Sites.Selected` grant. That's a separate admin step from creating the app.
- **404** usually means the `site_path` is wrong.

It also prints every library in each source site, marked `+` (will be mirrored) or `-`
(skipped), so you can see the scope before anything moves.

### 4. Run

```bash
# See what would happen — lists each source file and its destination mirror path
md-convert-sp --dry-run

# Convert just the first file end-to-end (safe first test)
md-convert-sp --limit 1

# Full run (all sources in the config)
md-convert-sp

# Re-convert everything, ignoring the incremental cache
md-convert-sp --force

# One-off run against a single site/library/folder, ignoring the config's sources
md-convert-sp --source-site /sites/aermade --source-library "75049 Northern Light Phase 2"
```

A folder-scoped run writes to the same destination paths a full run would, so you can work
through a big library piecemeal and the mirror stays consistent with itself.

### Selecting sources

Sources live in `sharepoint.toml` — see `sharepoint.example.toml`. Each `[[source]]` sets a
`site_path` plus a library selection:

| Key | Meaning |
|-----|---------|
| `library = ""` | the site's default document library |
| `library = "*"` | every library in the site |
| `library = "Name"` | one specific library |
| `libraries = [...]` | explicit allowlist; wins over `library` |
| `exclude = [...]` | names to skip, applied after the above |
| `folder = "..."` | limit the scan to a subfolder |

The same scoping is available per run via `--source-site`, `--source-library` and
`--source-folder`, which override the config's sources entirely.

One caveat worth planning around: every mirror lands in a single destination site under one
permission set. A library that was restricted at the source becomes readable by anyone with
access to the destination, and by any agent grounded on it. Scope deliberately, and curate
the destination afterwards.

### Incremental runs

Repeat runs are incremental. A local `sharepoint_state.json` records each source file's
content version, and unchanged files are skipped without being downloaded, so only new and
modified files cost anything on a re-run. `--force` ignores the cache.

### Reviewing a run

Every file, converted or failed or skipped, is recorded in
`sharepoint_logs/conversion_manifest.jsonl` and tagged with a `run_id`. Each run ends with a
breakdown of anything that needs attention:

- **unsupported** — the extension has no converter (grouped by extension)
- **failed** — the file was handled but broke (grouped by error type)
- **warned** — converted, but the converter flagged something

That last category is the easy one to miss. A file that converts to nothing still uploads a
valid but useless `.md`, and otherwise looks like a success.

```bash
# Replay the last run's breakdown from the manifest — instant, no network
md-convert-sp --report

# Show every path rather than the first 40 of each category
md-convert-sp --report --list-failed --list-unsupported --list-warned

# Cover every run in the manifest, not just the last
md-convert-sp --report --all-runs
```

`--report` only reads the local manifest, with no Graph calls and no credentials, so it
comes back in under a second even for a run that took an hour. The same `--list-*` flags
work during a live run.

A normal re-run won't regenerate any of this, because files that already converted are
skipped via the state cache and never re-examined. `--report` is the way back to a finished
run.

## Local mode

`md-convert` converts files on disk. It shares every converter with SharePoint mode, which
makes it the quickest way to test a conversion: no credentials, no network.

```bash
# Convert all files in ./input to ./output
md-convert

# Convert a single file
md-convert path/to/file.pdf

# Convert a folder to a specific output directory
md-convert path/to/folder -o path/to/output

# Inject YAML frontmatter into each output file
md-convert --frontmatter

# Raise errors instead of writing failure placeholders
md-convert --strict
```

Each converted file is written as `.md`, mirroring the input folder structure. A
`conversion_manifest.jsonl` log lands alongside the output with the status, converter used,
warnings, and errors for each file. Files that fail produce an empty
`_failed_to_convert.md` placeholder unless `--strict` is passed.

## Frontmatter

Pass `--frontmatter` (either mode) to prepend YAML metadata to each output file:

```yaml
---
converted_at: '2026-06-29T05:33:16+00:00'
converter: html_converter
source: report.html
source_path: C:\path\to\report.html
source_type: .html
title: Q3 Cost Report
---
```

`source`, `source_path`, `source_type`, `converter` and `converted_at` are always present.
`title` is included when it can be extracted from the source, and `warnings` when the
conversion produced any. In SharePoint mode, `source_path` is the file's path within its
source library rather than a local path.

## Adding a converter

1. Create a class inheriting from `BaseConverter` in `src/md_converter/converters/`.
2. Set `supported_extensions` and `name`.
3. Implement `convert(self, input_path: Path) -> ConversionResult`.
4. Add an instance to `ConverterRegistry` in `src/md_converter/core/registry.py`.

For formats MarkItDown can handle, inherit from `MarkItDownConverter` instead and skip
step 3. If MarkItDown doesn't recognize an extension but can read the format under another
name, map it via `extension_aliases` (e.g. `XlsxConverter` sets `{".xlsm": ".xlsx"}`).

Converters take a local path and return a `ConversionResult`; they never write files
themselves. Both modes pick them up unchanged, so there's no further wiring.
