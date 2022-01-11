## Example code for minio standalone server

This setup showcases automated provisioning of a fully functional (without TLS
though) [ Minio S3 storage server](https://min.io) using a [Safespring
terraform module](https://github.com/safespring-community/terraform-modules),
Ansible and the ansible terraform inventory (ATI) script.

ATI makes it possible to map a role in the Safespring terraform module to an
Ansible inventory host group consisting of servere having that role, thus
removing the need to maintain a static ansible inventory every time the setup
is deployed.

Usage:

* Find the public key to inject into the instance (or generate a new one)
* Edit `main.tf` to your liking (read comments)
* Decide wihich site/project to deploy your service
* Ask Safespring to open API-access from your source IP (or CIDR) by sending an email to <support@safespring.com>
* Export environment so that openstack cli works
* `terraform init`
* `terraform apply`
* ssh-add -t XXXXX the private key file matching the public one injected to the instance.
* `ansible-galaxy install atosatto.minio`
* `ansible-playbook -i inventory `minio-server`
* `ls -lart /tmp` , and find the tempfile with the minio server credentials. 
* Run the command in the tempfile 
* Check out the [minio docs](https:/min.io)

For real data:

* Create a dns A-record to the minio ip address
* Use the preinstalled certbot to [create LetsEncrypt certs](https://docs.min.io/docs/generate-let-s-encypt-certificate-using-concert-for-minio.html)
