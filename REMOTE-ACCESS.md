# Remote Access

dirplot can scan directory trees on remote sources without copying files locally. Remote backends are optional dependencies — install only what you need.

> **Warning:** Remote trees can contain hundreds of thousands of files. Every subdirectory requires a separate network round-trip, so a deep scan can take a long time and make a very large number of API calls. Use `--depth N` to limit how far down the tree dirplot recurses until you have a feel for the size of the target.

---

## SSH

Scan hosts reachable over SSH using [paramiko](https://www.paramiko.org/).

```bash
pip install "dirplot[ssh]"
```

### Usage

```bash
# ssh://user@host/path format
dirplot map ssh://alice@prod.example.com/var/www

# SCP-style user@host:/path format
dirplot map alice@prod.example.com:/var/www

# Exclude paths, cap depth, save to file
dirplot map ssh://alice@prod.example.com/var --exclude /var/cache --depth 4 --output remote.png --no-show
```

### Authentication

Credentials are resolved in this order:

1. `--ssh-key PATH` — explicit private key file
2. `SSH_KEY` environment variable — path to key file
3. `IdentityFile` from `~/.ssh/config` for the target host
4. ssh-agent (picked up automatically)
5. `--ssh-password` / `SSH_PASSWORD` environment variable
6. Interactive password prompt as a last resort

### SSH config

`~/.ssh/config` is read automatically. Host aliases, custom ports, and `IdentityFile` directives all work as expected:

```
Host prod
    HostName prod.example.com
    User alice
    IdentityFile ~/.ssh/prod_key
    Port 2222
```

```bash
dirplot map ssh://prod/var/www   # resolves using the config block above
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--ssh-key` | `~/.ssh/id_rsa` | Path to SSH private key |
| `--ssh-password` | `SSH_PASSWORD` env var | SSH password |
| `--depth` | unlimited | Maximum recursion depth |

### Python API

```python
from dirplot.ssh import connect, build_tree_ssh
from dirplot.render import create_treemap

client = connect("prod.example.com", "alice", ssh_key="~/.ssh/prod_key")
sftp = client.open_sftp()
try:
    root = build_tree_ssh(sftp, "/var/www", depth=5)
finally:
    sftp.close()
    client.close()

buf = create_treemap(root, width_px=1920, height_px=1080)
```

---

## AWS S3

Scan S3 buckets using [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html). File sizes come from S3 object metadata — no data is downloaded.

```bash
pip install "dirplot[s3]"
```

### Usage

```bash
# Scan a bucket prefix
dirplot map s3://my-bucket/path/to/prefix

# Scan an entire bucket
dirplot map s3://my-bucket

# Public bucket (no AWS credentials needed)
dirplot map s3://noaa-ghcn-pds --no-sign

# Use a named AWS profile, cap depth, save to file
dirplot map s3://my-bucket/data --aws-profile prod --depth 3 --output s3.png --no-show
```

### Authentication

boto3's standard credential chain is used automatically — no extra configuration needed if your environment is already set up for AWS:

1. `--aws-profile` / `AWS_PROFILE` env var — named profile from `~/.aws/config`
2. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables
3. `~/.aws/credentials` file
4. IAM instance role (on EC2 / ECS / Lambda)
5. `--no-sign` — skip signing entirely for anonymous access to public buckets

### Options

| Flag | Default | Description |
|---|---|---|
| `--aws-profile` | `AWS_PROFILE` env var | Named AWS profile |
| `--no-sign` | off | Anonymous access for public buckets |
| `--depth` | unlimited | Maximum recursion depth |
| `--exclude` | — | Full `s3://bucket/key` URI to skip (repeatable) |

### Python API

```python
from dirplot.s3 import make_s3_client, build_tree_s3
from dirplot.render import create_treemap

# Authenticated access
s3 = make_s3_client(profile="prod")

# Anonymous access to a public bucket
s3 = make_s3_client(no_sign=True)

root = build_tree_s3(s3, "my-bucket", "path/to/prefix/", depth=5)
buf = create_treemap(root, width_px=1920, height_px=1080)
```

### Public buckets to explore

These buckets are publicly accessible with `--no-sign`:

| Bucket | Contents |
|---|---|
| `s3://noaa-ghcn-pds` | NOAA Global Historical Climatology Network |
| `s3://noaa-goes16` | NOAA GOES-16 weather satellite imagery |
| `s3://sentinel-s2-l1c` | Copernicus Sentinel-2 satellite data (eu-central-1) |
| `s3://1000genomes` | 1000 Genomes Project |
