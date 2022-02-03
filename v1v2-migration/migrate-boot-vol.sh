#!/bin/bash
if [ $# -ne 2 ]
  then
     echo "USAGE: migrate-boot-vol.sh [rc-file source] [rc-file-destination]"
    echo "You need two OpenStack rc-files for API connection, one for source and one for the destination platform."
    echo "The script migrates a snapshot from the source platform to the destination platform."
    echo "When running the script you will be provided with a list of images/snapshots and asked to type which snapshot to migrate to the new platform"
    echo "For a secure migration the instance should be shut down before taking the snapshot"
    echo "If the instance is booting from image but has separate volumes it is safestto power down the machine, take an instance snapshot and then volume snapshots on all the attached volumes, power on the instance and then create volumes from the volumesnapshots and then run migrate-boot-vol.sh for the instance snapshot and migrate-data-vol.sh for all the volumes created from the snapshots."
    exit 1
fi

# Cleaning up OS-variables before reading source platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Read source platform variables
source $1

if ! openstack image list; then
    echo "No contact with source platform"
    exit 1
fi

echo "Please provide image name:"
read imgname
MIN_DISK=`openstack image show -f json $imgname|jq -r '.min_disk'`
echo "Downloading image $imgname with min_disk=$MIN_DISK"
openstack image save $imgname > $imgname.raw
echo "Converting image to $imgname.qcow2"
qemu-img convert -f raw -O qcow2 $imgname.raw $imgname.qcow2
if [ $? -eq 0 ] 
then 
      echo "Cleaning up temp raw file $imgname.raw"
      rm $imgname.raw 
  else 
        echo "Could not convert file" >&2
        exit 1
fi

# Cleaning up OS-variables before reading target platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Reading target platform variables
source $2

echo "Uploading $imgname.qcow2 to destination platform"
if ! openstack image create --disk-format qcow2 --container-format bare --private --min-disk $MIN_DISK $imgname < $imgname.qcow2; then
    echo "No contact with destination platform"
    exit 1
fi
echo "Cleaning up temp qcow2 image"
rm $imgname.qcow2
