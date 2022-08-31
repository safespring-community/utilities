#!/bin/bash

set -eo pipefail

# consistently
# https://stackoverflow.com/a/179231
pushd . > /dev/null
SCRIPT_PATH="${BASH_SOURCE[0]}"
if ([ -h "${SCRIPT_PATH}" ]); then
  while([ -h "${SCRIPT_PATH}" ]); do cd `dirname "${SCRIPT_PATH}"`;
  SCRIPT_PATH=`readlink "${SCRIPT_PATH}"`; done
fi

SCRIPT_DIR=$(dirname $SCRIPT_PATH)
BASE_DIR="${SCRIPT_DIR}/.."

function make_settings {
cat <<EOF
---
# uncomment and change default settings as needed
# terraform_version: "1.0.11"

okd_cluster_name: $1
okd_base_domain: $2

# If you don't set a specific okd_version, the latest from the stable stream will be used.
# If it does not work well, try to step back using specific releases from:
# https://github.com/openshift/okd/releases/
#
# okd_release:

# You can skip specifyng okd_fcos_image, it  will be filled in later by running image-installer.yml playbook
# Don't uncomment it though.

okd_fcos_image: 

# okd_loadbalancer_flavor: "lm.small"
# okd_master_flavor: "lm.large.1d"

# Anti affinity for master nodes. Possible values "anti-affinity" (for production) or soft-anti-affinity (default)
# master_affinity: soft-anti-affinity

# okd_masters: 3
# okd_workers: 2

# Network to put master and worker nodes. LB must be on public. This is hardcoded.
# network: default

api_cidrs:
  - 0.0.0.0/0
ssh_cidrs:
  - 0.0.0.0/0

# The size of ignition for boot node is too big to send directly to the Nova API
# so it needs to be uploaded to bucket and pulle from ther instead.
# You must export AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
# and the bucket name must exist
s3_bucket: "$3"
s3_filename: "{{okd_cluster_name}}-{{okd_base_domain}}.ign"

# Change endpoint url if you s3 bucket resides elsewhere
# Make sure that aws s3 presign works on the bucket objekt.
s3_endpoint_url: "https://minio-1.safedc.net:9091"

# The public key to inject in all cluster nodes
# make sure that the private key for it is added to your ssh-agent, otherwise the ansible setup of the loadbalncer node
# will fail, thus the cluster bootstrap will also fail.

ssh_key_path: "~/.ssh/id_rsa.pub"

# This multiline variable contains the terraform code to define worker sets
# It should be a terraform map variable defining all the worker sets.
# When playbook 04-cluster-finalize.yml is run, the worker sets can be changed
# by editing cluster.tf (the rendered terraform config) or edit the variable here and
# re-run 04-cluster-finalize.yml
# In order to finalize the cluster setup the "first" set is necessary
# Worker sets can be added/removed any time to adapt the changing needs.
# Just make sure it is in line with applications running (evacuate, cordon and delete nodes before scaling down.)
# If flavor is with local disk (flavor name starts with "l") then disk_size is forced to 0
# If flavor is without local disk (flavor name does not start with "l") then disk_size forced to minimum 50GB. If the
# value for disk_size is higher then the specified value will be used.
# This variable is consumed by the okd module on https://github.com/safespring-community/terraform-modules/blob/main/v2-okd-cluster-gandi-dns/variables.tf#L81
workersets: |
  workersets = {
    "first" = {
      prefix    = "initial-worker"
      flavor    = "l2.c4r8.100"
      count     = 2
      disk_size = 0  # Will be forced to 0 anyways because of local disk flavor
    }
    #"second" = {
    #  prefix = "large-worker"
    #  flavor = "b2.c4r16"
    #  count  = 2
    #  disk_size  = 50  # Set higher than 50 to increase size. If lower than 50 it is forced to 50 anyway.
    #}
  }
EOF
}

if [[ -z $3 ]]
then
  echo "Usage: $0 cluster-name gandi-domain-name base-directory"
  exit 1
fi

CLUSTER_NAME=$1
DOMAIN=$2
DIR=$3

mkdir -p ${DIR}

echo "Copying playbooks, settings and templates to your destination: ${DIR}/${CLUSTER_NAME}.${DOMAIN}"
cp -r ${BASE_DIR}/golden-cluster  ${DIR}/${CLUSTER_NAME}.${DOMAIN}
cp -r ${BASE_DIR}/../ati ${DIR}/${CLUSTER_NAME}.${DOMAIN}
make_settings ${CLUSTER_NAME} ${DOMAIN} ${S3_BUCKET} > ${DIR}/${CLUSTER_NAME}.${DOMAIN}/settings.yml

echo "Now cd to ${DIR}/${CLUSTER_NAME}.${DOMAIN}, change settings.yml to your needs run the playbooks in order"
echo "Each playbook must complete successfully before the next is run"
echo "The bootstrap and finalize playbooks take a long ting to finish"
