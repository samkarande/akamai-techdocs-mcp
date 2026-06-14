# Examples

Worked examples for common Akamai Cloud (Linode) tasks. The code here is
provided as a reference — review and apply it deliberately against your own
account. Each example includes the originating **prompt** (`prompt.txt`).

| # | Example | Stack | Builds |
|---|---|---|---|
| 1 | [`01-nodebalancer-vpc-apache`](01-nodebalancer-vpc-apache/) | Terraform (`linode/linode`) | 2 shared-CPU nano instances running Apache, behind a NodeBalancer, in a new VPC + subnet (region `us-iad`) |
| 2 | [`02-object-storage-private-bucket`](02-object-storage-private-bucket/) | Terraform (`linode/linode`) | A private (non-public) Object Storage bucket `raw-images` in `us-east` |
| 3 | [`03-managed-mysql-database`](03-managed-mysql-database/) | Terraform (`linode/linode`) | A Managed MySQL 8 database on the Shared 4GB plan in `us-east` |

Each example documents its own prerequisites and usage in its `README.md`.
