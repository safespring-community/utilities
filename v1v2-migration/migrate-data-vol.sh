#!/bin/bash
if [ $# -ne 2 ]
  then
    echo "USAGE: migrate.sh [rc-file source] [rc-file-destination]"
    echo "You need two OpenStack rc-files for API connection, one for source and one for the destination platform."
    echo "The script migrates a volume from the source platform to the destination platform"
    echo "For a secure migration the volume should be detached from the instance while migrating"
    echo "The simplest way to achieve this is to power off the machine and detach the volume and then run the script"
    echo "To minimize downtime you can also power down the instance, perform a volume snapshot and then power on the instance again."
    echo "Then you can create a new volume from the snapshot and migrate that."
    echo "If the instance is booting from image but has separate volumes it is safest to power down the machine, take an instance snapshot and then volume snapshots on all the attached volumes, power on the instance and then create volumes from the volume snapshots and then run migrate-boot-vol.sh for the instance snapshot and migrate-data-vol.sh for all the volumes created from the snapshots."
    exit 1
fi

# Cleaning up OS-variables before reading source platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Read source platform variables
source $1
if ! openstack volume list; then
    echo "No contact with source platform"
    exit 1
fi

echo "Please provide volume name:"
read volname
SNAP_SIZE=`openstack volume show -f json $volname|jq -r '.size'`

echo "Creating image from volume $volname with snap_size=$SNAP_SIZE"
openstack image create --volume  $volname $volname.tmp
# Wating for image to be ready
status="null"
while [[ $status != "active" ]]
do
    sleep 5
    status=`openstack image show -f json $volname.tmp|jq -r '.status'`
    echo "Wating to finish. Image Status: $status"
done

echo "Downloading image $volname.tmp..." 
openstack image save $volname.tmp > $volname.raw
echo "Cleaning up image $volname.tmp from source platform..."
openstack image delete $volname.tmp


echo "Converting image to $volname.qcow2..."
qemu-img convert -f raw -O qcow2 $volname.raw $volname.qcow2
if [ $? -eq 0 ] 
then 
      echo "Cleaning up temp raw file $volname.raw..."
      rm $volname.raw 
  else 
        echo "ERROR! Could not convert file" >&2
        exit 1
fi

# Cleaning up OS-variables before reading target platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Reading target platform variables
source $2

echo "Uploading $volname.qcow2 to destination platform..."
if ! openstack image create --disk-format qcow2 --container-format bare --private --min-disk $SNAP_SIZE $volname.img < $volname.qcow2; then
    echo "ERROR! No contact with destination platform"
    exit 1
fi
echo "Cleaning up temp qcow2 image"
rm $volname.qcow2
echo "Create volume from $volname.img..."
openstack volume create --image $volname.img --size $SNAP_SIZE --type fast $volname

status="null"
while [[ $status != "available" ]]
do
    sleep 5
    status=`openstack volume show -f json $volname|jq -r '.status'`
    echo "Wating to finish. Volume Status: $status"
done
echo "Cleaning up $volname.img image..."
openstack image delete $volname.img
echo "Finished! You can now boot you server from the volume $volname in the new platform."
