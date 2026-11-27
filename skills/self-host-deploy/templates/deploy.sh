#!/bin/sh
# Server-side deploy, called over SSH with a forced command. Commands: `status` | `deploy <sha>`.
# Expects /srv/app/{compose.yml,.env} with TAG=<sha> in .env and a service named "app" with a HEALTHCHECK.
set -eu
cd /srv/app
set -- ${SSH_ORIGINAL_COMMAND:-$*}
CMD="${1:-}"; NEW="${2:-}"
current() { sed -n 's/^TAG=//p' .env; }
case "$CMD" in
  status) current; exit 0 ;;
  deploy) ;;
  *) echo "usage: status | deploy <sha>" >&2; exit 2 ;;
esac
case "$NEW" in ''|*[!0-9a-f]*) echo "bad tag: $NEW" >&2; exit 2 ;; esac
exec 9>/srv/app/.deploy.lock
flock -n 9 || { echo "another deploy is running" >&2; exit 3; }
OLD="$(current)"
echo "deploy: $OLD -> $NEW"
TAG="$NEW" docker compose pull app
sed -i "s/^TAG=.*/TAG=$NEW/" .env
docker compose up -d app
i=0
while [ $i -lt 60 ]; do
  [ "$(docker inspect -f '{{.State.Health.Status}}' app 2>/dev/null || echo none)" = healthy ] && {
    echo "live: $(docker inspect -f '{{.Config.Image}}' app)"; exit 0; }
  i=$((i + 1)); sleep 5
done
echo "not healthy in 5 min — rolling back to $OLD" >&2
docker logs --tail 80 app >&2 || true
sed -i "s/^TAG=.*/TAG=$OLD/" .env
docker compose up -d app
exit 1
