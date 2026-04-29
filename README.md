# Git2Confluence

Generate documentation from GitLab repositories and publish it to Confluence, following the Porsche PASSTEN template structure.

## What It Does

Three-stage pipeline:

1. **Extract** — Scans GitLab repos (README, CI config, Dockerfiles, IaC, tests, dependencies) via REST API
2. **Synthesize** — Generates structured documentation using Claude API
3. **Publish** — Creates/updates Confluence pages via MCP server

Auto-generated pages get a 🤖 suffix in their title. Placeholder pages (requiring manual input) stay clean.

## Prerequisites

- Python 3.11+
- [mcporsche](https://github.com/porsche-code/ai4it-mcporsche) running locally (Confluence MCP on port 8001)
- GitLab token (via `glab auth login` or `GITLAB_TOKEN` env var)
- `ANTHROPIC_API_KEY` env var (only needed for `generate` / synthesis stage)

## Install

```bash
pip install -r passten/requirements.txt
```

## Usage

Before any publish command, make sure mcporsche is running:

```bash
cd ~/workspace/mcporsche && docker compose up -d
```

### Option A: Full pipeline (requires ANTHROPIC_API_KEY)

```bash
export ANTHROPIC_API_KEY=sk-...
python3 passten-generator.py generate --solution GFS
```

### Option B: Manual workflow with Claude Code

```bash
# 1. Extract repo data
python3 passten-generator.py extract --solution GFS --output gfs-extraction.json

# 2. Open Claude Code, let it read gfs-extraction.json,
#    generate page content, and save as passten-pages-full.json

# 3. Publish the generated pages
python3 passten-generator.py publish --input passten-pages-full.json --solution GFS
```

### Option C: Re-publish from cache

If you already have a `passten-pages-full.json` from a previous run:

```bash
python3 passten-generator.py publish --input passten-pages-full.json --solution GFS
```

## Configuration

Edit `passten-config.yaml`:

```yaml
solutions:
  GFS:
    gitlab_group_id: 4155
    gitlab_host: cicd.skyway.porsche.com
    confluence_space: GFS
    confluence_parent_id: "2451554935"
    language: en
    products:
      GFS:
        include_subgroups:
          - gff-crs
        exclude_patterns:
          - gfs-cls
        min_activity: "2025-06-01"
      PDA:
        subgroup_id: 75593
```

| Field | Description |
|---|---|
| `gitlab_group_id` | Top-level GitLab group ID |
| `gitlab_host` | Corporate GitLab hostname |
| `confluence_space` | Target Confluence space key |
| `confluence_parent_id` | Parent page ID under which all pages are created |
| `products` | Map of product names to repo discovery config |
| `min_activity` | Ignore repos with no commits after this date |
| `exclude_patterns` | Repo name substrings to skip |
| `subgroup_id` | Discover repos from a specific subgroup instead |

## Page Structure (PASSTEN Template)

The generated hierarchy follows the Porsche PASSTEN standard:

```
Digital Solution Home 🤖
├── Vision
├── Roadmap 🤖
├── Roles
├── Digital Solution Intent 🤖
│   ├── Architecture 🤖
│   ├── Compliance 🤖
│   ├── Data 🤖
│   ├── Functional 🤖
│   ├── Test Concept 🤖
│   ├── Test Evidences 🤖
│   ├── KPIs
│   └── Accessibility
└── Service Management
    ├── Software Development Culture 🤖
    ├── Deployment 🤖
    ├── Logging and Monitoring 🤖
    ├── Change Management 🤖
    ├── Configuration Management 🤖
    ├── Incident Management
    ├── Problem Management
    ├── Service Level Management
    ├── Support / Maintenance
    └── User Documentation
```

🤖 = auto-generated from code | no suffix = requires manual input

## Architecture

```
passten-generator.py          # CLI entrypoint
passten-config.yaml           # Solution configuration
passten/
├── config.py                 # YAML config loader
├── extractor.py              # GitLab REST API client
├── publisher.py              # Confluence MCP client (JSON-RPC)
├── synthesizer.py            # Claude API content generation
├── templates.py              # PASSTEN page hierarchy & section definitions
└── requirements.txt          # Python dependencies
```
