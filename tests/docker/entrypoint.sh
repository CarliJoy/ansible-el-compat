#!/bin/bash
set -e
if [ -n "$SSH_PUBKEY" ]; then
    printf '%s\n' "$SSH_PUBKEY" > /home/ansible/.ssh/authorized_keys
    chmod 600 /home/ansible/.ssh/authorized_keys
    chown ansible:ansible /home/ansible/.ssh/authorized_keys
fi
exec /usr/sbin/sshd -D
