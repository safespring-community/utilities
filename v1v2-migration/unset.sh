#!/bin/zsh
env|grep OS
for x in `env|grep OS|cut -d= -f 1`; do unset $x; done
env|grep OS
