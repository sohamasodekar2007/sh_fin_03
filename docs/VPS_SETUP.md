# VPS setup — connecting a company-owned server to CloudCare

CloudCare collects telemetry from your VPS over SSH. This is a **read-only**
integration in the current build (see `services/executor/simulated_executor.py`
— any proposal for a VPS resource is refused, not executed) but the key it
uses can still run arbitrary commands unless you lock it down. Follow all of
this, not just the parts that seem necessary for a demo.

**Do not reuse an existing admin/deploy key for this.** Generate a new
key pair specifically for CloudCare. If that key ever leaks, the blast
radius should be "read some system stats," not "here is root."

## 1. Create a dedicated `cloudcare` user

On the VPS, as an existing admin:

```bash
sudo adduser --disabled-password --gecos "" cloudcare
sudo mkdir -p /home/cloudcare/.ssh
sudo chmod 700 /home/cloudcare/.ssh
```

`cloudcare` must **not** be in the `sudo` / `wheel` group, and must have no
password set (`--disabled-password` above already ensures this — verify with
`sudo passwd -S cloudcare`, which should show `L` for locked).

## 2. Generate a new key pair (on your own machine, not the server)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/cloudcare_vps -C "cloudcare-monitor" -N "<a real passphrase>"
```

- Use a real passphrase. It goes in `VPS_SSH_KEY_PASSPHRASE` in `.env` — that
  variable unlocks the encrypted private key file, it is never a login
  password, and CloudCare's SSH client
  (`packages/vps/session.py:VPSConnection`) never accepts a password at all.
- This produces `cloudcare_vps` (private, keep off the server) and
  `cloudcare_vps.pub` (public, goes on the server below).

## 3. Install the public key with a command= restriction

This is the step that turns "a key that can read /proc/stat" into "a key
that can run absolutely anything as the cloudcare user." Do not skip it.

```bash
sudo -u cloudcare tee -a /home/cloudcare/.ssh/authorized_keys > /dev/null <<'EOF'
command="/home/cloudcare/cloudcare-metrics.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...your-public-key-here... cloudcare-monitor
EOF
sudo chmod 600 /home/cloudcare/.ssh/authorized_keys
sudo chown -R cloudcare:cloudcare /home/cloudcare/.ssh
```

Replace `ssh-ed25519 AAAA...` with the actual contents of
`cloudcare_vps.pub`. The `command=` restriction means **every** SSH session
opened with this key runs `cloudcare-metrics.sh` — the client can request
whatever command it wants, `sshd` ignores it and substitutes this one script
instead (paramiko's `exec_command` still works normally from CloudCare's
side; it's the server that's rewriting the command).

Create that wrapper script so the collector's actual commands
(`services/collector/vps/inventory.py`, `metrics.py`) can still reach
`/proc`, `virsh`/`qm`/`lxc-ls`/`docker`, and `sar` through it — the simplest
correct version just execs whatever `sshd` put in `$SSH_ORIGINAL_COMMAND`,
so the restriction is "only this user, only key auth, no shell/port
forwarding," not "only one exact command":

```bash
sudo tee /home/cloudcare/cloudcare-metrics.sh > /dev/null <<'EOF'
#!/bin/sh
# CloudCare's authorized_keys command= wrapper. sshd puts the command the
# client actually asked to run into $SSH_ORIGINAL_COMMAND; this just execs
# it, so the restriction above (no-pty, no forwarding, this user only) is
# what limits blast radius, not a single hardcoded command.
exec /bin/sh -c "$SSH_ORIGINAL_COMMAND"
EOF
sudo chmod 700 /home/cloudcare/cloudcare-metrics.sh
sudo chown cloudcare:cloudcare /home/cloudcare/cloudcare-metrics.sh
```

If you'd rather allowlist exact commands instead of trusting the wrapper,
replace the `exec` line with a `case "$SSH_ORIGINAL_COMMAND" in ... esac`
that only permits the specific `cat`, `df`, `virsh`, `qm`, `lxc-ls`,
`docker`, `sar`, `nproc` invocations CloudCare uses — see
`services/collector/vps/inventory.py` and `metrics.py` for the exact
argv lists.

## 4. Grant access to the virtualization tool actually in use, nothing else

Pick the one that applies:

**KVM/libvirt:**
```bash
sudo usermod -aG libvirt cloudcare
```

**LXC:** `lxc-ls`/`lxc-info` are readable by any user for containers owned by
`root` on most distros; if yours restricts this, add `cloudcare` to
whichever group your distro uses (often `lxd` or `sudo lxc-*` via a narrow
sudoers rule — do **not** grant broad sudo).

**Docker:**
```bash
sudo usermod -aG docker cloudcare
```
Note: membership in the `docker` group is effectively root-equivalent (a
container can bind-mount the host filesystem). If that's an unacceptable
risk for this box, don't add `cloudcare` to it — CloudCare falls back to
treating the whole host as one resource
(`services/collector/vps/inventory.py::_collect_host_only`), which is a
strictly safer, still-honest degradation.

**Proxmox VE (`qm`):** `qm list`/`qm config` need root or a PVE role with
`VM.Audit`; a plain Linux group won't help here. If you're not comfortable
granting that, again, host-only fallback is the safe default.

If `cloudcare` can't reach any of these, CloudCare doesn't error the whole
collection run — it just reports the host as a single resource. Confirm
which detection path actually ran via the Monitor agent's response
(`detection_path` field) or the `agent_runs` collection, not by assuming.

## 5. Install sysstat, so history isn't empty for two weeks

The analyzer's idle/over-provisioned rules need 7-14 days of samples before
they'll fire at all. Without a backfill, an hourly-only collector needs two
full weeks before the VPS card shows anything. `sysstat` already keeps
7-28 days of history on disk — CloudCare reads it once, on first connect.

```bash
sudo apt update && sudo apt install -y sysstat   # Debian/Ubuntu
# or: sudo dnf install -y sysstat                # RHEL/Fedora

