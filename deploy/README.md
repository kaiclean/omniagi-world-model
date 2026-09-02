# Running the watchdog as a service

`omniagi watch --once` performs one integrity check and exits with the status
that matters: `0` healthy, `1` the harness failed its own constitution. That
exit code is the whole interface — supervise it with whatever your platform
already trusts rather than leaving a `while True` loop in a forgotten terminal.

## Which mode to use

| Mode | Use when |
|---|---|
| `omniagi watch --once` under a timer | **Preferred.** The supervisor owns scheduling, restarts and alert routing. |
| `omniagi watch` (long-running loop) | Containers or hosts with no timer facility. Has built-in exponential backoff. |

The `--once` form is what CI exercises, so it is the path with test coverage.

## Linux (systemd)

```bash
sudo install -m 0644 deploy/omniagi-watchdog.service /etc/systemd/system/
sudo install -m 0644 deploy/omniagi-watchdog.timer   /etc/systemd/system/
# edit User=, Environment=OMNIAGI_ROOT= and WorkingDirectory= in the .service
sudo systemctl daemon-reload
sudo systemctl enable --now omniagi-watchdog.timer
```

Verify and inspect:

```bash
systemctl list-timers omniagi-watchdog.timer
systemctl start omniagi-watchdog.service   # force one run now
journalctl -u omniagi-watchdog.service -n 50
```

The unit is a `oneshot` with `Persistent=true` on the timer, so a machine that
was asleep runs the check on resume instead of skipping it. A skipped check and
a passing check are indistinguishable from the outside, which is precisely the
ambiguity the watchdog exists to remove.

The sandboxing directives (`ProtectSystem=strict`, `ProtectHome=true`,
`ReadWritePaths=` limited to `memory/`) reflect the fact that the watchdog only
reads the harness and appends to its own log. If you widen them, you are
widening the blast radius of a compromised check.

### Alerting

Route failures wherever you already look. Add to the `[Unit]` section:

```ini
OnFailure=omniagi-watchdog-alert@%n.service
```

...and define that unit to page you, post to Slack, or open an issue. Do not
rely on reading the journal: an alert nobody receives is not an alert.

## macOS (launchd)

```bash
cp deploy/com.omniagi.watchdog.plist ~/Library/LaunchAgents/
# replace every CHANGE_ME with your home directory
launchctl load ~/Library/LaunchAgents/com.omniagi.watchdog.plist
launchctl list | grep omniagi
```

To stop it:

```bash
launchctl unload ~/Library/LaunchAgents/com.omniagi.watchdog.plist
```

Logs land in `~/Library/Logs/omniagi-watchdog.log`.

## Containers and everything else

```bash
omniagi watch --interval 900 --max-backoff 3600
```

The loop resets to `--interval` after a healthy check and doubles the delay
after each failure, up to `--max-backoff`. This stops a broken harness from
generating an alert every fifteen minutes forever, while still retrying.

Add `--strict` to treat warnings as failures. Be deliberate about it: an
offline engine seat is reported as a warning, so a strict watchdog on a laptop
will page you for being on a plane.

## What the watchdog actually checks

Everything `omniagi check` covers — registry validity, generated-doc staleness,
constitution invariants, constitution file hashes against `memory/manifest.json`,
markdown links, memory expiry, and seat evidence freshness.

Constitution hash drift is the reason to run this on a schedule rather than only
in CI. CI sees what was committed; the watchdog sees what is on disk right now,
which is where tampering would actually appear.
