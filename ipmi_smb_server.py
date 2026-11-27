#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPMIAccess — standalone SMB server for BMC virtual media.

Windows' built-in SMB stack on some systems is broken or requires a reboot;
this tiny server (based on impacket) shares the iso_share folder on port 445
with guest/anonymous access so the Supermicro BMC can mount an ISO as a
virtual CD-ROM. SMB1 and SMB2 are both enabled — the BMC negotiates what it
supports.

Run AFTER stopping the Windows Server service (it owns port 445):
    net stop lanmanserver /y
Restore Windows sharing afterwards with:
    net start lanmanserver
"""
import logging
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, 'vendor'))

from impacket import smbserver  # noqa: E402
from impacket.smbserver import LOG  # noqa: E402

# ATEN BMC asks for the share in lower case ("ipmi_iso") while impacket stores
# share names upper case and compares case-sensitively — make lookup
# case-insensitive.
_orig_searchShare = smbserver.searchShare


def _searchShare_ci(connId, share, smbServer):
    result = _orig_searchShare(connId, share, smbServer)
    if result is None and isinstance(share, str):
        result = _orig_searchShare(connId, share.upper(), smbServer)
    return result


smbserver.searchShare = _searchShare_ci

ISO_DIR = os.path.join(BASE, 'iso_share')
LOG_FILE = os.path.join(BASE, 'ipmi_smb.log')


def main():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.DEBUG,
        format='%(asctime)s %(message)s',
    )
    LOG.setLevel(logging.DEBUG)
    # console too
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    LOG.addHandler(ch)

    server = smbserver.SimpleSMBServer('0.0.0.0', 445)
    server.setSMB2Support(True)          # let the BMC negotiate SMB1 or SMB2
    server.addShare('IPMI_ISO', ISO_DIR, 'IPMI virtual media', readOnly='yes')

    print('IPMIAccess SMB server: \\\\%s\\ipmi_iso -> %s' % (os.environ.get('COMPUTERNAME', '?'), ISO_DIR))
    print('Guest/anonymous access enabled. Ctrl+C to stop.')
    LOG.info('SMB server started, share ipmi_iso -> %s', ISO_DIR)
    try:
        server.start()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
