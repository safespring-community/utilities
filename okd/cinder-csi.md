# Cinder CSI on okd

Here is a recipe for one way to enable persistent volumes on okd running in
openstack. This approach uses application credentials to enable an okd-cluster
to automatically provision and attach persistent volumes (PVs) to pods using
the official Openstack Cinder container storage interface (CSI) from the
Kubernetes cloud provider for openstack.

First create a new project/namespace with an empty node selector in order to
let the daemonset of Cinder CSI run on all cluster nodes including master
nodes.

```
$ oc adm new-project csi --node-selector=""
$ oc project csi
```

The service-accounts running the node-daemonset and the controller-deployment
needs higher privileges than Openshift allows by default.  To allow these
services to run, the following commands will add the neceassary Security
Context Constraints (SCCs). SCCs are openshift specific and implements
restriciton for what pods are allowed to do in a simililar way like Pod
Security Policies (PSPs). It is possible to use PSPs in Openshift, however it
is easier to re-use premade SCCs than designing and PSPs with similar effect
and then use those. However, in some situations it might be necessary to
tighten security even closer to exactly what the cinder CSI needs and then it
it possible to create your own SCCs and/or PSPs implementing for implementing
that.

```
$ oc adm policy add-scc-to-user hostaccess -z csi-cinder-controller-sa
$ oc adm policy add-scc-to-user privileged -z csi-cinder-node-sa
```

Clone the git repo for the Kubernetes openstack cloud pirovider and check out the corresponding tag for correct kubernetes version.

```
$ git clone https://github.com/kubernetes/cloud-provider-openstack.git
$ oc version
Client Version: 4.9.0-0.okd-2021-11-28-035710
Server Version: 4.9.0-0.okd-2021-12-12-025847
Kubernetes Version: v1.22.1-1824+934e08bc2ce38f-dirty
$ cd cloud-provider-openstack
$ git tag
(...)
v1.22.1
$ git checkout v1.22.1
```

Create application credentials in the project.
```
openstack application credential create <app-cred-name>
```

Use the id and secret of the application credential in the cloud config for the helm chart deployment embedded in a helm chart values file.
```
$ cat csi-values.yaml
secret:
  enabled: true
  create: true
  name: cinder-csi-cloud-config
  data:
    cloud-config: |-
      [Global]
      auth-url=<the-api-endpoint-of-openstack-where-the-cluster-lives>
      application-credential-id=<id>
      application-credential-secret=<secret>
```

Deploy the chart to the project you created
```
helm install <name-of-helm-chart-deployment> -f csi-values.yaml ./cloud-provider-openstack/charts/cinder-csi-plugin
```

Check that all pods came up and/or check events and/or logs. Also check that the storage classes from the chart were created
```
$ oc get pods
NAME                                                     READY   STATUS    RESTARTS   AGE
openstack-cinder-csi-controllerplugin-6dcbdd9bc8-qrpjn   6/6     Running   0          19h
openstack-cinder-csi-nodeplugin-kmk4r                    3/3     Running   0          19h
openstack-cinder-csi-nodeplugin-l2kjc                    3/3     Running   0          19h
openstack-cinder-csi-nodeplugin-mrvxb                    3/3     Running   0          19h
openstack-cinder-csi-nodeplugin-rzczl                    3/3     Running   0          19h
openstack-cinder-csi-nodeplugin-z5s52                    3/3     Running   0          19h

$ oc logs openstack-cinder-csi-controllerplugin-6dcbdd9bc8-qrpjn
error: a container name must be specified for pod openstack-cinder-csi-controllerplugin-6dcbdd9bc8-qrpjn, choose one of: [csi-attacher csi-provisioner csi-snapshotter csi-resizer liveness-probe cinder-csi-plugin]
$ oc logs openstack-cinder-csi-controllerplugin-6dcbdd9bc8-qrpjn -c cinder-csi-plugin
(...)
$ oc get events
(...)
$ oc get storageclass
NAME                   PROVISIONER                RECLAIMPOLICY   VOLUMEBINDINGMODE   ALLOWVOLUMEEXPANSION   AGE
csi-cinder-sc-delete   cinder.csi.openstack.org   Delete          Immediate           true                   19h
csi-cinder-sc-retain   cinder.csi.openstack.org   Retain          Immediate           true                   19h
```

To test that dynamic provisioning and attachment you can apply this in a new project. It will create a persistent volume claim (PVC) and a pod utilising that PVC.
```
$ oc new-project bar
$ cat pvc-test.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: csi-pvc-cinderplugin
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  storageClassName: csi-cinder-sc-delete

---
apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  containers:
  - image: nginx
    imagePullPolicy: IfNotPresent
    name: nginx
    ports:
    - containerPort: 80
      protocol: TCP
    volumeMounts:
      - mountPath: /var/lib/www/html
        name: csi-data-cinderplugin
  volumes:
  - name: csi-data-cinderplugin
    persistentVolumeClaim:
      claimName: csi-pvc-cinderplugin
      readOnly: false

$oc apply -f pvc-test.yaml
persistentvolumeclaim/csi-pvc-cinderplugin created
pod/nginx created
```

