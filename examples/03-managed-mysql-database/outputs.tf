output "database_id" {
  description = "ID of the managed database cluster."
  value       = linode_database_mysql_v2.this.id
}

output "status" {
  description = "Provisioning status of the database."
  value       = linode_database_mysql_v2.this.status
}

output "host_primary" {
  description = "Primary host to connect to."
  value       = linode_database_mysql_v2.this.host_primary
}

output "port" {
  description = "Connection port."
  value       = linode_database_mysql_v2.this.port
}

output "root_username" {
  description = "Generated root username."
  value       = linode_database_mysql_v2.this.root_username
}

output "root_password" {
  description = "Generated root password."
  value       = linode_database_mysql_v2.this.root_password
  sensitive   = true
}

output "ca_cert" {
  description = "CA certificate for verifying TLS connections."
  value       = linode_database_mysql_v2.this.ca_cert
  sensitive   = true
}
