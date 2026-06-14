# Example 4 — Autoscaling LKE cluster

> **Prompt**
>
> create a LKE cluster with autoscale, desired capacity 2 nodes, 2 pods per
> node in washington dc region.

Infrastructure-as-Code (Terraform, `linode/linode` provider) that provisions an
autoscaling Linode Kubernetes Engine (LKE) cluster, plus a sample workload that
demonstrates the "2 pods per node" requirement at the Kubernetes layer.

> This example is **code only** — nothing here has been applied.

## What it builds

| Requirement | Resource / setting |
|---|---|
| LKE cluster | `linode_lke_cluster.this` |
| Autoscale, desired 2 nodes | one `pool` with `count = 2` and `autoscaler { min = 2, max = 4 }` |
| Washington, DC region | `region = "us-iad"` |
| 2 pods per node | Kubernetes `topologySpreadConstraints` (see note) — `k8s/sample-deployment.yaml` |

## Design notes

- **Autoscaling.** The node pool starts at the desired capacity (`count = 2`)
  and the autoscaler keeps it between `min` (2) and `max` (4) based on load.
  Because the autoscaler owns the live node count, `main.tf` sets
  `lifecycle { ignore_changes = [pool[0].count] }` so Terraform doesn't fight
  it on subsequent applies.
- **"2 pods per node" is a Kubernetes concern, not an LKE setting.** Standard
  LKE does not expose a kubelet `--max-pods` cap (the platform default is 110),
  so you cannot set "2 pods per node" on the node pool itself. The supported,
  Kubernetes-native way to bound pods-per-node for a workload is
  `topologySpreadConstraints` (or pod anti-affinity).
  [`k8s/sample-deployment.yaml`](k8s/sample-deployment.yaml) runs 4 replicas
  across the 2-node pool with `maxSkew: 1` on `kubernetes.io/hostname`, which
  places **2 pods per node**. Scale the workload in multiples of the node count
  to keep the even 2-per-node spread.
- **Region.** `us-iad` is Washington, DC.
- **Kubernetes version.** Defaults to `1.32`; confirm what's offered with
  `linode-cli lke versions-list`.

## Files

| File | Purpose |
|---|---|
| `versions.tf` | Terraform + provider constraints, provider config |
| `variables.tf` | Inputs (token, region, k8s version, node type, capacity, autoscaler bounds) |
| `main.tf` | The LKE cluster + autoscaling node pool |
| `outputs.tf` | Cluster id, status, API endpoints, dashboard URL, kubeconfig (sensitive) |
| `k8s/sample-deployment.yaml` | Sample workload demonstrating 2 pods/node |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` and fill in |

## Usage (when you choose to run it)

```bash
export LINODE_TOKEN=...                 # or set linode_token in tfvars
cp terraform.tfvars.example terraform.tfvars

terraform init
terraform plan
terraform apply        # cluster provisioning takes a few minutes
```

Get the kubeconfig and apply the sample workload:

```bash
terraform output -raw kubeconfig | base64 --decode > kubeconfig.yaml
export KUBECONFIG=$PWD/kubeconfig.yaml

kubectl get nodes
kubectl apply -f k8s/sample-deployment.yaml
kubectl get pods -o wide        # ~2 'web' pods scheduled per node
```

```bash
terraform destroy
```

## Prerequisites

- Terraform ≥ 1.5
- A Linode API token with Kubernetes (LKE) read/write scope
- `kubectl` (only to apply the sample workload)