Check that the PVC, PV, pod and attachments were made.
```
$ oc get pvc
NAME                   STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS           AGE
csi-pvc-cinderplugin   Bound    pvc-05650fd3-9ce3-4685-b9e8-614c84f31ccb   1Gi        RWO            csi-cinder-sc-delete   34s

$ oc get pv
NAME                                       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                      STORAGECLASS           REASON   AGE
pvc-05650fd3-9ce3-4685-b9e8-614c84f31ccb   1Gi        RWO            Delete           Bound    bar/csi-pvc-cinderplugin   csi-cinder-sc-delete            63s

$ oc get volumeattachments
NAME                                                                   ATTACHER                   PV                                         NODE                   ATTACHED   AGE
csi-2e0590e5d4cf01ae74666d6204159172a2db8dfa58e2a214ed58e4a483abf9e0   cinder.csi.openstack.org   pvc-05650fd3-9ce3-4685-b9e8-614c84f31ccb   worker-1-wip.saft.in   true       110s

$ oc get pods -o wide
NAME    READY   STATUS    RESTARTS   AGE    IP             NODE                   NOMINATED NODE   READINESS GATES
nginx   1/1     Running   0          3m3s   10.128.3.129   worker-1-wip.saft.in   <none>           <none>

$ openstack server show  worker-1-wip.saft.in
+-----------------------------+----------------------------------------------------------+
| Field                       | Value                                                    |
+-----------------------------+----------------------------------------------------------+
| OS-DCF:diskConfig           | MANUAL                                                   |
| OS-EXT-AZ:availability_zone | nova                                                     |
| OS-EXT-STS:power_state      | Running                                                  |
| OS-EXT-STS:task_state       | None                                                     |
| OS-EXT-STS:vm_state         | active                                                   |
| OS-SRV-USG:launched_at      | 2021-12-20T13:44:54.000000                               |
| OS-SRV-USG:terminated_at    | None                                                     |
| accessIPv4                  |                                                          |
| accessIPv6                  |                                                          |
| addresses                   | public=185.189.29.83, 2a0a:bcc0:40::475                  |
| config_drive                |                                                          |
| created                     | 2021-12-20T13:43:24Z                                     |
| flavor                      | m.medium (54fc7aef-ce1c-461f-aae5-803a38d6b28d)          |
| hostId                      | be6a5706b78a6cef606167b572d305cc6f6abffe0ce8e9d47ae86c7b |
| id                          | 3a724f09-052e-4b8c-84b0-405a3a9e72ee                     |
| image                       | N/A (booted from volume)                                 |
| key_name                    | None                                                     |
| name                        | worker-1-wip.saft.in                                     |
| progress                    | 0                                                        |
| project_id                  | e781ccfd60474dcda723cc638384bd60                         |
| properties                  | role='worker'                                            |
| security_groups             | name='wip-all_ports'                                     |
|                             | name='wip-ssh'                                           |
|                             | name='wip-cluster'                                       |
| status                      | ACTIVE                                                   |
| updated                     | 2021-12-20T13:44:54Z                                     |
| user_id                     | fa2679f75828421a87cd092fbdf898e6                         |
| volumes_attached            | id='35bcc25a-fc11-44b6-b333-029944fc34dd'                |
|                             | id='86bda412-59ea-471b-8831-31aac4d472b5'                |
+-----------------------------+----------------------------------------------------------+

$ openstack volume show 86bda412-59ea-471b-8831-31aac4d472b5
+------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Field                        | Value                                                                                                                                                                                                                                                                                                                               |
+------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| attachments                  | [{'server_id': '3a724f09-052e-4b8c-84b0-405a3a9e72ee', 'attachment_id': 'f9d869de-44d5-40a9-bf6c-b243471fb7b8', 'attached_at': '2021-12-30T10:04:34.000000', 'host_name': 'sto1-os-cl-1.node.safedc.net', 'volume_id': '86bda412-59ea-471b-8831-31aac4d472b5', 'device': '/dev/vdb', 'id': '86bda412-59ea-471b-8831-31aac4d472b5'}] |
| availability_zone            | nova                                                                                                                                                                                                                                                                                                                                |
| bootable                     | false                                                                                                                                                                                                                                                                                                                               |
| consistencygroup_id          | None                                                                                                                                                                                                                                                                                                                                |
| created_at                   | 2021-12-30T10:04:31.000000                                                                                                                                                                                                                                                                                                          |
| description                  | Created by OpenStack Cinder CSI driver                                                                                                                                                                                                                                                                                              |
| encrypted                    | False                                                                                                                                                                                                                                                                                                                               |
| id                           | 86bda412-59ea-471b-8831-31aac4d472b5                                                                                                                                                                                                                                                                                                |
| multiattach                  | False                                                                                                                                                                                                                                                                                                                               |
| name                         | pvc-05650fd3-9ce3-4685-b9e8-614c84f31ccb                                                                                                                                                                                                                                                                                            |
| os-vol-tenant-attr:tenant_id | e781ccfd60474dcda723cc638384bd60                                                                                                                                                                                                                                                                                                    |
| properties                   | cinder.csi.openstack.org/cluster='kubernetes', csi.storage.k8s.io/pv/name='pvc-05650fd3-9ce3-4685-b9e8-614c84f31ccb', csi.storage.k8s.io/pvc/name='csi-pvc-cinderplugin', csi.storage.k8s.io/pvc/namespace='bar'                                                                                                                    |
| replication_status           | None                                                                                                                                                                                                                                                                                                                                |
| size                         | 1                                                                                                                                                                                                                                                                                                                                   |
| snapshot_id                  | None                                                                                                                                                                                                                                                                                                                                |
| source_volid                 | None                                                                                                                                                                                                                                                                                                                                |
| status                       | in-use                                                                                                                                                                                                                                                                                                                              |
| type                         | fast                                                                                                                                                                                                                                                                                                                                |
| updated_at                   | 2021-12-30T10:04:35.000000                                                                                                                                                                                                                                                                                                          |
| user_id                      | fa2679f75828421a87cd092fbdf898e6                                                                                                                                                                                                                                                                                                    |
+------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
```
