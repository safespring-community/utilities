oc adm new-project csi --node-selector=""

oc project csi

Openshift does not allow pods to do what csi needs by default:

oc adm policy add-scc-to-user hostaccess -z csi-cinder-controller-sa
oc adm policy add-scc-to-user privileged -z csi-cinder-node-sa

git clone https://github.com/kubernetes/cloud-provider-openstack.git


openstack application credential create foo

cat csi-values.yaml
secret:
  enabled: true
  create: true
  name: cinder-csi-cloud-config
  data:
    cloud-config: |-
      [Global]
      auth-url=https://v2.dashboard.sto1.safedc.net:5000/v3
      application-credential-id=<id>
      application-credential-secret=<secret>

helm install cci -f csi-values.yaml ./cloud-provider-openstack/charts/cinder-csi-plugin


Test storage-class with for example:

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

