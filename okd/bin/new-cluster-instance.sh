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
# okd_version:

# You can skip specifyng okd_fcos_image, it  will be filled in later by running image-installer.yml playbook
# Don't uncomment it though.

okd_fcos_image: 

# There is different cluster types using different module variations. Default is to have all nodes except
# lb on local disk. Possible values: worker-central-disk
# okd_cluster_type: "worker-central-disk"

# okd_loadbalancer_flavor: "lm.small"
# okd_master_flavor: "lm.large.1d"
# okd_worker_flavor: "lm.medium.1d"

# Type of cluster
#  * local-disk for all nodes on local disk
#  * worker-central-disk for workers on central disk (default disk size is 50G baut can be overriden with okd_worker_disk_size)

# okd_cluster_type: "local-disk"
# Only relevant when workers are on central disk
# okd_worker_disk_size: 50

# okd_masters: 3
# okd_workers: 2

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

ssh_key_path: "~/.ssh/id_rsa.pub"

# This multiline variable contains the terraform code to define worker sets
# It should be a terraform map variable defining all the worker sets.
# When playbook 04-cluster-finalize.yml is run, the worker sets can be changed
# by editing cluster.tf (the rendered terraform config) or edit the variable here and
# re-run 04-cluster-finalize.yml
# In order to finalize the cluster setup the "first" set is necessary
# Worker sets can be changed in any direction at any time to adapt the changing needs.
# Just make sure it is in line with applications running (evacuate, cordon and delet nodes before scaling down.)
# Please adapt flavors according to the choice of worekr type (local disk or central disk).
# I.e. change to flavor not starting with "l" if choosing  okd_cluster_type: "worker-central-disk"
workersets: |
  workersets = {
    "first" = {
      prefix = "initial-worker"
      flavor = "lm.medium.1d"
      count  = 2
    }
    #"second" = {
    #  prefix = "large-worker"
    #  flavor = "lm.large.1d"
    #  count  = 2
    #}
  }
EOF
}

if [[ -z $3 ]]
then
  echo "Usage: $0 cluster-name gandi-domain-name S3-bucket base-directory"
  exit 1
fi

CLUSTER_NAME=$1
DOMAIN=$2
S3_BUCKET=$3
DIR=$4

mkdir -p ${DIR}

echo "Copying playbooks, settings and templates to your destination: ${DIR}/${CLUSTER_NAME}.${DOMAIN}"
cp -r ${BASE_DIR}/golden-cluster  ${DIR}/${CLUSTER_NAME}.${DOMAIN}
make_settings ${CLUSTER_NAME} ${DOMAIN} ${S3_BUCKET} > ${DIR}/${CLUSTER_NAME}.${DOMAIN}/settings.yml

echo "Now cd to ${DIR}/${CLUSTER_NAME}.${DOMAIN}, change settings.yml to your needs run the playbooks in order"
echo "Each playbook must complete successfully before the next is run"
echo "The bootstrap and finalize playbooks take a long ting to finish"
