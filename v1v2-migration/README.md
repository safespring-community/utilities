# utilities
Utilities for interacting with Safesprings platform

# migrate-instance-snapshot.sh
Prerequisites: Openstack Python CLI client, qemu-utils, double the space to hold the size of the snapshot you want to migrate in the directory where you run the script

First one needs to take a snapshot in the source platform of the instance that should be migrated.

The script is run with two environment files as arguments:
migate-instance-snapshot.sh [source-env] [destination-env]

The script will list all the available images and snapshots in the source platform. The user then provides the name of the snapshot that should be migrated.

The script downloads the snapshot, runs qemu-img to convert to qcow2 and then uploads it to the destination platform.

# migrate-data-vol.sh
Prerequisites: Openstack Python CLI client, qemu-utils, double the space to hold the size of the volume you want to migrate in the directory where you run the script

The script is run with two environment files for OpenStack API access as arguments:
migate-data-vol.sh [source-env] [destination-env]

The script first lists all available volumes in the source platform. You provide the name of the volume you want to migrate and the script will do the rest. At the end the script will ask you if you want to migrate another volume which could be practical if you have more volumes than one attached to an instance you want to migrate.


# Migration of instances (different cases)
If the instance you are migration boots from an image and has no additional volumes you shut down the instance and take an instance snapshot with the button at the end of the row in the instance listing. When the snapshot has finished you boot up the instance again and run the script and points it to the instance snapshot you just made.

If the instance boots from volume you shut down the instance and perform a volume snapshot in the volume listing view. Once that is done you can boot the instance again and create a volume from the volume snapshot and use that as input when running the migrate-data-vol.sh script.

If the instance boots from image and has one or more additional data volumes you first shut down the instance. You then perform an instance snapshot (in the instance listing view) and then go to Volumes and create volume snapshots for all the volumes attached to the instance. You then create new migration volumes from the volume snapshots. When that is done you use the migrate-instance-snapshot.sh to migrate the instance and the migrate-data-vol.sh script to migrate the attached volumes. 

# unset.sh
Utility script to unset the OS-env variables. Also part of the actual migrate script so does not need to be run indvidually but added to the repo for completeness.
