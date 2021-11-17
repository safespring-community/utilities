#!/bin/bash
if [ $# -ne 2 ]
  then
    echo "migrate.sh [rc-file source] [rc-file-destination]"
    exit 1
fi

# Cleaning up OS-variables before reading source platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Read source platform variables
source $1
if ! openstack token issue; then
    echo "No contact with source platform"
    exit 1
fi

openstack image list
echo "Please provide image name:"
read imgname
MIN_DISK=`openstack image show $imgname|grep min_disk|cut -d '|' -f 3|sed 's/^[ \t]*//;s/[ \t]*$//'`
echo" Downloading image $imgname"
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

if ! openstack token issue; then
    echo "No contact with destination platform"
    exit 1
fi
echo "Uploading $imgname.qcow2 to destination platform"
openstack image create --disk-format qcow2 --container-format bare --private --min-disk $MIN_DISK $imgname < $imgname.qcow2
echo "Cleaning up temp qcow2 image"
rm $imgname.qcow2
