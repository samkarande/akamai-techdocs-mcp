# Example 3 — Managed MySQL database

> **Prompt**
>
> create a managed mysql database with 4GB storage, choose appropriate linode
> size in us-east-1 region

Infrastructure-as-Code (Terraform, `linode/linode` provider) that provisions a
Linode Managed MySQL database (DBaaS).

> This example is **code only** — nothing here has been applied.

## What it builds

| Requirement | Resource / setting |
|---|---|
| Managed MySQL database | `linode_database_mysql_v2.this` (`engine_id = "mysql/8"`) |
| ~4GB / appropriate Linode size | `type = "g6-standard-2"` (Shared 4GB plan) |
| Region `us-east-1` | `region = "us-east"` (Newark — see note) |

## Design notes

- **Storage is bundled with the plan.** Linode managed databases don't take an
  independent storage size — disk, RAM, and vCPUs come together in the node
  `type`. So "4GB" is expressed by choosing the 4GB plan, `g6-standard-2`. For
  more capacity, pick a larger plan (`linode-cli databases types`).
- **`us-east-1` → `region = "us-east"`** (Newark, NJ) — same location, current
  region id.
- **`v2` resource.** `linode_database_mysql_v2` is the current Aiven-backed
  managed database. The legacy `linode_database_mysql` is being retired; prefer
  v2 for new clusters.
- **Access control.** `allow_list` is empty by default, which blocks all
  inbound connections. Set it to your client IP(s) (e.g. `["203.0.113.10/32"]`)
  in `terraform.tfvars`.
- **High availability.** `cluster_size = 1` is a single node. Set it to `3` for
  an HA cluster.
- **Credentials are sensitive.** `root_password` and `ca_cert` are marked
  `sensitive` and won't print in plan/apply output — read them explicitly (see
  below).

## Files

| File | Purpose |
|---|---|
| `versions.tf` | Terraform + provider constraints, provider config |
| `variables.tf` | Inputs (token, region, engine, plan, label, cluster size, allow list) |
| `main.tf` | The managed MySQL cluster |
| `outputs.tf` | Host, port, status, credentials (sensitive), CA cert |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in |

## Usage (when you choose to run it)

```bash
export LINODE_TOKEN=...                 # or set linode_token in tfvars
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set allow_list to your client IP(s)

terraform init
terraform plan
terraform apply        # provisioning a managed DB can take several minutes
```

Read the connection details (password is sensitive):

```bash
terraform output host_primary
terraform output port
terraform output -raw root_password
```

```bash
terraform destroy
```

## Prerequisites

- Terraform ≥ 1.5
- A Linode API token with database read/write scope
