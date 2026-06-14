# Example 2 — Private Object Storage bucket

> **Prompt**
>
> create object store named raw-images in us-east-1 region. make the object
> store non public.

Infrastructure-as-Code (Terraform, `linode/linode` provider) that creates a
single, private Object Storage bucket on Akamai Cloud (Linode).

> This example is **code only** — nothing here has been applied.

## What it builds

| Requirement | Resource / setting |
|---|---|
| Object store named `raw-images` | `linode_object_storage_bucket.raw_images` (`label = "raw-images"`) |
| Region `us-east-1` | `region = "us-east"` (Newark — see note below) |
| Non-public | `acl = "private"` |

## Design notes

- **`us-east-1` → `region = "us-east"`.** `us-east-1` is the legacy Object
  Storage *cluster* id for Newark, NJ. The current provider takes a `region`
  argument; `us-east` is the same Newark location. Confirm what your account
  can use with `linode-cli object-storage endpoints`.
- **"Non public" → `acl = "private"`.** A private canned ACL means objects are
  not publicly readable. The ACL (and `cors_enabled`) are applied through the
  Linode API at bucket creation, so this example needs only an API **token** —
  no S3 access keys.
- **Versioning / lifecycle omitted.** Those are managed over the S3 API and
  would require `access_key`/`secret_key` (e.g. from a
  `linode_object_storage_key`) on the resource. Add a key resource if you need
  them.

## Files

| File | Purpose |
|---|---|
| `versions.tf` | Terraform + provider constraints, provider config |
| `variables.tf` | Inputs (token, region, bucket label, acl) |
| `main.tf` | The private bucket |
| `outputs.tf` | Bucket label, region, hostname, effective ACL |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in |

## Usage (when you choose to run it)

```bash
export LINODE_TOKEN=...                 # or set linode_token in tfvars
cp terraform.tfvars.example terraform.tfvars

terraform init
terraform plan
terraform apply
```

Verify it is private (objects shouldn't be anonymously accessible):

```bash
linode-cli object-storage buckets-list
# Anonymous GET of an uploaded object should return 403, not 200.
```

```bash
terraform destroy   # remove the bucket (must be empty first)
```

## Prerequisites

- Terraform ≥ 1.5
- A Linode API token with Object Storage read/write scope
- Object Storage available in the target region (first bucket enables the
  service on the account)
