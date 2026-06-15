# Linode Terraform Provider — Best Practices

Lessons learned from real-world Terraform deployments on Akamai Cloud (Linode).
These complement the official provider docs and highlight common pitfalls.

---

## 1. `linode_instance` — IP address attributes

### `ip_address` is deprecated

The `ip_address` attribute on `linode_instance` is deprecated. Do not use it in
new configurations or outputs.

**Wrong:**
```hcl
value = [for i in linode_instance.web : i.ip_address]
```

**Correct:**
```hcl
value = [for i in linode_instance.web : tolist(i.ipv4)[0]]
```

### `ipv4` is a `set(string)`, not a list

The `ipv4` attribute is a `set(string)`. Sets cannot be indexed by integer
directly in Terraform. Always convert to a list first:

```hcl
tolist(i.ipv4)[0]   # first public IPv4
```

### Always allocate a private IP for NodeBalancer backends

Enable `private_ip = true` on every instance that will serve as a NodeBalancer
backend. This allocates a `192.168.x.x` address which the NodeBalancer requires.

```hcl
resource "linode_instance" "web" {
  ...
  private_ip = true
}
```

---

## 2. `linode_nodebalancer_node` — backend address

### NodeBalancer-in-VPC is not universally available

Pointing NodeBalancer nodes at VPC IPs (`10.x.x.x`) requires NodeBalancer-in-VPC
support, which is not enabled on all accounts. Using a VPC IP when the feature is
unavailable produces an error like:

> `address must start with 192.168`

**Always use the private IP as the safe default:**

```hcl
resource "linode_nodebalancer_node" "web" {
  ...
  address = "${linode_instance.web[count.index].private_ip_address}:80"
}
```

Only switch to VPC IPs after confirming NodeBalancer-in-VPC is enabled for the
account.

---

## 3. `linode_firewall` — always attach a firewall

Every deployment that exposes compute or a NodeBalancer to the public internet
should have an explicit firewall. The default Linode posture allows all inbound
traffic — a firewall with `inbound_policy = "DROP"` is required to enforce
least-privilege access.

### Minimal web-tier firewall (HTTP + HTTPS)

```hcl
resource "linode_firewall" "web" {
  label = "${var.prefix}-web-fw"
  tags  = var.tags

  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "allow-http"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "80"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  inbound {
    label    = "allow-https"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = "443"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  # Attach to both instances and the NodeBalancer
  linodes       = linode_instance.web[*].id
  nodebalancers = [linode_nodebalancer.this.id]
}
```

### Rules

- Set `inbound_policy = "DROP"` — deny everything not explicitly allowed.
- Set `outbound_policy = "ACCEPT"` — instances need outbound internet for
  package installs (cloud-init, apt) and API calls.
- Attach the firewall to **both** `linodes` and `nodebalancers` when both are
  part of the topology.
- Give each `inbound` block a short, descriptive `label` (e.g. `allow-http`).
- Include both `ipv4` and `ipv6` in each rule so dual-stack traffic is covered.

---

## 4. General Terraform hygiene

- **Use `random_password`** for `root_pass` — never hardcode passwords.
- **Use `authorized_users`** to reference SSH keys stored in the Linode account
  rather than embedding public keys in `authorized_keys` strings.
- **Tag all resources** with a shared `tags` variable so resources belonging to
  the same stack are easy to identify and clean up in the Cloud Manager.
- **Pin provider versions** in `versions.tf` to avoid unexpected behaviour when
  the Linode provider ships breaking changes.
