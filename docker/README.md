# Serving container

`docker/Dockerfile.serve` packages the fail-stop websocket policy server (`python -m policybank serve`,
see `policybank/serving/`) into a small image:

- base `python:3.12.7-slim-bookworm`, pinned by tag
- runs as uid/gid 65532 (non-root), with `tini` as PID 1 so `docker stop` reaches the server and the
  server's exit code becomes the container's exit code
- contains only `pyproject.toml`, `README.md`, `LICENSE` and `policybank/` installed with
  `pip install .[serve]`; `data/`, `site/`, `paper/` and `results/` are not copied
- listens on port 8000; a `HEALTHCHECK` polls `GET /healthz` (200 `OK` while serving, 503 after a
  terminal failure, after which the process exits)
- entrypoint `tini -- python -m policybank serve --host 0.0.0.0 --port 8000`; default arguments
  `--replay 32 --chunk 4`

Without `--upstream` the container serves the deterministic `ScriptedPolicy`. That is only useful for
smoke tests and for checking evaluator wiring.

## Build

From the repository root:

```bash
docker build -f docker/Dockerfile.serve -t policybank-serve .
```

## Run

```bash
docker run -d --name policybank-serve --restart no -p 8000:8000 policybank-serve
curl -fsS http://127.0.0.1:8000/healthz        # OK
```

Arguments after the image name replace the default `--replay 32 --chunk 4`, so pass all of them:

```bash
docker run --rm -p 8000:8000 policybank-serve --policy scripted --replay 20 --chunk 4 --query-timeout 550
```

`--chunk` must divide `--replay`, or the server refuses to start.

### Exit codes

| Situation | Container exit |
| --- | --- |
| `docker stop` (SIGTERM forwarded by tini), no failure | 0 |
| Terminal policy failure: contract violation, task change, nonfinite action, model or upstream error, query timeout | 1 (the evaluator connection is closed with 1011 first) |
| Startup error (bad arguments, upstream unreachable) | nonzero |

The image never restarts the server. Run it with `--restart no` (Docker's default), use
`restartPolicy: Never` on Kubernetes, and don't put it under a supervisor that restarts it. A failed
rollout should stay failed. A restarted container would accept a new task binding and hide the fault.

## Fronting a real OpenPI checkpoint

Real checkpoints run in their own runtime image (CUDA, model weights, the policy's native
preprocessing) behind an OpenPI-compatible websocket server (`serve_policy.py` or the Comet and
2025-winner forks). This container sits in front of that server with `--upstream`. It enforces the
challenge contract, splits batches per environment for the unbatched upstream, and serves the
upstream's native plan in fixed transport chunks.

Example: the checkpoint server listens on port 8001 on the Docker host.

```bash
docker run -d --name pb-task-17 --restart no -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  policybank-serve \
  --upstream ws://host.docker.internal:8001 --policy comet --replay 32 --chunk 4
```

- `--add-host=host.docker.internal:host-gateway` is needed on Linux. Docker Desktop provides
  `host.docker.internal` itself. On a user-defined network, use the upstream container's name instead
  (`--upstream ws://checkpoint:8000`).
- `--replay` must equal the checkpoint's native receding horizon: 32 for the Comet family, 20 for the
  2025-winner family. The upstream must return at least that many actions per plan.
- Start the upstream first. The connection is opened once at startup, and an unreachable upstream
  makes the container exit nonzero before `/healthz` comes up.
- Run one task per container. The first query binds the task id, and a later query with a different
  task id is a terminal failure. Start a fresh container (and, if needed, upstream) for each task.
- Resets are not forwarded upstream. OpenPI servers keep no per-episode state; the chunk queue in
  this container is cleared on every reset and every new session.

## Smoke test

`docker/smoke_test.py` drives a fresh server that is serving the scripted policy. It needs `numpy`,
`msgpack`, `websockets` and the `policybank` package; from a plain checkout it falls back to importing
the package from the repository root. The checks run in this order:

1. `GET /healthz` returns 200 within `--startup-timeout` (default 60 s).
2. The metadata map sent on connect has protocol `b1k-2026`, `action_dim` 23, `max_batch` 10, chunk 4,
   replay 32, `failure_mode` `terminal` and policy `scripted`.
3. A batch-10 query returns `action` (10, 23), `action_chunk` (10, 4, 23) and `server_timing`, with
   `action == action_chunk[:, 0]` and values equal to the scripted stream.
4. Eight more batch-10 queries step through the 32-action native plan. The ninth query in the session
   starts plan 1, so the plan boundary is crossed with no gap or repeat.
5. `{"reset": True}` gets no reply within 0.5 s. The next query (unbatched, shape change allowed after
   a reset) starts a fresh plan.
6. A second concurrent connection is closed with 1013, and the first session keeps answering.
7. A clean close ends with code 1000, and `/healthz` stays 200, because a disconnect is not a failure.
8. A reconnect gets a new session that starts from a fresh plan.
9. A query with a different task id (an invalid frame) is closed with 1011.
10. `/healthz` stops returning 200 (503, or connection refused once the process has exited).

The script exits 0 when all checks pass and 1 otherwise, naming the failing check. The last two
checks stop the server, so never point the smoke test at a container that is serving an evaluation.

From source:

```bash
pip install ".[serve]"
python -m policybank serve --host 127.0.0.1 --port 8000 &
python docker/smoke_test.py --uri ws://127.0.0.1:8000 --http http://127.0.0.1:8000
wait $!; echo "server exit code $?"            # nonzero: the server stopped itself
```

Against the image:

```bash
docker run -d --name pb-smoke -p 8000:8000 policybank-serve
python docker/smoke_test.py --uri ws://127.0.0.1:8000 --http http://127.0.0.1:8000
docker wait pb-smoke                            # prints the nonzero exit code
docker logs pb-smoke && docker rm pb-smoke
```

`.github/workflows/serve-smoke.yml` runs both on every push to `main` and every pull request. The image
job also checks that PID 1 is tini running as uid 65532, that Docker reports the container healthy,
and that the container stops by itself with a nonzero exit code, zero restarts and the contract
failure in its log.

## Limitations

- No GPU, CUDA, model weights or OpenPI code are in this image. It holds only the fail-stop front end
  and the scripted test policy. Every real checkpoint needs its own runtime image serving the OpenPI
  protocol.
- `/healthz` reports this server's state only. Upstream health is not probed. An upstream that dies or
  restarts surfaces on the next re-plan, as a terminal failure.
- The smoke test covers the scripted policy only. It does not exercise `--upstream`; the repository's
  unit tests cover that path with a fake upstream.
- Plain `ws://` only, with no TLS or authentication. Keep the port on a private network, or put it
  behind a TLS-terminating proxy.
- The base image is pinned by tag, not digest. For bit-for-bit reproducible builds, pin
  `python:3.12.7-slim-bookworm@sha256:...` and the Python dependencies as well.