sudo sed -i 's/^ENABLED="false"/ENABLED="true"/' /etc/default/sysstat  # Debian/Ubuntu path
sudo systemctl enable --now sysstat
```

Verify it's actually collecting (give it a few minutes after enabling):
```bash
test -d /var/log/sa && echo "sysstat directory exists" && ls /var/log/sa
```

If `/var/log/sa` is empty or missing, CloudCare doesn't fail — it sets
`vps_history_warm=false` on the account and the UI shows "collecting
history — N of 14 days" instead of an empty panel
(`services/collector/vps/metrics.py::backfill_from_sar`). But real history
from day one is much better than a two-week warm-up, so do this now, before
you connect the VPS in CloudCare, not after.

## 6. Fill in `.env`

```bash
VPS_HOST=<your server's IP or hostname>
VPS_PORT=22
VPS_USERNAME=cloudcare
VPS_SSH_KEY_PATH=~/.ssh/cloudcare_vps
VPS_SSH_KEY_PASSPHRASE=<the passphrase from step 2>
VPS_COMPANY_NAME=<your company/team name — appears as FOCUS PublisherName>
VPS_MONTHLY_COST=1800
VPS_MONTHLY_COST_CURRENCY=INR
```

## 7. Test the connection manually before connecting it in CloudCare

```bash
ssh -i ~/.ssh/cloudcare_vps cloudcare@<VPS_HOST> 'cat /proc/stat | head -1'
```

This must succeed and print a `cpu  ...` line before you rely on CloudCare's
own connection — `paramiko.AuthenticationException` almost always means the
private key's file permissions are wrong (`chmod 600 ~/.ssh/cloudcare_vps`)
or the `command=` restriction is misconfigured; this manual test isolates
which one, faster than debugging it through the app.

## Optional: Prometheus / node_exporter instead of SSH

If you already run `node_exporter` on this box (or a Prometheus server that
scrapes it), set `VPS_METRICS_ENDPOINT` to that Prometheus server's base URL
and CloudCare prefers it automatically over SSH for metrics — better data,
real time series, no SSH round trip per sample
(`services/collector/vps/metrics.py::sample_prometheus_metrics`). SSH is
still used for inventory (`virsh`/`qm`/`lxc-ls`/`docker` detection)
regardless — node_exporter doesn't know about individual VMs/containers,
only the host.
