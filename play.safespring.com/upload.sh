#!/bin/zsh

s3cmd -c ~/.s3cfgs/play.safespring.com sync --recursive ./ProcessedVideos/* s3://processedvideos/
s3cmd -c ~/.s3cfgs/play.safespring.com sync --recursive ./RawVideos/* s3://rawvideos/
s3cmd -c ~/.s3cfgs/play.safespring.com setacl --acl-public --recursive s3://processedvideos/
s3cmd -c ~/.s3cfgs/play.safespring.com setacl --acl-public --recursive s3://rawvideos/

echo "Processed Video URL at: https://s3.sto1.safedc.net/a489f53964f14fe897308b4243d7138d:processedvideos/{filename}"
echo "Raw Video URL at: https://s3.sto1.safedc.net/a489f53964f14fe897308b4243d7138d:rawvideos/{filename}"

