###############################################################################
# Example 1 — 2x Shared-CPU Nano instances behind a NodeBalancer, in a new VPC.
#
# Topology:
#   VPC (10.0.0.0/16)
#    └─ subnet (10.0.4.0/24)
#        ├─ web-1  (public iface for egress + vpc iface 10.0.4.10)
#        └─ web-2  (public iface for egress + vpc iface 10.0.4.11)
#   NodeBalancer (HTTP :80, round-robin) ──> web-1:80, web-2:80 (private IPs)
#   Firewall (ports 80/443 inbound) ──> NodeBalancer + web instances
#
# Apache is installed via cloud-init (Linode Metadata user_data).
# Root SSH access uses the SSH keys already saved in your Linode account,
# referenced through `authorized_users`.
###############################################################################

locals {
  # Deterministic VPC IPs so the NodeBalancer nodes can target the backends
  # without depending on DHCP assignment order.
  instance_vpc_ips = [
    for i in range(var.instance_count) : cidrhost(var.subnet_cidr, 10 + i)
  ]
}

# A strong, random root password is required by the API even when SSH keys are
# used. It is not printed; log in with your SSH key.
resource "random_password" "root" {
  length  = 32
  special = true
}

# --- Network -----------------------------------------------------------------

resource "linode_vpc" "this" {
  label       = "${var.prefix}-vpc"
  region      = var.region
  description = "Example 1 VPC for NodeBalancer + Apache web tier."
}

resource "linode_vpc_subnet" "web" {
  vpc_id = linode_vpc.this.id
  label  = "${var.prefix}-web-subnet"
  ipv4   = var.subnet_cidr
}

# --- Compute -----------------------------------------------------------------

resource "linode_instance" "web" {
  count  = var.instance_count
  label  = "${var.prefix}-web-${count.index + 1}"
  region = var.region
  type   = var.instance_type
  image  = var.image
  tags   = var.tags

  root_pass  = random_password.root.result
  private_ip = true

  # Use SSH keys already stored in the Linode account for these usernames.
  authorized_users = var.authorized_users

  # Install Apache on first boot via cloud-init.
  metadata {
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
      hostname = "${var.prefix}-web-${count.index + 1}"
    }))
  }

  # eth0: public interface — gives the instance outbound internet so cloud-init
  # can apt-install Apache, and a public IP for administration.
  interface {
    purpose = "public"
  }

  # eth1: VPC interface with a static address used as the NodeBalancer backend.
  interface {
    purpose   = "vpc"
    subnet_id = linode_vpc_subnet.web.id

    ipv4 {
      vpc = local.instance_vpc_ips[count.index]
    }
  }
}

# --- Load balancing ----------------------------------------------------------

resource "linode_nodebalancer" "this" {
  label  = "${var.prefix}-nb"
  region = var.region
  tags   = var.tags
}

resource "linode_nodebalancer_config" "http" {
  nodebalancer_id = linode_nodebalancer.this.id

  port      = 80
  protocol  = "http"
  algorithm = "roundrobin"

  # Active HTTP health check against the Apache default vhost.
  check          = "http"
  check_path     = "/"
  check_interval = 10
  check_timeout  = 5
  check_attempts = 3
}

resource "linode_nodebalancer_node" "web" {
  count           = var.instance_count
  nodebalancer_id = linode_nodebalancer.this.id
  config_id       = linode_nodebalancer_config.http.id

  label   = "${var.prefix}-web-${count.index + 1}"
  address = "${linode_instance.web[count.index].private_ip_address}:80"
  weight  = 50
  mode    = "accept"
}

# --- Firewall ----------------------------------------------------------------

resource "linode_firewall" "this" {
  label = "${var.prefix}-apache-fw"
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

  linodes       = linode_instance.web[*].id
  nodebalancers = [linode_nodebalancer.this.id]
}
