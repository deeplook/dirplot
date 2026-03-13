uv run dirplot map --size 800x400 --no-show --output docs/fastapi.png github://FastAPI/FastAPI
uv run dirplot map --size 800x400 --no-show --output docs/flask.png github://pallets/flask --legend
uv run dirplot map --size 800x400 --no-show --output docs/python.png github://python/cpython
uv run dirplot map --size 800x400 --no-show --output docs/pypy.png github://pypy/pypy

uv run dirplot map --size 800x400 --no-show --no-sign --depth 2 --output docs/s3.png s3://noaa-ghcn-pds

docker run -d --name pg-demo -e POSTGRES_PASSWORD=x postgres:17-alpine
uv run dirplot map --size 800x400 --no-show --log --output docs/docker.png docker://pg-demo:/usr
docker rm -f pg-demo

kubectl run pg-demo --image=postgres:17-alpine --restart=Never \
  --env POSTGRES_PASSWORD=x
kubectl wait --for=condition=Ready pod/pg-demo --timeout=90s
uv run dirplot map --size 800x400 --no-show --output docs/k8s.png pod://pg-demo/var/
kubectl delete pod pg-demo --grace-period=0
