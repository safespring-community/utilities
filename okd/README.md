## Tooling for OKD 4.X installation

Here are the scripts, playbooks, and templates needed to install OKD
using the terraform module(s) in https://github.com/safespring-community/terraform-modules

### Prerequisites

* A project in one of Safespring's v2 sites with "OKD-minimal" resource profile:
* An ACL entry allowing openstack API access from your source IP address. This can be obtained by sending an email to <support@safespring.com>
  * Or even better: use a jumphost (which is already whitelisted). See https://www.safespring.com/blogg/2022/2022-08-using-jumphost-for-safespring-apis/
* A liveDNS domain @ gandi.net
* An API key for your gandi.net user (export GANDI_PERSONAL_ACCESS_TOKEN=xxxxxxx)
  * See 
* Following packages installed
  * jq
  * ansible

### Creating an OKD cluster instance


* Use [application credentials][appcredz] to deploy the cluster. The following environment must be set:
  * `OS_AUTH_URL=`
  * `OS_APPLICATION_CREDENTIAL_SECRET=`
  * `OS_APPLICATION_CREDENTIAL_ID=`
  * `OS_APPLICATION_CREDENTIAL_NAME=`
  * `OS_AUTH_TYPE=v3applicationcredential`
* Export `GANDI_PERSONAL_ACCESS_TOKEN`
* Run `./bin/new-cluster-instance.sh <cluster-name> <gandi-livedns-domain> <directory>`
  * This will copy all you need to a directory of you own choosing
* `cd <directory>`
* Adjust settings.yaml to your needs
  * Ensure that the ssh-key is correct, and that you have added the private part of it before running plabooks 03-.. and 04-..
* Run the ansible playbooks in order and follow the instructions at the end of each one of them
  * The playbooks ( 03 and 04 ) must be run with option `-i ati` in order to include inventory for the loadbalancer node.
```console
$ ansible-playbook 01-installer-image.yml
$ ansible-playbook -i ati 02-cluster-bootstrap.yml
$ ansible-playbook -i ati 03-cluster-finalize.yml
```

To see the cluster bootstrap progress in another window:

* `export KUBECONFIG=installer/auth/kubeconfig`
* `watch oc get clusteroperator`

To approve CSRs for joining worker nodes (after control plane bootstrap):

* `export KUBECONFIG=installer/auth/kubeconfig`
* `oc get csr -o go-template='{{range .items}}{{if not .status}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}' | xargs --no-run-if-empty oc adm certificate approve`
* `oc get nodes` (Workers should appear, first as NotReady, then become ready after a while)
* When installing OCP (Enterprise), use ./bin/oc instead of just oc

PS: Be patient. It takes up to an hour for OKD to assemble itself. But if there are no changes in cluster operator status for ca. 15 minutes, the installation might have stalled.

PS2: If more than 24h passed and you wan't to re-use the instance previously deployed (and destroyed) you **must** remove the `installer` directory.

### Default kubeadmin credentials

Default kubeadmin credentials can be found in file installer/auth/kubeadmin-password

### Worker sets

Sets of worker nodes are now maintained as a terraform map which initially is
injecteted to the terraform config (`cluster.tf`) via the default
`settings.yml`.  Each set needs specificatione of setname (only used internaly
in terraform) count, prefix and flavor. Please see comments in the generated
default `settings.yml` for details.

---
**NOTE**

To remove cluster just run `terraform destroy`. Do not reuse the created
installer directory when re-installing a cluster. The certificates in the
installer directory expire after 24 hours. The playbook will create a new installer directory if it
does not exist: thus just remove the old one after `terraform destroy`.

Opentufu should work eqully well as Terraform in provisioning the cluster, however, it is not yet tested.
**Known issues**

Sometimes Ansible fails to set up HAProxy on the lb-node. If this happens, just
re-run the playbook once more.

---

[appcreds]: https://docs.safespring.com/new/app-creds/
