#!/usr/libexec/platform-python
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is the bootstrap wrapper for the carlijoy.compat.dnf binary module.
# The module code bundled in this zip (ansible/modules/dnf.py and all
# ansible/module_utils/* dependencies) is unmodified from ansible-core 2.15.0.
#
# Original dnf module authors:
#   Copyright 2015 Cristian van Ee <cristian at cvee.org>
#   Copyright 2015 Igor Gnatenko <i.gnatenko.brain@gmail.com>
#   Copyright 2018 Adam Miller <admiller@redhat.com>
#
# Original source: https://github.com/ansible/ansible/blob/v2.15.0/lib/ansible/modules/dnf.py
# License of bundled code: GNU General Public License v3.0 or later (GPL-3.0-or-later)
#
# This bootstrap wrapper itself:
#   SPDX-FileCopyrightText: 2025 Carli* Freudenberg <kound@posteo.de>
#   SPDX-License-Identifier: GPL-3.0-or-later
"""Bootstrap for carlijoy.compat.dnf binary module.

Ansible binary-module protocol
-------------------------------
The controller transfers this zip-executable to the remote host as
``AnsiballZ_dnf`` and runs::

    /usr/libexec/platform-python AnsiballZ_dnf <args-file>

where ``<args-file>`` contains ``json.dumps(module_args)`` — the bare module
parameters without the ``ANSIBLE_MODULE_ARGS`` wrapper expected by
``AnsibleModule._load_params()``.

We filter the args so that only ``_ansible_*`` keys known to ansible-core 2.15
(derived from ``PASS_VARS`` in ``ansible.module_utils.common.parameters``) are
passed through. Keys added by newer controller versions (e.g.
``_ansible_ignore_unknown_opts``, ``_ansible_target_log_info``,
``_ansible_tracebacks_for``) are dropped to avoid "Unsupported parameters"
errors from the bundled 2.15 ``AnsibleModule``.

We inject the cleaned args via ``_ANSIBLE_ARGS`` before the bundled dnf module
is imported; ``_load_params()`` checks that global first and short-circuits
the argv/stdin path.
"""

import json
import sys
from pathlib import Path

# _ansible_* keys accepted by ansible-core 2.15 PASS_VARS (from
# ansible.module_utils.common.parameters). Derived from the bundled source.
_KNOWN_ANSIBLE_INTERNAL = {
    "_ansible_check_mode",
    "_ansible_debug",
    "_ansible_diff",
    "_ansible_keep_remote_files",
    "_ansible_module_name",
    "_ansible_no_log",
    "_ansible_remote_tmp",
    "_ansible_selinux_special_fs",
    "_ansible_shell_executable",
    "_ansible_socket",
    "_ansible_string_conversion_action",
    "_ansible_syslog_facility",
    "_ansible_tmpdir",
    "_ansible_verbosity",
    "_ansible_version",
}


def run() -> None:
    """Entry point: inject args then hand off to the bundled dnf module."""
    _here = Path(__file__).parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        raw = json.loads(Path(sys.argv[1]).read_bytes())
        clean = {
            k: v
            for k, v in raw.items()
            if not k.startswith("_ansible_") or k in _KNOWN_ANSIBLE_INTERNAL
        }
        import ansible.module_utils.basic as _basic

        _basic._ANSIBLE_ARGS = json.dumps({"ANSIBLE_MODULE_ARGS": clean}).encode("utf-8")

    from ansible.modules.dnf import main

    main()


if __name__ == "__main__":
    run()
