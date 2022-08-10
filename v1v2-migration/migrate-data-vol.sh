#!/bin/bash
if [ $# -ne 2 ]
then
    echo "USAGE: migrate-data-vol.sh [os-cloud source] [os-cloude
destination]"
    echo "You need API access correctly setup with a clouds.yaml. Please go
to https://docs.openstack.org/python-openstackclient/pike/configuration/inde
x.html to get directions for how to set that up."
    echo "The script migrates a volume from the source platform to the destination platform"
    echo "For a secure migration the volume should be detached from the instance while migrating"
    echo "The simplest way to achieve this is to power off the machine and detach the volume and then run the script"
    echo "To minimize downtime you can also power down the instance, perform a volume snapshot and then power on the instance again."
    echo "You can then create a new volume from the snapshot and migrate that."
    echo "If the instance is booting from image but has separate volumes it is safest to power down the machine, take an instance snapshot and then volume snapshots on all the attached volumes, power on the instance and then create volumes from the volume snapshots and then run migrate-instance-snapshot.sh for the instance snapshot and migrate-data-vol.sh for all the volumes created from the snapshots."
    exit 1
fi
one_more=1
while [ "$one_more" != "0" ]
do

    # Cleaning up OS-variables before reading source platform variables
    #for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
    # Read source platform variables
    #source $1
    if ! openstack --insecure --os-cloud=$1 volume list; then
        echo $(date -u) ": No contact with source platform"
        exit 1
    fi

    echo "Please provide volume name:"
    read volname
    SNAP_SIZE=`openstack --insecure --os-cloud=$1 volume show -f json $volname|jq -r '.size'`
    VOL_TYPE=`openstack --insecure --os-cloud=$1 volume show -f json $volname|jq -r '.type'`

    echo $(date -u) ": Creating image from volume $volname with size=$SNAP_SIZE and type=$VOL_TYPE..."
    if ! openstack --insecure --os-cloud=$1 image create --volume  "$volname" "$volname".tmp 2> /dev/null; then
        echo $(date -u) ": ERROR! No such volume or volume busy. Have you detached it from the instance?"
        exit 1
    fi
    # Wating for image to be ready
    status="null"
    while [[ $status != "active" ]]
    do
        sleep 5
        status=`openstack --insecure --os-cloud=$1 image show -f json "$volname".tmp|jq -r '.status'`
        echo $(date -u) ": Wating to finish. Image Status: $status"
    done

    echo $(date -u) ": Downloading image $volname.tmp..." 
    openstack --insecure --os-cloud=$1 image save "$volname".tmp > "$volname".raw
    echo $(date -u) ": Cleaning up image $volname.tmp from source platform..."
    openstack --insecure --os-cloud=$1 image delete "$volname".tmp


    echo $(date -u) ": Converting image to $volname.qcow2..."
    qemu-img convert -f raw -O qcow2 "$volname".raw "$volname".qcow2
    if [ $? -eq 0 ] 
    then 
        echo $(date -u) ": Cleaning up temp raw file $volname.raw..."
        rm "$volname".raw
    else 
        echo $(date -u) ": ERROR! Could not convert file" >&2
        exit 1
    fi

# Cleaning up OS-variables before reading target platform variables
# Not needed when using os-cloud, kept if script should be altered to handle both os-cloud and env variables scenario
#for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
# Reading target platform variables
#source $2

echo $(date -u) ": Uploading $volname.qcow2 to destination platform..."
if ! openstack --os-cloud=$2 image create --disk-format qcow2 --container-format bare --private --min-disk "$SNAP_SIZE" "$volname".img < "$volname".qcow2 2> /dev/null; then
    echo $(date -u) ": ERROR! No contact with destination platform"
    exit 1
fi
echo $(date -u) ": Cleaning up temp qcow2 image"
rm "$volname".qcow2
echo $(date -u) ": Create volume from $volname.img..."
openstack --os-cloud=$2 volume create --image "$volname".img --size "$SNAP_SIZE" --type "$VOL_TYPE" "$volname" 2> /dev/null

status="null"
while [[ $status != "available" ]]
do
    sleep 5
    status=`openstack --os-cloud=$2 volume show -f json $volname|jq -r '.status'`
    echo $(date -u) ": Wating to finish. Volume Status: $status"
    if [ "$status" = "error" ]; then
        vol_id=`openstack --os-cloud=$2 volume show -f json "$volname"|jq -r '.id'`
        echo $(date -u) ": ERROR! Could not create volumei with id $vol_id. Plz run the script again. If problem persists contact support@safespring.com with volume id and timestamp. Cleaning up..."
        openstack --os-cloud=$2 volume delete "$volname"
        openstack --os-cloud=$2 image delete "$volname".img
        exit 1
    fi
done
echo $(date -u) ": Cleaning up $volname.img image..."
openstack --os-cloud=$2 image delete "$volname".img
echo $(date -u) ": Finished! You can now use the volume $volname in the new platform."
echo "Do you want to migrate another volume? (NO=0, YES=1)"
read one_more
done
