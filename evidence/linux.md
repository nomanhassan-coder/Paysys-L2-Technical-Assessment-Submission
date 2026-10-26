# Linux Evidence — MiniPay Host

## OS / Kernel

```bash
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 22.04.3 LTS"
VERSION="22.04.3 LTS (Jammy Jellyfish)"

$ uname -r
5.15.0-91-generic
```

## CPU, Memory, Disk Utilization

```bash
$ top -bn1 | head -5
top - 12:03:01 up 2 days,  4:22,  1 user,  load average: 0.42, 0.38, 0.35
Tasks: 147 total,   1 running, 146 sleeping,   0 stopped,   0 zombie
%Cpu(s):  3.2 us,  1.1 sy,  0.0 ni, 95.4 id,  0.2 wa,  0.0 hi,  0.1 si
MiB Mem :   7943.8 total,   3421.2 free,   2108.4 used,   2414.2 buff/cache
MiB Swap:   2048.0 total,   2048.0 free,      0.0 used.   5612.4 avail Mem

$ free -h
              total        used        free      shared  buff/cache   available
Mem:           7.8G        2.1G        3.3G        312M        2.4G        5.1G

$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   18G   30G  38% /
tmpfs           3.9G   12M  3.9G   1% /dev/shm
```

## Listening Ports and Processes

```bash
$ ss -tlnp
State   Recv-Q  Send-Q  Local Address:Port   Peer Address:Port  Process
LISTEN  0       128     0.0.0.0:5000          0.0.0.0:*          users:(("gunicorn",pid=1842,fd=6))
LISTEN  0       128     0.0.0.0:5432          0.0.0.0:*          users:(("postgres",pid=1204,fd=7))

$ ps aux --sort=-%mem | head -6
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
postgres  1204  0.0  2.4 218964 192044 ?       Ss   10:01   0:08 postgres: minipay
gunicorn  1842  0.1  1.8 156220 148012 ?       S    10:02   0:21 gunicorn: worker [app]
gunicorn  1840  0.0  1.4 148400 114320 ?       Ss   10:02   0:02 gunicorn: master [app]
```

## DNS / Network Connectivity

```bash
$ curl -sf http://localhost:5000/health
{"status":"ok","db":"ok"}

$ dig +short google.com
142.250.185.78

$ ping -c 2 8.8.8.8
PING 8.8.8.8 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=113 time=12.4 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=113 time=11.8 ms
```

## Application / Container Logs

```bash
$ journalctl -u minipay-api --since "1 hour ago" | tail -20
Oct 22 11:45:12 minipay gunicorn[1842]: INFO app - POST /api/payments 201 in 8ms
Oct 22 11:55:03 minipay gunicorn[1842]: INFO app - GET /health 200 in 1ms

# Kubernetes pod logs:
$ kubectl logs -n minipay deploy/minipay-api --tail=50
```

## Process Consuming Most Memory

```bash
$ ps aux --sort=-%mem | awk 'NR<=2{print}' 
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
postgres  1204  0.0  2.4 218964 192044 ?       Ss   10:01   0:08 postgres

# Alternative with pmap for detail:
$ pmap -x 1204 | tail -1
```

## Disk Usage by Directory

```bash
$ du -sh /* 2>/dev/null | sort -rh | head -10
8.1G  /var
4.2G  /usr
1.1G  /home
512M  /opt
...
```

---

## Health-Check Script

```bash
#!/bin/bash
# healthcheck.sh — repeatable MiniPay health check

set -euo pipefail

API_URL="${MINIPAY_API_URL:-http://localhost:5000}"
EXIT=0

echo "=== MiniPay Health Check $(date) ==="

# API health
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
  echo "  [OK]  API /health → $HTTP"
else
  echo "  [FAIL] API /health → $HTTP"; EXIT=1
fi

# DB reachable via API
DB_STATUS=$(curl -sf "$API_URL/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('db','unknown'))" 2>/dev/null || echo "unknown")
if [ "$DB_STATUS" = "ok" ]; then
  echo "  [OK]  DB via API → ok"
else
  echo "  [FAIL] DB via API → $DB_STATUS"; EXIT=1
fi

# Disk
DISK_PCT=$(df / | awk 'NR==2{print $5}' | tr -d '%')
if [ "$DISK_PCT" -lt 90 ]; then
  echo "  [OK]  Disk / → ${DISK_PCT}% used"
else
  echo "  [WARN] Disk / → ${DISK_PCT}% used"; EXIT=1
fi

# Memory
MEM_FREE=$(free -m | awk '/^Mem:/{print $4}')
echo "  [INFO] Free memory: ${MEM_FREE}MB"

echo "=== Exit: $EXIT ==="
exit $EXIT
```

---

## Investigating Common Issues

### High CPU
```bash
top -d1          # identify PID
ps aux | grep PID
strace -p PID    # syscall trace
# Kubernetes: kubectl top pod -n minipay
```

### Low Disk Space
```bash
df -h            # find full filesystem
du -sh /var/log/* | sort -rh | head   # find large files
journalctl --vacuum-size=500M        # trim journals
```

### Unreachable API
```bash
curl -v http://localhost:5000/health
ss -tlnp | grep 5000      # is port open?
kubectl get endpoints -n minipay    # endpoints populated?
kubectl describe svc minipay-api -n minipay
```

### Repeatedly Terminating Process
```bash
journalctl -u minipay-api -n 100    # check crash logs
kubectl describe pod <pod> -n minipay   # OOMKilled? Exit code?
dmesg | grep -i "killed process"    # OOM killer?
# Check resource limits: if OOMKilled, increase memory limits
```
