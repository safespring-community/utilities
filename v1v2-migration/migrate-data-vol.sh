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

openstack volume snapshot list
echo "Please provide volume snapshot name:"
read volsnapname
SNAP_SIZE=`openstack volume snapshot show $volsnapname|grep size|cut -d '|' -f 3|sed 's/^[ \t]*//;s/[ \t]*$//'`


echo" Creating migration volume from $volsnapname"
openstack volume create --snapshot $volsnapname --size $SNAP_SIZE $volsnapname.mig

echo" Creating image from migration volume $volsnapname.mig"
openstack image create --volume  $volsnapname.mig $volsnapname.img

# TODO: Wait for operation to complete
#       Remove the migration volume
wait


echo" Downloading image $volsnapname.img" 
openstack image save $volsnapname.img > $volsnapname.raw


echo "Converting image to $volsnapname.qcow2"
qemu-img convert -f raw -O qcow2 $volsnapname.raw $volsnapname.qcow2
if [ $? -eq 0 ] 
then 
      echo "Cleaning up temp raw file $imgname.raw"
      rm $volsnapname.raw 
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
echo "Uploading $volsnapname.qcow2 to destination platform"
openstack image create --disk-format qcow2 --container-format bare --private --min-disk $SNAP_SIZE $volsnapname.img < $volsnapname.qcow2
echo "Cleaning up temp qcow2 image"
rm $volsnapname.qcow2
