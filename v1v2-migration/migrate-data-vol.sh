#!/bin/bash
if [ $# -ne 2 ]
  then
    echo "migrate.sh [rc-file source] [rc-file-destination]"
    exit 1
fi

#echo "This script ihas not been tested, use it as reference and do not run i directly. Exiting."
#exit 1

# Cleaning up OS-variables before reading source platform variables
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Read source platform variables
source $1
if ! openstack token issue; then
    echo "No contact with source platform"
    exit 1
fi

openstack volume list
echo "Please provide volume name:"
read volname
SNAP_SIZE=`openstack volume show $volname|grep size|head -1|cut -d '|' -f 3|sed 's/^[ \t]*//;s/[ \t]*$//'`

#echo $SNAP_SIZE
#echo "Creating migration volume from $volsnapname"
#openstack volume create --snapshot $volsnapname --size $SNAP_SIZE $volsnapname.mig

echo "Creating image from volume $volname"
openstack image create --volume  $volname $volname.tmp

# TODO: Wait for operation to complete, by checing  state of "openstack image list" is not "SAVING" anymore
#       Remove the migration volume
status="null"

while [[ $status != "active" ]]
do
    status=`openstack image show $volname.tmp|grep status|cut -d '|' -f 3|sed 's/^[ \t]*//;s/[ \t]*$//'`
    echo "Image Status: $status"
    sleep 5
done

echo "Downloading image $volname.tmp" 
openstack image save $volname.tmp > $volname.raw
echo "Cleaning up image $volname.tmp from source platform"
openstack image delete $volname.tmp


echo "Converting image to $volname.qcow2"
qemu-img convert -f raw -O qcow2 $volname.raw $volname.qcow2
if [ $? -eq 0 ] 
then 
      echo "Cleaning up temp raw file $volname.raw"
      rm $volname.raw 
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
echo "Uploading $volname.qcow2 to destination platform"
openstack image create --disk-format qcow2 --container-format bare --private --min-disk $SNAP_SIZE $volname.img < $volname.qcow2
echo "Cleaning up temp qcow2 image"
rm $volname.qcow2
echo "Create volume from $volname.img"
openstack image create --image $volname.img --size $SNAP_SIZE --type fast $volname
echo "Cleaning up $volname.img"
openstack image delete $volname.img
echo "Finished! You can now boot you server from the volume$volname in the new platform"
