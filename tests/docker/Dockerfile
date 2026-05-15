# syntax=docker/dockerfile:1
FROM almalinux:8

RUN <<EOF
set -e
dnf install -y openssh-server python3.12 epel-release sudo
dnf clean all
ssh-keygen -A
useradd -m -s /bin/bash ansible
mkdir -p /etc/sudoers.d /home/ansible/.ssh
echo 'ansible ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ansible
chmod 700 /home/ansible/.ssh
chown ansible:ansible /home/ansible/.ssh
EOF

COPY --chmod=755 entrypoint.sh /entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
