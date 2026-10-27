# Linux Evidence — MiniPay Host

This evidence was captured from the final local runtime on **2026-10-27 at
06:15 (+05:00)**. It replaces earlier illustrative output. The API was
running under Gunicorn on port 5000 and PostgreSQL was running in the
`minipay-postgres` Docker container, published on port 55432.

## OS / Kernel

```text
$ uname -a
Linux noman-hassan 7.0.0-38-generic #38-Ubuntu SMP PREEMPT_DYNAMIC Fri Sep  4 09:10:14 UTC 2026 x86_64 GNU/Linux

$ cat /etc/os-release
PRETTY_NAME="Ubuntu 26.04.1 LTS"
VERSION_ID="26.04"
VERSION_CODENAME=resolute
```

## Memory

```text
$ free -h
               total        used        free      shared  buff/cache   available
Mem:             14Gi       4.7Gi       7.7Gi       661Mi       3.6Gi        10Gi
Swap:           4.0Gi          0B       4.0Gi
```

## Disk

```text
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           3.0G  3.0M  3.0G   1% /run
/dev/nvme0n1p2  233G   59G  162G  27% /
tmpfs           7.5G   17M  7.5G   1% /dev/shm
/dev/nvme0n1p1  1.1G  6.4M  1.1G   1% /boot/efi
tmpfs           7.5G   37M  7.5G   1% /tmp
```

## Listening Ports

```text
$ ss -tlnp
LISTEN 0 2048 0.0.0.0:5000  0.0.0.0:* users:(("gunicorn",pid=9205,fd=5),("gunicorn",pid=9204,fd=5),("gunicorn",pid=9203,fd=5))
LISTEN 0 4096 0.0.0.0:55432 0.0.0.0:*
LISTEN 0 4096 [::]:55432    [::]:*
```

The other listeners shown by `ss` were host/desktop services unrelated to
MiniPay. PostgreSQL is exposed through Docker port 55432 rather than a host
port 5432 listener.

## MiniPay Processes

```text
$ ps -ef | grep '[g]unicorn'
noman 9203 5861 0 06:12 ? 00:00:00 /tmp/minipay-runtime/bin/python3 /tmp/minipay-runtime/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
noman 9204 9203 0 06:12 ? 00:00:00 /tmp/minipay-runtime/bin/python3 /tmp/minipay-runtime/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
noman 9205 9203 0 06:12 ? 00:00:00 /tmp/minipay-runtime/bin/python3 /tmp/minipay-runtime/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
```

The full host process list was sorted by memory during capture. The largest
entries were VS Code and Chrome desktop processes; MiniPay's Gunicorn
processes were present but were not the host's largest consumers.

## Disk Usage by Directory

```text
$ du -xhd1 /home/noman/Downloads/paysys-solution | sort -h
28K  /home/noman/Downloads/paysys-solution/.pytest_cache
512K /home/noman/Downloads/paysys-solution/.git
1.6M /home/noman/Downloads/paysys-solution/solution
2.2M /home/noman/Downloads/paysys-solution
```

## API Health

```text
$ curl -sS -i http://localhost:5000/health
HTTP/1.1 200 OK
Server: gunicorn
Content-Type: application/json

{"db":"ok","status":"ok"}
```

The repository health-check script also passed:

```text
$ bash scripts/health_check.sh
MiniPay API is healthy at http://localhost:5000
```

## Application Logs

Gunicorn stdout during this capture confirmed the API process and workers:

```text
[9203] [INFO] Starting gunicorn 21.2.0
[9203] [INFO] Listening at: http://0.0.0.0:5000 (9203)
[9203] [INFO] Using worker: sync
[9204] [INFO] Booting worker with pid: 9204
[9205] [INFO] Booting worker with pid: 9205
```

The current application does not emit per-request access logs by default, so
no fabricated request log lines are included here. Kubernetes logs should be
captured separately when a cluster deployment is available.
