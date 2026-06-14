# Example 1 — Apache web tier behind a NodeBalancer in a VPC

> **Prompt**
>
> Create 2 linode shared cpu nano instances behind a node balancer within a
> VPC - create new VPC and subnet. Install apache web server on these linode
> instances and use ssh certificates available within the account. Choose
> region washington dc 2.

Infrastructure-as-Code (Terraform, `linode/linode` provider) that provisions a
small, load-balanced Apache web tier on Akamai Cloud (Linode).

> This example is **code only** — nothing here has been applied. Review the
> plan before running it against a real account.

## What it builds

| Requirement | Resource |
|---|---|
| New VPC + subnet | `linode_vpc.this`, `linode_vpc_subnet.web` |
| 2 × shared-CPU nano instances | `linode_instance.web` (`count = 2`, type `g6-nanode-1`) |
| NodeBalancer in front | `linode_nodebalancer.this` + `_config.http` (HTTP :80) + `_node.web` |
| Instances inside the VPC | each instance gets a `vpc` interface with a static VPC IP |
| Apache web server | installed on first boot via cloud-init (`cloud-init.yaml`) |
| SSH keys from the account | `authorized_users` installs the account's saved SSH keys |
| Region Washington, DC | `region = "us-iad"` |

```
VPC 10.0.0.0/16
 └─ subnet 10.0.4.0/24
     ├─ web-1  (vpc 10.0.4.10, + public iface for egress)
     └─ web-2  (vpc 10.0.4.11, + public iface for egress)
NodeBalancer :80 (round-robin, HTTP health check) ──> web-1:80, web-2:80
```

## Design notes

- **"SSH certificates available within the account"** → `authorized_users`. This
  installs the SSH keys saved under the named Linode account user(s)
  (Profile → SSH Keys) instead of embedding raw key material in the config. A
  random `root_pass` is still generated because the API requires one; log in
  with your key.
- **Public + VPC interfaces.** Each instance has a `public` interface (eth0) so
  cloud-init has outbound internet to install Apache, plus a `vpc` interface
  (eth1) with a deterministic address used as the NodeBalancer backend.
- **NodeBalancer → VPC backends** requires NodeBalancer-in-VPC support for your
  account/provider version. If unavailable, switch the instances to private
  networking (`private_ip = true`) and point the nodes at the `192.168.x` IPs.
- **Region id.** `us-iad` is Washington, DC. Confirm the exact id you want with
  `linode-cli regions list` and override `var.region` if needed.

## Files

| File | Purpose |
|---|---|
| `versions.tf` | Terraform + provider version constraints, provider config |
| `variables.tf` | Inputs (token, region, type, count, SSH usernames, CIDRs) |
| `main.tf` | VPC, subnet, instances, NodeBalancer, config, nodes |
| `cloud-init.yaml` | Apache install + landing page (templated per instance) |
| `outputs.tf` | NodeBalancer IP/hostname, instance IPs, VPC id |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in |

## Usage (when you choose to run it)

```bash
export LINODE_TOKEN=...                 # or set linode_token in tfvars
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set authorized_users to your Linode username

terraform init
terraform plan
terraform apply
```

Then browse to `http://<nodebalancer_ipv4>/` and refresh — round-robin should
alternate between `web-1` and `web-2`.

```bash
terraform destroy   # tear it all down
```

## Prerequisites

- Terraform ≥ 1.5
- A Linode API token with read/write scope
- At least one SSH key saved in your Linode account, and the username that owns
  it set in `authorized_users`
