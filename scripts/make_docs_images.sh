uv run dirplot map --canvas 800x400 --no-show --output docs/images/fastapi.png github://FastAPI/FastAPI
uv run dirplot map --canvas 800x400 --no-show --output docs/images/flask.png github://pallets/flask --legend
uv run dirplot map --canvas 800x400 --no-show --output docs/images/python.png github://python/cpython
uv run dirplot map --canvas 800x400 --no-show --output docs/images/pypy.png github://pypy/pypy

uv run dirplot map --canvas 800x400 --no-show --no-sign --depth 2 --output docs/images/s3.png s3://noaa-ghcn-pds

docker run -d --name pg-demo -e POSTGRES_PASSWORD=x postgres:17-alpine
uv run dirplot map --canvas 800x400 --no-show --log-scale 4 --output docs/images/docker.png docker://pg-demo:/usr
docker rm -f pg-demo

kubectl run pg-demo --image=postgres:17-alpine --restart=Never \
  --env POSTGRES_PASSWORD=x
kubectl wait --for=condition=Ready pod/pg-demo --timeout=90s
uv run dirplot map --canvas 800x400 --no-show --output docs/images/k8s.png pod://pg-demo/var/
kubectl delete pod pg-demo --grace-period=0
