#!/usr/bin/env sh
# This script is designed to facilitate secure access to Kubernetes resources by
# generating a dedicated kubeconfig file for a specific service account.
#
# It's particularly useful for administrators and DevOps teams who manage
# Kubernetes clusters and need to distribute access to users or automated systems
# (such as CI/CD pipelines) without sharing personal credentials.
#
# By executing this script, a new kubeconfig file is created, configured to
# authenticate as a predefined service account within a specific namespace.
#
# This approach enhances security by limiting access to what's necessary for the
# tasks at hand and avoids the potential risks associated with broader access rights.
# It's an ideal solution for those looking to streamline access management in a
# Kubernetes environment, ensuring operations are both secure and efficient.

set -eu

# Define the kubeconfig filename
kubeconfig="kubeconfig-sa.yaml"

# Check for kubectl, fall back to oc if not found
if command -v kubectl /dev/null 2>&1; then
	CLI="kubectl"
elif command -v oc /dev/null 2>&1; then
	CLI="oc"
else
	echo "Neither kubectl nor oc command is available."
	exit 1
fi

script_dir=$(dirname "$0")

# Extract the namespace from the kustomization.yaml file
namespace=$(sed -n 's/^namespace: \(.*\)/\1/p' "${script_dir}/kustomization.yaml")

# Extract the service account secret token name from the serviceaccount-token.yaml file
# and then get the token
sa_secret_name=$(sed -n 's/^[[:space:]]*name: \(.*\)/\1/p' "${script_dir}/serviceaccount-token.yaml")
token=$(${CLI} -n "${namespace}" get secret "${sa_secret_name}" -o jsonpath='{.data.token}')
token=$(echo "${token}" | base64 -d)

# Extract the current Kubernetes API server URL from the kubeconfig of the
# currently logged-in user
cluster=$(${CLI} config view --minify --output jsonpath="{.clusters[*].cluster.server}")
clustername_and_port=${cluster#*//}
clustername=${clustername_and_port%:*}
echo "API cluster has the name ${clustername}"

# Create new kubeconfig file
${CLI} config --kubeconfig="${kubeconfig}.tmp" set-cluster "${clustername}" --server="${cluster}"
${CLI} config --kubeconfig="${kubeconfig}.tmp" set-credentials "${clustername}/${namespace}/sa-user" --token="${token}"
${CLI} config --kubeconfig="${kubeconfig}.tmp" set-context "${clustername}/${namespace}/sa-user" --cluster="${clustername}" --namespace="${namespace}" --user="${clustername}/${namespace}/sa-user"
${CLI} config --kubeconfig="${kubeconfig}.tmp" use-context "${clustername}/${namespace}/sa-user"

mv -f "${kubeconfig}.tmp" "${kubeconfig}"
