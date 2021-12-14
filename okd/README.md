## Tooling for OKD 4.X installation

Here are the scripts, playbooks, and templates needed to install OKD
using the terraform module(s) in https://github.com/safespring-community/terraform-modules

### Prerequisites

* A project in one of Safespring's v2 sites with minimum resources:
  * Memory: 60GB
  * VCPUs: 16
  * Security groups: 15
  * Security group rules: 40
* Storage access to S3 in sto2 site
* A liveDNS domain @ gandi.net
* An API key for your gandi.net user

### Creating an OKD cluster instance

* Export openstack environment variables
  * `OS_PASSWORD=`
  * `OS_USERNAME=`
  * `OS_AUTH_URL=https://v2.api.osl1.safedc.net:5000/v3`
  * `OS_IDENTITY_API_VERSION=3`
  * `OS_PROJECT_DOMAIN_NAME=`
  * `OS_PROJECT_NAME=`
  * `OS_REGION_NAME=<sto1 or osl1>`
  * `OS_USER_DOMAIN_NAME=`
* Export `GANDI_KEY`
* Export `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
  * For uploading ignition file to s3 bucket
* Run `./bin/new-cluster-instance.sh <cluster-name> <gandi-livedns-domain> <directory>`
  * This will copy all you need to a directory of you own choosing
* `cd <directory>`
* Run the ansible playbooks in order and follow the instructions at the end of each one of them

To see the cluster bootstrap progress in another window:

* `export KUBECONFIG=installer/auth/kubeconfig`
* `watch oc get clusteroperator`

To approve CSRs for joining worker nodes (after control plane bootstrap):

* `export KUBECONFIG=installer/auth/kubeconfig`
* `oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs --no-run-if-empty oc adm certificate approve`
* `oc get nodes` (Workers should appear, first as NotReady, then become ready after a while)

PS: Be patient. It takes up to an hour for OKD to assemble itself. But if there are no changes in cluster operator status for ca. 15 minutes, the installation might have stalled.
