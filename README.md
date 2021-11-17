# utilities
Utilities for inteacting with Safesprings platform

# migrate_boot_volume_v1v2.sh
First one needs to take a snapshot in the source platform of the instance that should be migrated.

The script is run with two environment files as arguments:
migate.sh [source-env] [destination-env]

The script will list all the avaiable images and snashots in the source platform. The user then provides then name of the snashot that should be migrated.

Then the script downloads the snapshot, runs qemu-img to convert to qcow2 and then uploads it to the destination platform.

# unset.sh
Utility script to unset the OS-env variables. Also part of the actual migrate.sh script so does not need to be run induvidually but added to the repo for completeness.
