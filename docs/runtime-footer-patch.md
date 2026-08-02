# Optional: quota line under the runtime footer

The plugin's default integration appends the quota line directly to the reply
text via the `transform_llm_output` hook. With Hermes' built-in runtime footer
enabled, the message looks like:

```
<reply>

opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]

deepseek-v4-flash · 6% · ~
```

If you want the quota **below** the footer (footer on the first line, quota on
the second), apply this optional 15-line patch that adds an `opencode_go`
field to Hermes' runtime footer.

## Apply

```bash
cd ~/.hermes/hermes-agent
git apply ../.hermes/plugins/opencode-go-quota/patches/runtime_footer_opencode_go.patch
# or from the plugin dir:
#   git -C ~/.hermes/hermes-agent apply "$(pwd)/patches/runtime_footer_opencode_go.patch"
hermes gateway restart
```

Then add the field to `~/.hermes/config.yaml` (using `hermes config set` or a
text editor):

```yaml
display:
  runtime_footer:
    enabled: true
    fields: [model, context_pct, cwd, opencode_go]
```

The order of `fields` is the display order; put `opencode_go` last to get:

```
deepseek-v4-flash · 6% · ~
opencode-go 5h 62% (3h后) · 周 45% (2d后) · 月 18% (12d后) [pro]
```

## What the patch does

`gateway/runtime_footer.py` gains:

1. A new recognized field name `opencode_go` in `format_runtime_footer()`
   (skipped there — IO is done in `build_footer_line`).
2. `_opencode_go_script_path()` — locates the standalone script
   (`~/.hermes/scripts/opencode_go_quota.py` or
   `$HERMES_HOME/scripts/opencode_go_quota.py`).
3. `_is_opencode_go_provider(user_config)` — true when
   `model.provider == "opencode-go"` or `model.base_url` contains
   `opencode.ai/zen/go`.
4. `_opencode_go_quota_line()` — runs the script (6s timeout, silent failure).
5. `build_footer_line()` — when the field is enabled AND the provider is
   opencode-go, appends the quota line below the regular footer.

> **Standalone script required.** The patch calls a separate script at
> `~/.hermes/scripts/opencode_go_quota.py`. With the plugin installed you can
> symlink it:
>
> ```bash
> ln -sf ~/.hermes/plugins/opencode-go-quota/quota.py ~/.hermes/scripts/opencode_go_quota.py
> ```
>
> (The plugin repo's `quota.py` is the same file the standalone patch expects.)

## Caveats

- **Core file.** This modifies a Hermes core file; a Hermes update may
  overwrite it — re-apply the patch after updating.
- **Alternative without the patch.** If you don't want to touch core, keep the
  default plugin behavior (quota line above the footer). Functionally identical
  information, just a different line order.
- **CLI sessions** also render the runtime footer via the same code path, so
  the patched footer works there too.
