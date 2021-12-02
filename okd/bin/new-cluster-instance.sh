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
#uncomment and change default settings as needed

okd_cluster_name: $1
okd_base_domain: $2

# You can leave this blank for now, it  will be filled in later by running image-installer.yml playbook
okd_fcos_image: 


# okd_loadbalancer_flavor: "lm.small"
# okd_master_flavor: "lm.large.1d"
# okd_worker_flavor: "lm.medium.1d"

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
s3_bucket: "your-bucket-name"
s3_filename: "{{okd_cluster_name}}-{{okd_base_domain}}.ign"

# Change endpoint url if you s3 bucket resides elsewhere
# Make sure that aws s3 presign works on the bucket objekt.
s3_endpoint_url: "https://s3.sto2.safedc.net"

ssh_key_path: "~/.ssh/id_rsa.pub"
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
make_settings ${CLUSTER_NAME} ${DOMAIN} ${DIR}/${CLUSTER_NAME}.${DOMAIN} > ${DIR}/${CLUSTER_NAME}.${DOMAIN}/settings.yml

echo "Now cd to ${DIR}/${CLUSTER_NAME}.${DOMAIN}, change settings.yml to your needs run the playbooks in order"
echo "Each playbook must complete successfully before the next is run"
echo "The bootstrap and finalize playbooks take a long ting to finish"
