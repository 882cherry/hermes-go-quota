# opencode-go-quota

Append your **OpenCode Go** quota (5h rolling / weekly / monthly) to every
final assistant reply in [Hermes Agent](https://github.com/NousResearch/hermes-agent) —
but **only when the active model provider is opencode-go**.

```
user: 帮我查一下今天的天气
assistant: 今天晴,25°C……

opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]
```

Zero changes to Hermes core. Works on CLI, Telegram, and every other gateway
platform, including streaming mode (the streamed message is edited in place).

---

## Why this exists

OpenCode Go (https://opencode.ai) has **no public token/API-key endpoint** for
querying your remaining quota — the community works around this by fetching the
dashboard page with your browser `auth` cookie and parsing the embedded usage
data. This plugin wraps that approach into a single drop-in Hermes plugin:

- `quota.py` — standalone fetcher (also usable as a CLI: `python quota.py`)
- `__init__.py` — Hermes plugin wiring via the `transform_llm_output` hook

Both are stdlib-only (no pip dependencies).

---

## Install

```bash
# 1. Clone into Hermes' user plugin directory
git clone https://github.com/<you>/opencode-go-quota ~/.hermes/plugins/opencode-go-quota

# 2. Enable it
hermes plugins enable opencode-go-quota

# 3. Restart the gateway (or start a new session for CLI)
hermes gateway restart
```

Verify: `hermes plugins list | grep opencode-go-quota` → `enabled`.

> **Note**: if you already have an older standalone copy of
> `opencode_go_quota.py` in `~/.hermes/scripts/`, you can delete it — the
> plugin ships its own fetcher.

---

## Configure: get your auth cookie

OpenCode Go has no API for quota, so the plugin needs the `auth` cookie from
your browser session (it starts with `Fe26.`).

1. Log in to https://opencode.ai in your browser
2. Open DevTools (F12) → **Application** → **Cookies** → `https://opencode.ai`
3. Copy the value of the `auth` cookie

Then write it to one of:

**Option A — Hermes home (recommended):**

```json
// ~/.hermes/opencode_go_quota.json
{
  "auth_cookie": "Fe26.2a**...copy-your-cookie...**",
  "workspace_id": "wrk_xxx"   // optional — auto-resolved when omitted
}
```

**Option B — XDG config:**

```json
// ~/.config/opencode-go-quota/config.json
{ "auth_cookie": "Fe26....", "workspace_id": "wrk_xxx" }
```

**Option C — environment variable** (highest priority):

```bash
export OPENCODE_GO_AUTH_COOKIE="Fe26...."
export OPENCODE_GO_WORKSPACE_ID="wrk_xxx"   # optional
```

The cookie **expires** — when the quota line stops appearing, re-copy it from
the browser and update the file. There is no auto-refresh (login needs a
human).

---

## How it works

```
assistant turn finishes
   └─ agent/turn_finalizer.py fires "transform_llm_output" hook
        └─ this plugin appends:  "<reply>\nopencode-go 5h 62% · 周 45% · 月 18%"
```

- The plugin only appends when Hermes' `model.provider == "opencode-go"` (or
  `model.base_url` contains `opencode.ai/zen/go`) — switch providers and the
  line disappears automatically.
- Quota data is cached for 60 seconds, so the dashboard is fetched at most
  once per minute no matter how many replies you get.
- Any failure (network, expired cookie, unparseable page) is **silent** — the
  reply goes out unchanged.
- `OPENCODE_GO_QUOTA_MODE=always` forces the line even when provider detection
  disagrees (e.g. a custom base_url).

---

## Optional: show the quota UNDER the runtime footer

By default the quota line is appended directly to the reply text, so with the
built-in runtime footer enabled you see:

```
<reply>

opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]

deepseek-v4-flash · 6% · ~      ← runtime footer (model · context% · cwd)
```

If you prefer the quota **below** the footer (`... · 6% · ~` on the first line,
quota on the second), apply the optional 15-line patch to
`gateway/runtime_footer.py` that adds an `opencode_go` field:

```bash
cd ~/.hermes/hermes-agent
git apply patches/runtime_footer_opencode_go.patch   # or apply manually, see below
hermes gateway restart
```

Then add the field to your config:

```yaml
display:
  runtime_footer:
    enabled: true
    fields: [model, context_pct, cwd, opencode_go]
```

> ⚠️ This patch modifies a Hermes core file. It is **optional** — the plugin
> works without it. A Hermes update may overwrite the patch; re-apply after
> updating. (Patch contents are inline in [`docs/runtime-footer-patch.md`](docs/runtime-footer-patch.md).)

---

## CLI usage

The fetcher also works standalone:

```bash
python quota.py            # one-line summary (60s cache)
python quota.py --refresh  # bypass cache
```

Output: `opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]`
(empty + exit 1 on any failure — safe for cron/watchdog use).

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No quota line at all | Cookie missing/expired → re-copy `auth` from browser. Or provider isn't opencode-go (check `model.provider` in `~/.hermes/config.yaml`) |
| `401/403` in `python quota.py` | Cookie expired → re-login and update config |
| Line shows old values | 60s cache → wait, or `python quota.py --refresh` |
| Plugin not enabled | `hermes plugins enable opencode-go-quota`, then restart gateway |

---

## Files

```
opencode-go-quota/
├── plugin.yaml        # plugin manifest (transform_llm_output hook)
├── __init__.py        # Hermes plugin: provider detection + hook wiring
├── quota.py           # stdlib-only quota fetcher (CLI + library)
├── patches/
│   └── runtime_footer_opencode_go.patch   # optional: quota under the footer
└── docs/
    └── runtime-footer-patch.md            # human-readable patch instructions
```

## License

MIT
