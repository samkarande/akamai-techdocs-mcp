variable "linode_token" {
  description = "Linode API token. Leave empty to use the LINODE_TOKEN env var."
  type        = string
  default     = ""
  sensitive   = true
}

variable "region" {
  description = <<-EOT
    Region for the managed database. "us-east" is Newark, NJ — the location
    historically addressed as "us-east-1". Confirm availability with
    `linode-cli databases engines` / `linode-cli regions list`.
  EOT
  type        = string
  default     = "us-east"
}

variable "engine" {
  description = "Database engine id, in the form 'mysql/<major>'."
  type        = string
  default     = "mysql/8"
}

variable "database_type" {
  description = <<-EOT
    Node plan for the database. Storage is bundled with the plan (it is NOT
    set independently). g6-standard-2 is the Shared 4GB plan — the
    "appropriate Linode size" for ~4GB. Bump to a larger plan for more
    storage/RAM. List options with `linode-cli databases types`.
  EOT
  type        = string
  default     = "g6-standard-2"
}

variable "label" {
  description = "Label for the managed database cluster."
  type        = string
  default     = "example3-mysql"
}

variable "cluster_size" {
  description = "Number of nodes. 1 = single node; 3 = high-availability."
  type        = number
  default     = 1

  validation {
    condition     = contains([1, 3], var.cluster_size)
    error_message = "cluster_size must be 1 or 3."
  }
}

variable "allow_list" {
  description = <<-EOT
    IPs/CIDRs permitted to connect. An empty list blocks all inbound access
    until you add an entry — set this to your client IP(s), e.g.
    ["203.0.113.10/32"].
  EOT
  type        = list(string)
  default     = []
}
