"""An OpenStack Python Pulumi program"""

import pulumi
from pulumi_openstack import compute
from pulumi_openstack import networking

sg = networking.SecGroup('pulumi-sg',
        name = 'pulumi-sg')

ssh_rule = networking.SecGroupRule("pulumi-ssh-ingress",
    direction="ingress",
    ethertype="IPv4",
    protocol="tcp",
    port_range_min=22,
    port_range_max=22,
    remote_ip_prefix="0.0.0.0/0",
    security_group_id=sg.id)

instance = compute.Instance('pulumi-demo',
        name = 'pulumi-demo',
        flavor_name='l2.c2r4.100',
        networks=[{"name": "public"}],
        security_groups=[sg.name],           # <- New parameter for security group membership
        image_name='ubuntu-22.04')

