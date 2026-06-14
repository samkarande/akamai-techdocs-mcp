output "nodebalancer_ipv4" {
  description = "Public IPv4 of the NodeBalancer — browse to http://<this-ip>/."
  value       = linode_nodebalancer.this.ipv4
}

output "nodebalancer_hostname" {
  description = "DNS hostname of the NodeBalancer."
  value       = linode_nodebalancer.this.hostname
}

output "instance_public_ips" {
  description = "Public IPv4 of each web instance (for SSH administration)."
  value       = [for i in linode_instance.web : i.ip_address]
}

output "instance_vpc_ips" {
  description = "VPC IPv4 of each web instance (NodeBalancer backends)."
  value       = local.instance_vpc_ips
}

output "vpc_id" {
  description = "ID of the created VPC."
  value       = linode_vpc.this.id
}
