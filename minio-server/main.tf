terraform {
required_version = ">= 0.14.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
    }
  }
}

module sg {
   source = "github.com/safespring-community/terraform-modules/v2-compute-security-group"
   name = "mino_external_access"
   description = "External access for mino"
   rules = [
     {
       ip_protocol = "tcp"
       to_port = "22"
       from_port = "22"
       cidr = "0.0.0.0/0"
     },
     {
       ip_protocol = "tcp"
       to_port = "80"
       from_port = "80"
       cidr = "0.0.0.0/0"
     },
     {
       ip_protocol = "tcp"
       to_port = "9091"
       from_port = "9091"
       cidr = "0.0.0.0/0"
     },
     {
       ip_protocol = "icmp"
       to_port = "-1"
       from_port = "-1"
       cidr = "0.0.0.0/0"
     }
  ]
}

resource "openstack_compute_keypair_v2" "skp" {
  name       = "mino-kp"
  # Change this to where the pubkey is located
  public_key = "${chomp(file("id_rsa.pub"))}"
}

module  minio_server{
  source = "github.com/safespring-community/terraform-modules/v2-compute-local-disk-and-attached-disk"
  key_pair_name = openstack_compute_keypair_v2.skp.name
  security_groups = [module.sg.name]
  prefix = "minio"
  volume_size = 20
  domain_name = "example.com"
  flavor = "lb.small"
  role = "minio_server"
}

