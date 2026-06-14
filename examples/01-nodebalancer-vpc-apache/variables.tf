variable "linode_token" {
  description = "Linode API token. Leave empty to use the LINODE_TOKEN env var."
  type        = string
  default     = ""
  sensitive   = true
}

variable "region" {
  description = "Linode region. us-iad is Washington, DC. Verify with `linode-cli regions list`."
  type        = string
  default     = "us-iad"
}

variable "instance_type" {
  description = "Linode plan. g6-nanode-1 is the Shared CPU Nanode 1GB ('nano')."
  type        = string
  default     = "g6-nanode-1"
}

variable "image" {
  description = "Image to boot. Must support cloud-init (Metadata) for Apache install."
  type        = string
  default     = "linode/ubuntu22.04"
}

variable "instance_count" {
  description = "Number of web instances behind the NodeBalancer."
  type        = number
  default     = 2
}

variable "prefix" {
  description = "Name prefix applied to all created resources."
  type        = string
  default     = "example1"
}

variable "authorized_users" {
  description = <<-EOT
    Linode usernames whose account SSH keys are installed on the instances'
    root account. This uses the SSH keys already saved in your Linode account
    (Profile > SSH Keys) rather than embedding raw key material here.
    Example: ["myusername"].
  EOT
  type        = list(string)
  default     = []
}

variable "vpc_cidr" {
  description = "CIDR for the new VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR for the new VPC subnet (must be within vpc_cidr)."
  type        = string
  default     = "10.0.4.0/24"
}

variable "tags" {
  description = "Tags applied to taggable resources."
  type        = list(string)
  default     = ["example1", "apache", "managed-by-terraform"]
}
